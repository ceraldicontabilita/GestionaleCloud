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
    }
    env.update(injected)
    script = '''
import json, os
import scripts.e2e_distruttivo_server
from app.services import postgres_diretto
from app.config import settings
print(json.dumps({
    "dsn": postgres_diretto.dsn(),
    "supabase": settings.SUPABASE_URL,
    "scheduler": settings.ENABLE_SCHEDULER,
    "external_keys": [k for k in json.loads(os.environ["E2E_INJECTED_KEYS"]) if k in os.environ and k != "ENABLE_SCHEDULER"],
}))
'''
    env["E2E_INJECTED_KEYS"] = json.dumps(list(injected))
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env,
                            text=True, capture_output=True, timeout=30, check=True)
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data == {"dsn": None, "supabase": None, "scheduler": False, "external_keys": []}
