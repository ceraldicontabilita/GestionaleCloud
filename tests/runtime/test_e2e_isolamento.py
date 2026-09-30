"""Il server distruttivo non deve ereditare connessioni cloud reali."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_e2e_non_puo_usare_connessioni_esterne_ereditate():
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    injected = {
        "SUPABASE_URL": "https://production.invalid",
        "SUPABASE_RUNTIME_SECRET": "production-test-placeholder",
        "HR_SUPABASE_DB_URL": "postgresql://user:fake@production.invalid/db",
        "APPDIPENDENTI_DB_URL": "postgresql://user:fake@production.invalid/db",
        "MENU_SUPABASE_KEY": "production-test-placeholder",
        "LOTTI_INTEGRATION_KEY": "production-test-placeholder",
        "GOOGLE_DRIVE_SA_JSON": "production-test-placeholder",
        "REACT_APP_BACKEND_URL": "https://production.invalid",
        "ENABLE_SCHEDULER": "true",
        "MONGO_URL": "mongodb://production.invalid/fixture",
        "JWT_SECRET": "legacy-production-test-placeholder",
        "GEMINI_API_KEY": "production-test-placeholder",
    }
    env.update(injected)
    script = '''
import json, os
from unittest.mock import patch
client_esterni_chiamati = []
def esterno_vietato(*args, **kwargs):
    client_esterni_chiamati.append(True)
    raise AssertionError("client esterno chiamato dal collaudo")
with patch("pymongo.MongoClient", esterno_vietato):
    import scripts.e2e_distruttivo_server
    import app.hr.config
from app.services import postgres_diretto
from app.config import settings
print(json.dumps({
    "dsn": postgres_diretto.dsn(),
    "supabase": settings.SUPABASE_URL,
    "scheduler": settings.ENABLE_SCHEDULER,
    "client_esterni_chiamati": len(client_esterni_chiamati),
    "external_keys": [k for k in json.loads(os.environ["E2E_INJECTED_KEYS"]) if k in os.environ and k != "ENABLE_SCHEDULER"],
}))
'''
    env["E2E_INJECTED_KEYS"] = json.dumps(list(injected))
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env,
                            text=True, capture_output=True, timeout=30, check=True)
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data == {"dsn": None, "supabase": None, "scheduler": False,
                    "external_keys": [], "client_esterni_chiamati": 0}


def test_ambiente_test_esclude_dotenv_e_file_segreti(tmp_path, monkeypatch):
    from app.config import Settings

    dotenv = tmp_path / ".env"
    dotenv.write_text("SUPABASE_URL=https://dotenv.invalid\nSUPABASE_RUNTIME_SECRET=fixture-secret\n")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "SUPABASE_URL").write_text("https://secrets.invalid")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_RUNTIME_SECRET", raising=False)
    settings = Settings(_env_file=dotenv, _secrets_dir=secrets)
    assert settings.SUPABASE_URL is None
    assert settings.SUPABASE_RUNTIME_SECRET is None
    # Lo sviluppo ordinario continua a leggere il suo file configurato.
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert Settings(_env_file=dotenv).SUPABASE_URL == "https://dotenv.invalid"


def test_runner_rimuove_alias_legacy_prima_di_importare_app():
    from scripts.collaudo_isolato import ambiente_isolato

    env = ambiente_isolato({
        "MONGO_URL": "mongodb://fixture.invalid", "JWT_SECRET": "fixture",
        "GEMINI_API_KEY": "fixture", "APPDIPENDENTI_DB_URL": "postgresql://fixture.invalid",
        "GESTIONALECLOUD_API_URL": "https://fixture.invalid", "PORT": "8788",
    })
    assert env["PORT"] == "8788"
    assert env["ENVIRONMENT"] == "test"
    assert not set(env).intersection({"MONGO_URL", "JWT_SECRET", "GEMINI_API_KEY",
                                     "APPDIPENDENTI_DB_URL", "GESTIONALECLOUD_API_URL"})
