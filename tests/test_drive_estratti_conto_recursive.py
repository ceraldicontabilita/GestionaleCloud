import json
import re

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

    items, sources = _discover_work_items(service, "root")

    assert {(item["id"], item["route"]) for item in items} == {
        ("ec1", "bank"), ("pos1", "pos"), ("pos2", "pos"),
        ("fee", "pos"),
        ("pp1", "paypal"), ("pp2", "paypal"),
    }
    assert {source["path"] for source in sources} == {"BNL", "pos bpm", "Paypal"}
    assert all(item["id"] not in {"old", "root_old", "pp_old"} for item in items)


def test_piu_radici_da_env_e_registro_sono_deduplicate(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS", "root-a, root-b")
    monkeypatch.setattr(settings, "DRIVE_FOLDER_ESTRATTI_CONTO_IDS", None)
    monkeypatch.setattr(settings, "DRIVE_ESTRATTI_CONTO_FOLDER_IDS", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_ID", "root-a")
    monkeypatch.setattr(settings, "DRIVE_FOLDER_ESTRATTI_CONTO_ID", None)
    monkeypatch.setattr(settings, "DRIVE_ESTRATTI_CONTO_FOLDER_ID", None)
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

    items, sources = _discover_work_items(service, "carte", initial_route="nexi")

    assert {(item["id"], item["route"]) for item in items} == {
        ("n1", "nexi"), ("n2", "nexi"),
    }
    assert sources == [{"id": "carte", "path": "Estratti conto"}]


def test_crea_ciclo_anche_per_fonte_riconosciuta_senza_file():
    service = _Service({
        "root": [_folder("bpm", "BPM")],
        "bpm": [],
    })

    items, sources = _discover_work_items(service, "root")

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
