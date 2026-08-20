import json
import re

import pytest

from app.config import settings
from app.services.drive_estratti_conto_ingest import (
    _discover_work_items,
    _folder_ids,
    _nexi_folder_ids,
    _work_item_priority,
)


FOLDER = "application/vnd.google-apps.folder"


class _Request:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Files:
    def __init__(self, tree):
        self.tree = tree

    def list(self, **kwargs):
        query = kwargs.get("q") or ""
        match = re.search(r"'([^']+)' in parents", query)
        parent = match.group(1) if match else ""
        return _Request({"files": self.tree.get(parent, [])})


class _Service:
    def __init__(self, tree):
        self._files = _Files(tree)

    def files(self):
        return self._files


def _folder(id_, name):
    return {"id": id_, "name": name, "mimeType": FOLDER}


def _file(id_, name):
    return {"id": id_, "name": name, "mimeType": "application/octet-stream"}


@pytest.fixture(autouse=True)
def _senza_soglia_arretrato(monkeypatch):
    """Qui si verifica l'instradamento, non il blocco dell'arretrato.

    Il filtro per anno ha un test suo; lasciarlo acceso farebbe sparire da
    questi casi i documenti storici che servono proprio a provare che
    vengono classificati bene.
    """
    monkeypatch.setattr(settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 0, raising=False)


def test_scansione_ricorsiva_separa_banca_pos_paypal_e_ignora_archivi():
    service = _Service({
        "root": [
            _folder("bnl", "BNL"), _folder("pos", "pos bpm"),
            _folder("paypal", "Paypal"), _folder("done", "Elaborate"),
        ],
        "bnl": [_file("ec1", "2019-Q4 Estratto BNL.pdf"), _folder("bnl_done", "Elaborate")],
        "bnl_done": [_file("old", "gia-elaborato.pdf")],
        "pos": [
            _file("pos1", "Export_Mensile_Giugno_2026.csv"),
            _file("fee", "Commissioni_Giugno_2026.xlsx"),
            _folder("pos_inbox", "Da elaborare"),
        ],
        "pos_inbox": [_file("pos2", "Export_Transazioni_Luglio_2026.xlsx")],
        "paypal": [
            _file("pp1", "2025-06-MSR.pdf"),
            _folder("paypal_inbox", "Da elaborare"),
            _folder("paypal_done", "Elaborate"),
        ],
        "paypal_inbox": [_file("pp2", "2025-07-CSR.pdf")],
        "paypal_done": [_file("pp_old", "2024-01-MSR.pdf")],
        "done": [_file("root_old", "estratto-archiviato.pdf")],
    })

    items, sources, _rimandati = _discover_work_items(service, "root")

    assert {(item["id"], item["route"]) for item in items} == {
        ("ec1", "bank"), ("pos1", "pos"), ("pos2", "pos"),
        ("fee", "pos"),
        ("pp1", "paypal"), ("pp2", "paypal"),
    }
    assert {source["path"] for source in sources} == {"BNL", "pos bpm", "Paypal"}
    assert all(item["id"] not in {"old", "root_old", "pp_old"} for item in items)


def test_recupero_archivio_elaborate_e_esplicito_e_non_confonde_l_inbox():
    service = _Service({
        "root": [
            _folder("inbox", "Da elaborare"),
            _folder("done", "Elaborate"),
        ],
        "inbox": [_file("new", "Estratto_BPM_Giugno_2026.csv")],
        "done": [_file("old", "Estratto_BPM_Maggio_2026.csv")],
    })

    items, _sources, _rimandati = _discover_work_items(
        service, "root", include_elaborate=True,
    )

    assert {item["id"] for item in items} == {"new", "old"}
    nuovo = next(item for item in items if item["id"] == "new")
    archivio = next(item for item in items if item["id"] == "old")
    assert nuovo["archive_recovery"] is False
    assert archivio["archive_recovery"] is True
    assert archivio["source_path"] == "Elaborate/Estratto_BPM_Maggio_2026.csv"


def test_piu_radici_da_env_e_registro_sono_deduplicate(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS", "root-a, root-b")
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_ID", "root-a")
    monkeypatch.setattr(settings, "DRIVE_CARTE_FOLDER_ID", "root-carte")
    monkeypatch.setattr(settings, "DRIVE_FOLDER_REGISTRY_JSON", json.dumps({"folders": [
        {"area": "estratti_conto_bnl", "folder_id": "root-c"},
        {"area": "nexi", "folder_id": "root-carte-registro"},
        {"area": "fatture", "folder_id": "ignore"},
    ]}))

    assert _folder_ids() == ["root-a", "root-b", "root-c", "root-carte", "root-carte-registro"]
    assert _nexi_folder_ids() == ["root-carte", "root-carte-registro"]


def test_radice_nexi_accetta_pdf_con_nomi_generici():
    service = _Service({
        "carte": [
            _file("n1", "Estratto_Conto gennaio.pdf"),
            _file("n2", "nexi febbraio.pdf"),
            _folder("done", "Elaborate"),
        ],
        "done": [_file("old", "dicembre.pdf")],
    })

    items, sources, _rimandati = _discover_work_items(
        service, "carte", initial_route="nexi")

    assert {(item["id"], item["route"]) for item in items} == {
        ("n1", "nexi"), ("n2", "nexi"),
    }
    assert sources == [{"id": "carte", "path": "Estratti conto"}]


def test_crea_ciclo_anche_per_fonte_riconosciuta_senza_file():
    service = _Service({
        "root": [_folder("bpm", "BPM")],
        "bpm": [],
    })

    items, sources, _rimandati = _discover_work_items(service, "root")

    assert items == []
    assert sources == [{"id": "bpm", "path": "BPM"}]


def test_da_elaborare_ha_priorita_sui_file_storici_diretti():
    items = [
        {"id": "storico", "source_path": "BPM/estratto-2024.pdf"},
        {"id": "inbox-b", "source_path": "BPM/Da elaborare/b.pdf"},
        {"id": "inbox-a", "source_path": "BNL/Da elaborare/a.pdf"},
    ]

    ordinati = sorted(items, key=_work_item_priority)

    assert [item["id"] for item in ordinati] == [
        "inbox-a", "inbox-b", "storico",
    ]


def test_l_arretrato_non_entra_nel_lavoro_ma_viene_contato(monkeypatch):
    """Cartella unica con dentro storico e anno in corso: passa solo il 2026,
    e i documenti fermi restano dichiarati invece di sparire in silenzio."""
    monkeypatch.setattr(settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 2026, raising=False)
    service = _Service({
        "root": [_folder("inbox", "Da elaborare")],
        "inbox": [
            _file("nuovo", "Export_Mensile_Giugno_2026.csv"),
            _file("vecchio", "EC-38949004-agosto 2024.pdf"),
            _file("senza_anno", "Estratto_Conto (7).pdf"),
        ],
    })

    items, _sources, rimandati = _discover_work_items(service, "root")

    assert [item["id"] for item in items] == ["nuovo", "senza_anno"]
    assert rimandati == ["EC-38949004-agosto 2024.pdf"]
