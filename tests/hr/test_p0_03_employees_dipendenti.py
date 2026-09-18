"""P0.3 — Libro Unico e verbali devono usare la collezione canonica `dipendenti`,
non `employees`, così l'anagrafica creata dall'import buste paga è la stessa che
TFR/Prima Nota Salari leggono."""
from pathlib import Path

from app.database import Collections


def test_collections_employees_e_dipendenti():
    assert Collections.EMPLOYEES == "dipendenti"


def test_libro_unico_non_scrive_piu_su_employees():
    src = Path("app/routers/libro_unico_parser.py").read_text(encoding="utf-8")
    assert "db.employees.update_one" not in src
    assert "db[Collections.EMPLOYEES].update_one" in src


def test_verbali_api_usa_dipendenti_per_driver():
    src = Path("app/routers/verbali_noleggio_api.py").read_text(encoding="utf-8")
    assert "db.employees.find_one" not in src
    assert 'db["dipendenti"].find_one' in src
