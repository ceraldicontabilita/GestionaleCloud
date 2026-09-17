import json

from app.config import settings
from app.services.drive_folder_registry import get_public_catalog


def test_catalog_hides_folder_ids(monkeypatch):
    secret_id = "folder-id-that-must-not-leak"
    monkeypatch.setattr(settings, "DRIVE_FOLDER_REGISTRY_JSON", json.dumps({"folders": [
        {"area": "fatture", "label": "Fatture XML", "folder_id": secret_id},
        {"area": "assegni", "label": "Assegni", "folder_id": "another-id"},
    ]}))

    result = get_public_catalog()

    assert result["total"] == 2
    assert result["configured"] == 2
    assert result["automatic"] == 1
    assert result["folders"][0]["mode"] == "automatico"
    assert secret_id not in json.dumps(result)


def test_invalid_registry_is_empty(monkeypatch):
    monkeypatch.setattr(settings, "DRIVE_FOLDER_REGISTRY_JSON", "not-json")
    assert get_public_catalog() == {"folders": [], "total": 0, "configured": 0, "automatic": 0}
