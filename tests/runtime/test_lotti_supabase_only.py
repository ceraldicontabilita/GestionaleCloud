"""Guardrail: Lotti non deve ripiegare su un archivio volatile nel runtime."""

import os
import subprocess
import sys


def test_lotti_senza_supabase_fallisce_chiuso():
    env = dict(os.environ)
    for nome in ("LOTTI_SUPABASE_URL", "LOTTI_SUPABASE_ANON_KEY", "LOTTI_DB_SECRET", "LOTTI_TEST_MEMORY"):
        env.pop(nome, None)
    esito = subprocess.run(
        [sys.executable, "-c", "import app.lotti.db"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert esito.returncode != 0
    assert "fallback non persistente" in (esito.stderr + esito.stdout)


def test_mock_lotti_richiede_flag_esplicito_della_suite():
    source = open("app/lotti/db.py", encoding="utf-8").read()
    assert 'os.environ.get("LOTTI_TEST_MEMORY") == "1"' in source
    assert 'STORAGE = "memoria"' in source
