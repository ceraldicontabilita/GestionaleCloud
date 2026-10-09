"""Fase 3 — i quattro stati del netto esistono e la guardia fallisce chiusa.

CLAUDE.md, «Personale», impone quattro stati e una regola sola:
**solo `NETTO_VERIFICATO_DA_CEDOLINO` alimenta Salari e bonifici**, e una
cella vuota vale nullo, mai zero. Nel codice esisteva un solo stato, e le sue
uniche due occorrenze stavano dentro una guardia che trattava lo stato
**assente** come verificato:

    status = str(row.get("status") or "NETTO_VERIFICATO_DA_CEDOLINO")

Su un dato che diventa un bonifico, l'assenza di prova non puo' valere come
prova.
"""
import asyncio

import pytest

from app.constants.stati_netto import (
    ERRORE_PARSER,
    MULTIPLE_NETS_DA_VERIFICARE,
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    NETTO_VERIFICATO_DA_CEDOLINO,
    STATI_NETTO,
    alimenta_salari,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# Gli stati esistono davvero
# ──────────────────────────────────────────────────────────────────────

def test_esistono_tutti_e_quattro_gli_stati():
    assert STATI_NETTO == (
        NETTO_VERIFICATO_DA_CEDOLINO,
        NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
        MULTIPLE_NETS_DA_VERIFICARE,
        ERRORE_PARSER,
    )


@pytest.mark.parametrize("stato", [
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    MULTIPLE_NETS_DA_VERIFICARE,
    ERRORE_PARSER,
    None,
    "",
    "   ",
    "qualcosa_di_inventato",
])
def test_solo_il_netto_verificato_alimenta_salari(stato):
    """Fail chiuso: assente, vuoto e sconosciuto non passano."""
    assert alimenta_salari(stato) is False


def test_il_netto_verificato_passa():
    assert alimenta_salari(NETTO_VERIFICATO_DA_CEDOLINO) is True
    assert alimenta_salari("netto_verificato_da_cedolino") is True


# ──────────────────────────────────────────────────────────────────────
# Il parser: nullo, mai zero
# ──────────────────────────────────────────────────────────────────────

def test_netto_illeggibile_e_nullo_non_zero():
    """Un netto che non si riesce a leggere deve restare distinguibile da
    uno zero vero: `0.0` li confondeva per sempre."""
    from app.hr.parsers.payslip_parser_v2 import PayslipParserMultiFormat

    parser = PayslipParserMultiFormat(pdf_content=b"")
    assert parser._extract_netto("una pagina senza alcun importo", "standard") is None


def test_netto_leggibile_torna_il_valore():
    from app.hr.parsers.payslip_parser_v2 import PayslipParserMultiFormat

    parser = PayslipParserMultiFormat(pdf_content=b"")
    assert parser._extract_netto("NETTO DEL MESE 1.234,56", "standard") == 1234.56


# ──────────────────────────────────────────────────────────────────────
# La guardia di Prima Nota Salari fallisce chiusa
# ──────────────────────────────────────────────────────────────────────

class _Coll:
    def __init__(self):
        self.inseriti = []

    def find(self, *a, **k):
        class _C:
            async def to_list(self_inner, n):
                return []
        return _C()

    async def find_one(self, *a, **k):
        return None

    async def insert_one(self, doc):
        self.inseriti.append(doc)

    async def insert_many(self, docs):
        self.inseriti.extend(docs)

    async def update_one(self, *a, **k):
        class _R:
            modified_count = 0
        return _R()


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, nome):
        return self.colls.setdefault(nome, _Coll())


def _riga(**extra):
    base = {
        "employee": "ZZZ Test Dipendente",
        "year": 2026,
        "month": 5,
        "net_amount": 1500.0,
        "source": "drive://test/zzz.pdf",
    }
    base.update(extra)
    return base


@pytest.mark.parametrize("status", [None, "", "   ", ERRORE_PARSER,
                                    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
                                    MULTIPLE_NETS_DA_VERIFICARE])
def test_una_riga_senza_netto_verificato_non_entra_in_prima_nota(status, monkeypatch):
    """Il caso che contava: `status` assente passava per verificato."""
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))

    riga = _riga() if status is None else _riga(status=status)
    if status is None:
        riga.pop("status", None)

    esito = _run(modulo.import_salari_verificati({"righe": [riga]}))

    assert esito["created"] == 0, f"status={status!r} non doveva creare nulla"
    assert esito["skipped"] == 1
    assert db["prima_nota_salari"].inseriti == []


def test_una_riga_verificata_entra_regolarmente(monkeypatch):
    """Il fail-closed non deve rompere il caso buono."""
    from app.routers.accounting import prima_nota_salari as modulo

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))

    esito = _run(modulo.import_salari_verificati(
        {"righe": [_riga(status=NETTO_VERIFICATO_DA_CEDOLINO)]}
    ))

    assert esito["created"] == 1
    assert esito["skipped"] == 0
