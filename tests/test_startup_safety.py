"""Contratti di sicurezza del bootstrap Drive/Sheets e dell'health check."""
import asyncio
import json

import pytest

from app.config import Settings
from app.database import Database
from app.main import health_check
from app.services.auth_secret import initialize_auth_secret
from app.services.sheets_document_store import MemorySheetsClient


def test_cors_produzione_senza_origin_esplicito_e_chiuso():
    cfg = Settings(
        ENVIRONMENT="production", CORS_ALLOWED_ORIGINS="",
        CORS_ORIGINS="*", ALLOWED_ORIGINS="*", FRONTEND_URL=None,
        ALLOW_CREDENTIALS=True,
    )
    assert cfg.get_cors_origins() == []


def test_fail_fast_accetta_fallback_cors_same_origin(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        GOOGLE_SHEETS_LEDGER_ID="sheet-1", CORS_ALLOWED_ORIGINS="",
        ALLOW_CREDENTIALS=True,
    )
    cfg.validate_startup()


def test_fail_fast_rifiuta_cors_wildcard_con_credenziali(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        GOOGLE_SHEETS_LEDGER_ID="sheet-1", CORS_ALLOWED_ORIGINS="*",
        ALLOW_CREDENTIALS=True,
    )
    with pytest.raises(RuntimeError, match="CORS wildcard"):
        cfg.validate_startup()


def test_fail_fast_richiede_il_registro_sheets(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        GOOGLE_SHEETS_LEDGER_ID=None,
        GOOGLE_SHEETS_LEDGER_FOLDER_ID=None, CORS_ALLOWED_ORIGINS="",
    )
    with pytest.raises(RuntimeError, match="GOOGLE_SHEETS_LEDGER_ID"):
        cfg.validate_startup()


def test_fail_fast_accetta_cartella_registro_esplicita(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        GOOGLE_SHEETS_LEDGER_ID=None,
        GOOGLE_SHEETS_LEDGER_FOLDER_ID="drive-root-1",
        CORS_ALLOWED_ORIGINS="",
    )
    cfg.validate_startup()


def test_health_check_non_dichiara_healthy_senza_database(monkeypatch):
    monkeypatch.setattr(Database, "db", None)
    response = asyncio.run(health_check())
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "disconnected"


def test_health_check_verifica_idratazione_sheets(monkeypatch):
    database = MemorySheetsClient()["health"]
    database.hydration_result = {
        "spreadsheet_id": "SHEET-1",
        "fogli": [{"valide": 2920, "numero_errori": 0}],
    }
    monkeypatch.setattr(Database, "db", database)
    response = asyncio.run(health_check())
    assert response["status"] == "healthy"
    assert response["database"] == "connected"
    assert response["storage"] == "drive_sheets"
    assert response["hydrated_rows"] == 2920
    assert response["hydration_errors"] == 0
    assert response["salari_sync"] == "not_started"


def test_health_check_segnala_righe_sheets_escluse_senza_nascondere_i_dati(monkeypatch):
    database = MemorySheetsClient()["health_degraded"]
    database.hydration_result = {
        "spreadsheet_id": "SHEET-1",
        "fogli": [{"valide": 100, "numero_errori": 2}],
    }
    monkeypatch.setattr(Database, "db", database)

    response = asyncio.run(health_check())

    assert response["status"] == "degraded"
    assert response["database"] == "connected"
    assert response["hydrated_rows"] == 100
    assert response["hydration_errors"] == 2


def test_riparazioni_dati_startup_disabilitate_per_default():
    cfg = Settings()
    assert cfg.SHEETS_REGISTRY_NAME == "GestionaleCloud"
    assert cfg.RUN_STARTUP_DATA_REPAIRS is False
    assert cfg.RUN_STARTUP_INDEX_MIGRATIONS is False
    assert cfg.RUN_STARTUP_SEED_DATA is False


def test_settings_non_fa_io_e_bootstrap_secret_e_condiviso():
    cfg_a = Settings(SECRET_KEY=None)
    cfg_b = Settings(SECRET_KEY=None)
    assert cfg_a.auth_secret_source == "ephemeral"
    assert cfg_b.auth_secret_source == "ephemeral"
    db = MemorySheetsClient()["auth_bootstrap_test"]
    assert asyncio.run(initialize_auth_secret(db, cfg_a)) == "sheets"
    assert asyncio.run(initialize_auth_secret(db, cfg_b)) == "sheets"
    assert cfg_a.SECRET_KEY == cfg_b.SECRET_KEY
    assert cfg_a.auth_secret_source == "sheets"


def test_secret_esplicito_non_viene_sovrascritto_da_sheets():
    explicit = "x" * 64
    cfg = Settings(SECRET_KEY=explicit)
    db = MemorySheetsClient()["auth_explicit_test"]
    asyncio.run(db["sistema_stato"].insert_one({
        "_id": "auth_secret", "chiave": "auth_secret", "valore": "y" * 64,
    }))
    assert asyncio.run(initialize_auth_secret(db, cfg)) == "configured"
    assert cfg.SECRET_KEY == explicit


def test_runtime_non_ripiega_se_hydrate_fallisce(monkeypatch):
    class BrokenSheetsRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        async def hydrate(self):
            raise RuntimeError("registro Sheets non disponibile")

    monkeypatch.setattr(
        "app.services.sheets_runtime_database.SheetsRuntimeDatabase",
        BrokenSheetsRuntime,
    )
    monkeypatch.setattr(Database, "client", None)
    monkeypatch.setattr(Database, "db", None)
    with pytest.raises(RuntimeError, match="registro Sheets non disponibile"):
        asyncio.run(Database.connect_db())
    assert Database.client is None
    assert Database.db is None
