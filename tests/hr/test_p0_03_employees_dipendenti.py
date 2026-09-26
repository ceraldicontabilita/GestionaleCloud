"""P0.3 — i verbali usano la collezione canonica `dipendenti`, non `employees`,
cosi' l'anagrafica e' la stessa che TFR e Prima Nota Salari leggono."""
from pathlib import Path

from app.database import Collections


def test_collections_employees_e_dipendenti():
    assert Collections.EMPLOYEES == "dipendenti"


def test_dettaglio_verbale_canonico_usa_dipendenti_per_driver():
    """Il requisito segue il comportamento, non il vecchio file duplicato."""
    src = Path("app/routers/verbali_noleggio.py").read_text(encoding="utf-8")
    assert "db.employees.find_one" not in src
    assert 'db["dipendenti"].find_one' in src
