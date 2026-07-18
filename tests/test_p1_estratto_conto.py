"""P1 §5.6 — Estratto conto: canonica MOVIMENTI = `estratto_conto_movimenti`
(unica sorgente riconciliazione/saldi); `estratti_conto` è il registro separato dei
DOCUMENTI caricati; le legacy `estratto_conto`/`bank_statements`/`movimenti_f24_banca`
non devono ricevere scritture dirette dal codice applicativo."""
import pathlib

from app.db_collections import (
    COLL_ESTRATTO_CONTO,
    COLL_ESTRATTI_CONTO_DOCUMENTI,
    COLL_ESTRATTO_CONTO_LEGACY,
    COLL_BANK_STATEMENTS,
)
from app.database import Collections

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def test_costanti_canoniche():
    assert COLL_ESTRATTO_CONTO == "estratto_conto_movimenti"
    assert COLL_ESTRATTI_CONTO_DOCUMENTI == "estratti_conto"
    # movimenti e registro documenti sono concetti distinti
    assert COLL_ESTRATTO_CONTO != COLL_ESTRATTI_CONTO_DOCUMENTI
    # l'alias inglese risolve alla canonica dei movimenti (non a "bank_statements")
    assert Collections.BANK_STATEMENTS == "estratto_conto_movimenti"


def _writers(coll: str) -> list:
    hits = []
    for p in APP.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for op in (".insert_one", ".insert_many", ".update_one",
                       ".update_many", ".replace_one", ".bulk_write"):
                if f'db["{coll}"]{op}' in line or f"db['{coll}']{op}" in line:
                    hits.append(f"{p.name}:{i}")
    return hits


def test_nessun_writer_su_legacy():
    for coll in (COLL_ESTRATTO_CONTO_LEGACY, COLL_BANK_STATEMENTS, "movimenti_f24_banca"):
        assert _writers(coll) == [], f"writer inatteso sulla legacy {coll}: {_writers(coll)}"
