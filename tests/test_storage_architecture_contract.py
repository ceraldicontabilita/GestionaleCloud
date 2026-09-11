"""Contratti architetturali della persistenza di GestionaleCloud.

Supabase e' il registro operativo di produzione. Google Sheets resta soltanto
un percorso transitorio di rollback/test e non deve diventare il default del
deploy.
"""
from pathlib import Path

import yaml

from app.config import Settings


def _render_env() -> dict[str, dict]:
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    service = next(item for item in blueprint["services"] if item["name"] == "GestionaleCloud")
    return {item["key"]: item for item in service.get("envVars", [])}


def test_render_production_uses_supabase_as_operational_backend():
    env = _render_env()
    assert env["DATA_BACKEND"]["value"] == "supabase"


def test_render_declares_all_supabase_runtime_secrets():
    env = _render_env()
    for key in (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_RUNTIME_SECRET",
    ):
        assert key in env
        assert env[key].get("sync") is False


def test_supabase_startup_accepts_complete_runtime_configuration(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="supabase",
        SECRET_KEY="x" * 64,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_RUNTIME_SECRET="runtime-secret-test-value-1234567890",
        CORS_ALLOWED_ORIGINS="",
    )
    cfg.validate_startup()


def test_supabase_startup_fails_closed_when_runtime_secret_is_missing(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="supabase",
        SECRET_KEY="x" * 64,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_RUNTIME_SECRET=None,
        CORS_ALLOWED_ORIGINS="",
    )
    try:
        cfg.validate_startup()
    except RuntimeError as exc:
        assert "SUPABASE_RUNTIME_SECRET" in str(exc)
    else:
        raise AssertionError("startup Supabase deve fallire senza runtime secret")


def test_sheets_requires_explicit_backend_selection_and_registry(monkeypatch):
    """Il percorso Sheets resta ammesso solo quando viene selezionato esplicitamente."""
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production",
        DATA_BACKEND="sheets",
        SECRET_KEY="x" * 64,
        GOOGLE_SHEETS_LEDGER_ID="rollback-ledger",
        CORS_ALLOWED_ORIGINS="",
    )
    cfg.validate_startup()
