import asyncio

from app.services.drive_fiscal_registry import FOLDER_MIME, _discover_sync, _is_under_target


class _Call:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class _Files:
    def __init__(self, items, metadata):
        self.items = items
        self.metadata = metadata

    def get(self, fileId, **kwargs):
        return _Call(self.metadata[fileId])

    def list(self, q, **kwargs):
        parent = q.split("'")[1]
        return _Call({"files": self.items.get(parent, [])})


class _Service:
    def __init__(self, items, metadata): self._files = _Files(items, metadata)
    def files(self): return self._files


def test_discovery_requires_exact_unique_folders():
    root = {"id": "root", "name": "Fiscale", "mimeType": FOLDER_MIME, "trashed": False}
    items = {
        "root": [{"id": "a", "name": "Avvisi bonari", "mimeType": FOLDER_MIME},
                 {"id": "sub", "name": "Archivio", "mimeType": FOLDER_MIME}],
        "sub": [{"id": "c", "name": "Cartelle esattoriali", "mimeType": FOLDER_MIME}],
        "a": [], "c": [],
    }
    service = _Service(items, {"root": root})
    _, results = _discover_sync(service, "root")
    entries = {item["area"]: item for item in results}
    assert entries["avvisi_bonari"]["folder_id"] == "a"
    assert entries["cartelle_esattoriali"]["folder_id"] == "c"
    assert entries["cartelle_esattoriali"]["path"].endswith("Archivio/Cartelle esattoriali")


def test_discovery_fails_closed_on_duplicate_name():
    root = {"id": "root", "name": "Fiscale", "mimeType": FOLDER_MIME, "trashed": False}
    items = {"root": [
        {"id": "a1", "name": "Avvisi bonari", "mimeType": FOLDER_MIME},
        {"id": "a2", "name": "AVVISI BONARI", "mimeType": FOLDER_MIME},
    ], "a1": [], "a2": []}
    _, results = _discover_sync(_Service(items, {"root": root}), "root")
    error = next(item for item in results if item["area"] == "avvisi_bonari")
    assert error == {"area": "avvisi_bonari", "matches": 2, "error": "cartella assente o ambigua"}


def test_nested_file_is_under_target():
    metadata = {
        "nested": {"id": "nested", "parents": ["target"], "trashed": False},
    }
    service = _Service({}, metadata)
    assert _is_under_target(service, {"parents": ["nested"]}, {"target"}) is True
