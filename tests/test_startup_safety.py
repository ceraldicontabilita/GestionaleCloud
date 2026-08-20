"""Contratti di sicurezza del bootstrap e dell'health check."""
import asyncio
import json

import pytest

from app.config import Settings
from app import database as database_module
from app.database import Database
from app.main import health_check
from app.services.auth_secret import initialize_auth_secret
from mongomock_motor import AsyncMongoMockClient


def test_cors_produzione_senza_origin_esplicito_e_chiuso():
    cfg = Settings(
        ENVIRONMENT="production",
        CORS_ALLOWED_ORIGINS="",
        CORS_ORIGINS="*",
        ALLOWED_ORIGINS="*",
        FRONTEND_URL=None,
        ALLOW_CREDENTIALS=True,
    )

    assert cfg.get_cors_origins() == []


def test_fail_fast_accetta_fallback_cors_same_origin(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="mongodb",
        SECRET_KEY="x" * 64,
        MONGODB_ATLAS_URI="mongodb://example.invalid",
        CORS_ALLOWED_ORIGINS="",
        ALLOW_CREDENTIALS=True,
    )

    cfg.validate_startup()


def test_fail_fast_rifiuta_cors_wildcard_con_credenziali(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="mongodb",
        SECRET_KEY="x" * 64,
        MONGODB_ATLAS_URI="mongodb://example.invalid",
        CORS_ALLOWED_ORIGINS="*",
        ALLOW_CREDENTIALS=True,
    )

    with pytest.raises(RuntimeError, match="CORS wildcard"):
        cfg.validate_startup()


def test_fail_fast_sheets_non_usa_mongo_come_fallback(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="sheets",
        SECRET_KEY="x" * 64,
        GOOGLE_SHEETS_LEDGER_ID=None,
        GOOGLE_SHEETS_LEDGER_FOLDER_ID=None,
        MONGODB_ATLAS_URI="mongodb://example.invalid",
        CORS_ALLOWED_ORIGINS="",
    )

    with pytest.raises(RuntimeError, match="MongoDB non e' un fallback"):
        cfg.validate_startup()


def test_fail_fast_sheets_accetta_cartella_registro_esplicita(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="sheets",
        SECRET_KEY="x" * 64,
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


def test_riparazioni_dati_startup_disabilitate_per_default():
    cfg = Settings()

    assert cfg.DATA_BACKEND == "sheets"
    assert cfg.RUN_STARTUP_DATA_REPAIRS is False
    assert cfg.RUN_STARTUP_INDEX_MIGRATIONS is False
    assert cfg.RUN_STARTUP_SEED_DATA is False


def test_settings_non_fa_io_e_bootstrap_secret_e_condiviso():
    cfg_a = Settings(SECRET_KEY=None, MONGO_URL="mongomock://local")
    cfg_b = Settings(SECRET_KEY=None, MONGO_URL="mongomock://local")
    assert cfg_a.auth_secret_source == "ephemeral"
    assert cfg_b.auth_secret_source == "ephemeral"

    db = AsyncMongoMockClient()["auth_bootstrap_test"]
    assert asyncio.run(initialize_auth_secret(db, cfg_a)) == "mongodb"
    assert asyncio.run(initialize_auth_secret(db, cfg_b)) == "mongodb"
    assert cfg_a.SECRET_KEY == cfg_b.SECRET_KEY
    assert cfg_a.auth_secret_source == "mongodb"


def test_secret_esplicito_non_viene_sovrascritto_da_mongo():
    explicit = "x" * 64
    cfg = Settings(SECRET_KEY=explicit)
    db = AsyncMongoMockClient()["auth_explicit_test"]
    asyncio.run(db["sistema_stato"].insert_one({
        "_id": "auth_secret", "chiave": "auth_secret", "valore": "y" * 64,
    }))

    assert asyncio.run(initialize_auth_secret(db, cfg)) == "configured"
    assert cfg.SECRET_KEY == explicit


def test_cutover_sheets_rimuove_credenziali_mongo_dal_processo(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://example.invalid")
    monkeypatch.setenv("MONGODB_ATLAS_URI", "mongodb://secret.invalid")
    monkeypatch.setattr(database_module.settings, "MONGO_URL", "mongodb://example.invalid")
    monkeypatch.setattr(database_module.settings, "MONGODB_ATLAS_URI", "mongodb://secret.invalid")

    database_module.scrub_mongo_runtime_configuration()

    assert "MONGO_URL" not in database_module.os.environ
    assert "MONGODB_ATLAS_URI" not in database_module.os.environ
    assert database_module.settings.MONGO_URL == ""
    assert database_module.settings.MONGODB_ATLAS_URI is None
