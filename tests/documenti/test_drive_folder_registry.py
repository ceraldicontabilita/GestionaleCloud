"""Il catalogo Drive e' la sola cartella unica, e non espone mai l'ID."""
import json

from app.services import drive_cartella_unica as cu
from app.services.drive_folder_registry import get_configured_entries, get_public_catalog


def test_catalogo_e_la_cartella_unica_senza_id(monkeypatch):
    secret_id = "folder-id-that-must-not-leak"
    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", secret_id)

    result = get_public_catalog()

    assert result["total"] == 1 and result["configured"] == 1 and result["automatic"] == 1
    assert result["folders"][0]["area"] == "dati_societa"
    assert result["folders"][0]["mode"] == "automatico"
    assert secret_id not in json.dumps(result)
    assert get_configured_entries() == [
        {"area": "dati_societa", "label": "DATI SOCIETA CERALDI", "folder_id": secret_id},
    ]


def test_senza_cartella_unica_il_catalogo_dice_da_configurare(monkeypatch):
    monkeypatch.delenv("GOOGLE_DRIVE_DATI_FOLDER_ID", raising=False)
    assert cu.radice() is None
    result = get_public_catalog()
    assert result["configured"] == 0
    assert result["folders"][0]["status"] == "da_configurare"
    assert get_configured_entries() == []
