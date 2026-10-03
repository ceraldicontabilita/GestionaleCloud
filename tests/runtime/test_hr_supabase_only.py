"""Guardrail: HR non deve riaprire un backend MongoDB alternativo."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_database_hr_e_supabase_only():
    source = (ROOT / "app/hr/database.py").read_text(encoding="utf-8")
    assert "AsyncIOMotorClient" not in source
    assert "HR_MONGO_URL" not in source
    assert 'backend = "mongo"' not in source


def test_config_hr_non_legge_o_scrive_segreti_su_mongo():
    source = (ROOT / "app/hr/config.py").read_text(encoding="utf-8")
    assert "MongoClient" not in source
    assert "HR_MONGO_URL" not in source
    assert "sistema_stato" not in source


def test_diagnostica_nomina_il_backend_reale():
    source = (ROOT / "app/hr/routers/diagnostica.py").read_text(encoding="utf-8")
    assert "Connessione MongoDB" not in source
    assert "HR_MONGO_URL" not in source
    assert "Connessione Supabase/Postgres" in source


def test_servizio_acconti_non_dipende_da_motor():
    source = (ROOT / "app/hr/services/acconti_auto_linker.py").read_text(encoding="utf-8")
    assert "motor.motor_asyncio" not in source
    assert "AsyncIOMotorDatabase" not in source
