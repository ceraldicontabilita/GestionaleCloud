"""Un movimento bancario puo' produrre una sola riga di Prima Nota.

Fino al 19/09/2026 due motori scrivevano in `prima_nota_banca` partendo
dall'estratto conto: `proiezione_bancaria.py` (`proiezione_semantica_ec`, 308
righe, 352.469,57 EUR) e un trigger PL/pgSQL che viveva solo dentro Supabase
(`estratto_conto_hub`, 82 righe, 129,50 EUR).

Non si sovrapponevano — verificato: zero movimenti con due righe — perche'
condividevano la chiave `estratto_conto_id`. Ma due implementazioni delle
stesse regole, una in Python e una in SQL, possono divergere senza che nessuno
se ne accorga, e il costo non e' un errore visibile: e' un'uscita contata due
volte nei saldi.
"""
import asyncio

from app.services.collaudo_invarianti import (
    CHECKS,
    check_movimento_ec_proiettato_due_volte,
)


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Cursore:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield dict(d)
        return gen()


class _Db:
    def __init__(self, righe):
        self._righe = righe
        self.letture = 0

    def __getitem__(self, nome):
        db = self

        class _Coll:
            def find(self, query=None, proj=None):
                db.letture += 1
                return _Cursore(db._righe)
        return _Coll()


def _riga(ec_id, source, importo=10.0, rid=None):
    return {"id": rid or f"pn-{source}-{ec_id}", "source": source,
            "importo": importo, "estratto_conto_id": ec_id,
            "movimento_estratto_conto_id": ec_id}


def test_le_due_fonti_sullo_stesso_movimento_sono_una_violazione():
    """Il caso che si vuole impedire: Python e SQL scrivono lo stesso fatto."""
    db = _Db([
        _riga("ec-1", "proiezione_semantica_ec", 1.0),
        _riga("ec-1", "estratto_conto_hub", 1.0),
    ])

    esito = _run(check_movimento_ec_proiettato_due_volte(db))

    assert esito["violazioni"] == 1
    assert esito["esempi"][0]["movimento_ec"] == "ec-1"
    assert esito["esempi"][0]["fonti"] == [
        "estratto_conto_hub", "proiezione_semantica_ec"]
    assert esito["esempi"][0]["importo"] == 2.0, "l'importo doppio va detto"


def test_un_movimento_per_riga_non_e_una_violazione():
    db = _Db([
        _riga("ec-1", "proiezione_semantica_ec"),
        _riga("ec-2", "estratto_conto_hub"),
    ])

    assert _run(check_movimento_ec_proiettato_due_volte(db))["violazioni"] == 0


def test_due_righe_della_stessa_fonte_contano_lo_stesso():
    """Anche un solo motore che sbaglia idempotenza raddoppia il saldo."""
    db = _Db([
        _riga("ec-1", "proiezione_semantica_ec", 5.0, rid="a"),
        _riga("ec-1", "proiezione_semantica_ec", 5.0, rid="b"),
    ])

    esito = _run(check_movimento_ec_proiettato_due_volte(db))

    assert esito["violazioni"] == 1
    assert esito["esempi"][0]["fonti"] == ["proiezione_semantica_ec"]


def test_le_righe_senza_legame_con_l_estratto_conto_restano_fuori():
    """Uno stipendio o un trasferimento POS non nascono da un movimento EC."""
    db = _Db([
        {"id": "x", "source": "trasferimento_pos", "importo": 100.0},
        {"id": "y", "source": "legacy_versamenti", "importo": 200.0,
         "estratto_conto_id": ""},
    ])

    assert _run(check_movimento_ec_proiettato_due_volte(db))["violazioni"] == 0


def test_le_due_chiavi_indicano_lo_stesso_movimento():
    """`estratto_conto_id` e `movimento_estratto_conto_id` sono sinonimi:
    leggerne una sola lascerebbe passare meta' dei doppioni."""
    db = _Db([
        {"id": "a", "source": "uno", "importo": 3.0, "estratto_conto_id": "ec-9"},
        {"id": "b", "source": "due", "importo": 3.0,
         "movimento_estratto_conto_id": "ec-9"},
    ])

    assert _run(check_movimento_ec_proiettato_due_volte(db))["violazioni"] == 1


def test_il_check_e_registrato_nel_collaudo():
    assert check_movimento_ec_proiettato_due_volte in CHECKS


def test_legge_la_collezione_una_volta_sola():
    db = _Db([_riga(f"ec-{i}", "proiezione_semantica_ec") for i in range(40)])

    _run(check_movimento_ec_proiettato_due_volte(db))

    assert db.letture == 1
