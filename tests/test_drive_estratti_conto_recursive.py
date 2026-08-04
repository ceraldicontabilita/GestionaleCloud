import json
import re

from app.config import settings
from app.services.drive_estratti_conto_ingest import _discover_work_items, _folder_ids


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


def test_scansione_ricorsiva_separa_banca_pos_e_ignora_archivi():
    service = _Service({
        "root": [_folder("bnl", "BNL"), _folder("pos", "pos bpm"), _folder("done", "Elaborate")],
        "bnl": [_file("ec1", "2019-Q4 Estratto BNL.pdf"), _folder("bnl_done", "Elaborate")],
        "bnl_done": [_file("old", "gia-elaborato.pdf")],
        "pos": [
            _file("pos1", "Export_Mensile_Giugno_2026.csv"),
            _file("fee", "Commissioni_Giugno_2026.xlsx"),
            _folder("pos_inbox", "Da elaborare"),
        ],
        "pos_inbox": [_file("pos2", "Export_Transazioni_Luglio_2026.xlsx")],
        "done": [_file("root_old", "estratto-archiviato.pdf")],
    })

    items, sources = _discover_work_items(service, "root")

    assert {(item["id"], item["route"]) for item in items} == {
        ("ec1", "bank"), ("pos1", "pos"), ("pos2", "pos"),
    }
    assert {source["path"] for source in sources} == {"BNL", "pos bpm"}
    assert all(item["id"] not in {"old", "fee", "root_old"} for item in items)


def test_piu_radici_da_env_e_registro_sono_deduplicate(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS", "root-a, root-b")
    monkeypatch.setattr(settings, "DRIVE_FOLDER_ESTRATTI_CONTO_IDS", None)
    monkeypatch.setattr(settings, "DRIVE_ESTRATTI_CONTO_FOLDER_IDS", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_ID", "root-a")
    monkeypatch.setattr(settings, "DRIVE_FOLDER_ESTRATTI_CONTO_ID", None)
    monkeypatch.setattr(settings, "DRIVE_ESTRATTI_CONTO_FOLDER_ID", None)
    monkeypatch.setattr(settings, "DRIVE_FOLDER_REGISTRY_JSON", json.dumps({"folders": [
        {"area": "estratti_conto_bnl", "folder_id": "root-c"},
        {"area": "fatture", "folder_id": "ignore"},
    ]}))

    assert _folder_ids() == ["root-a", "root-b", "root-c"]


def test_crea_ciclo_anche_per_fonte_riconosciuta_senza_file():
    service = _Service({
        "root": [_folder("bpm", "BPM")],
        "bpm": [],
    })

    items, sources = _discover_work_items(service, "root")

    assert items == []
    assert sources == [{"id": "bpm", "path": "BPM"}]
