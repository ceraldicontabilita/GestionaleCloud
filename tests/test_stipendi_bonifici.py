"""Richiesta utente 18/07/2026: quando l'estratto conto contiene un
bonifico "FAVORE <nome dipendente>", il pagamento va associato in
automatico alla riga stipendio pendente del dipendente. Le commissioni
COMM.SU BONIFICI e i beneficiari non-dipendenti (fornitori, distinte
cumulative) non devono mai essere associati."""
import asyncio
import re

import pytest

from app.services.stipendi_bonifici import (
    associa_bonifici_stipendi,
    estrai_nome_favore,
    riconciliazione_salario_verificata,
)


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self._docs


class _Coll:
    def __init__(self, docs):
        self.docs = docs
        self.updates = []

    def _match(self, d, query):
        for key, cond in query.items():
            if key == "$or":
                if not any(self._match(d, sub) for sub in cond):
                    return False
                continue
            v = d.get(key)
            if isinstance(cond, dict):
                if "$ne" in cond and v == cond["$ne"]:
                    return False
                if "$lt" in cond and not (v is not None and v < cond["$lt"]):
                    return False
                if "$regex" in cond and not re.search(
                    cond["$regex"], str(v or ""), re.I if cond.get("$options") == "i" else 0
                ):
                    return False
            elif v != cond:
                return False
        return True

    def find(self, query=None, *a, **k):
        return _Cursor([dict(d) for d in self.docs if self._match(d, query or {})])

    async def find_one(self, query=None, *a, **k):
        return next((dict(d) for d in self.docs if self._match(d, query or {})), None)

    async def update_one(self, filtro, update):
        self.updates.append((filtro, update))
        for d in self.docs:
            if all(d.get(k) == v for k, v in filtro.items()):
                for k, v in update.get("$set", {}).items():
                    d[k] = v


class _Db:
    def __init__(self, salari, movimenti, dipendenti=None):
        self.salari = _Coll(salari)
        self.movimenti = _Coll(movimenti)
        self.cedolini = _Coll([])
        self.dipendenti = _Coll(dipendenti or [])

    def __getitem__(self, name):
        return {"prima_nota_salari": self.salari,
                "estratto_conto_movimenti": self.movimenti,
                "cedolini": self.cedolini,
                "dipendenti": self.dipendenti}[name]


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_estrai_nome_favore():
    assert estrai_nome_favore(
        "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B39331331/90553586 "
        "FAVORE Lesina Angela - ADD.TOT - lesina Angela") == "Lesina Angela"
    # le commissioni non sono il pagamento
    assert estrai_nome_favore(
        "COMM.SU BONIFICI - VS.DISP. RIF. MB0B/90553586 FAVORE Lesina Angela - ADD.SPE") is None
    assert estrai_nome_favore("INCAS. TRAMITE P.O.S - NUMIA") is None


def test_associa_bonifico_per_nome_e_importo():
    db = _Db(
        salari=[{"id": "S1", "dipendente": "POCCI SALVATORE", "anno": 2026, "mese": 3,
                 "importo_busta": 530.0, "riconciliato": False},
                {"id": "S2", "dipendente": "VESPA VINCENZO", "anno": 2026, "mese": 3,
                 "importo_busta": 1461.0, "riconciliato": False}],
        movimenti=[
            # formato reale post-import: importo ASSOLUTO + tipo "uscita",
            # descrizione in descrizione_originale
            {"id": "M1", "data": "2026-04-03", "importo": 530.0, "tipo": "uscita",
             "descrizione_originale": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. X FAVORE Pocci Salvatore - ADD.TOT"},
            {"id": "M2", "data": "2026-04-03", "importo": 600.0, "tipo": "uscita",
             "descrizione_originale": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. X FAVORE Dolciaria Acquaviva S.p.A. NOTPROVIDE - ADD.TOT"},
            # un'ENTRATA con "FAVORE" nel testo non è mai un pagamento stipendio
            {"id": "M3", "data": "2026-04-03", "importo": 530.0, "tipo": "entrata",
             "descrizione_originale": "STORNO FAVORE Pocci Salvatore"},
        ])
    r = _run(associa_bonifici_stipendi(db))
    assert r["bonifici_associati"] == 1
    assert r["righe_stipendio_completate"] == 1
    mov = db.movimenti.docs[0]
    assert mov["riconciliato"] is True and mov["stipendio_id"] == "S1"
    assert mov["categoria"] == "Stipendi"
    riga = db.salari.docs[0]
    assert riga["riconciliato"] is True and riga["importo_bonifico"] == 530.0
    # il fornitore Dolciaria non viene mai toccato
    assert not db.movimenti.docs[1].get("riconciliato")


def test_anagrafica_associa_movimento_senza_parole_stipendio_o_favore():
    db = _Db(
        salari=[{
            "id": "S1", "dipendente_id": "D1", "dipendente": "CERALDI VALERIO",
            "anno": 2026, "mese": 7, "importo_busta": 1400.0,
            "riconciliato": False,
        }],
        movimenti=[{
            "id": "M1", "data": "2026-08-07", "importo": -1400.0,
            "descrizione_originale": (
                "VOSTRA DISPOSIZIONE RIF. 90731633 CERALDI VALERIO "
                "CRLVLR88H14F839O COMPETENZE"
            ),
        }],
        dipendenti=[{
            "id": "D1", "nome": "Valerio", "cognome": "Ceraldi",
            "codice_fiscale": "CRLVLR88H14F839O",
        }],
    )
    result = _run(associa_bonifici_stipendi(db))
    assert result["bonifici_associati"] == 1
    assert db.movimenti.docs[0]["stipendio_id"] == "S1"
    assert db.movimenti.docs[0]["dipendente_id"] == "D1"
    assert db.salari.docs[0]["riconciliato"] is True


def test_anagrafica_non_diventa_ambigua_se_salario_storico_non_ha_dipendente_id():
    db = _Db(
        salari=[{
            "id": "S1", "dipendente": "CERALDI VALERIO",
            "anno": 2026, "mese": 7, "importo_busta": 1400.0,
            "riconciliato": False,
        }],
        movimenti=[{
            "id": "M1", "data": "2026-08-07", "importo": -1400.0,
            "descrizione": "VOSTRA DISPOSIZIONE CERALDI VALERIO COMPETENZE",
        }],
        dipendenti=[{
            "id": "D1", "nome_completo": "Valerio Ceraldi",
            "codice_fiscale": "CRLVLR88H14F839O",
        }],
    )

    result = _run(associa_bonifici_stipendi(db))

    assert result["bonifici_associati"] == 1
    assert db.movimenti.docs[0]["dipendente_id"] == "D1"
    assert db.salari.docs[0]["riconciliato"] is True


def test_id_anagrafico_impedisce_associazione_a_omonimo_diverso():
    db = _Db(
        salari=[
            {
                "id": "S1", "dipendente_id": "D1", "dipendente": "MARIO ROSSI",
                "anno": 2026, "mese": 7, "importo_busta": 1200.0,
                "riconciliato": False,
            },
            {
                "id": "S2", "dipendente_id": "D2", "dipendente": "MARIO ROSSI",
                "anno": 2026, "mese": 7, "importo_busta": 1200.0,
                "riconciliato": False,
            },
        ],
        movimenti=[{
            "id": "M1", "data": "2026-08-07", "importo": -1200.0,
            "descrizione": "VS.DISP. RSSMRA80A01F839X MARIO ROSSI COMPETENZE",
        }],
        dipendenti=[
            {
                "id": "D1", "nome_completo": "Mario Rossi",
                "codice_fiscale": "RSSMRA80A01F839X",
            },
            {
                "id": "D2", "nome_completo": "Mario Rossi",
                "codice_fiscale": "RSSMRA81A01F839Y",
            },
        ],
    )

    result = _run(associa_bonifici_stipendi(db))

    assert result["bonifici_associati"] == 1
    assert db.movimenti.docs[0]["stipendio_id"] == "S1"
    assert db.salari.docs[0]["riconciliato"] is True
    assert db.salari.docs[1]["riconciliato"] is False


def test_acconto_viene_associato_ma_non_chiude_la_busta():
    db = _Db(
        salari=[{"id": "S1", "dipendente": "CAROTENUTO ANTONELLA", "anno": 2026, "mese": 3,
                 "importo_busta": 1047.0, "riconciliato": False}],
        movimenti=[{"id": "M1", "data": "2026-04-02", "importo": -1000.0,
                    "descrizione": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. X FAVORE Carotenuto Antonella - ADD.TOT - Carotenuto Antonella"}])
    r = _run(associa_bonifici_stipendi(db))
    assert r["bonifici_associati"] == 1
    assert r["righe_stipendio_completate"] == 0
    riga = db.salari.docs[0]
    assert riga.get("riconciliato") is not True
    assert riga.get("importo_bonifico") == 1000.0
    assert riga.get("saldo") == 47.0
    assert db.movimenti.docs[0].get("riconciliato") is True


def test_due_bonifici_acconto_e_saldo_chiudono_una_sola_busta():
    db = _Db(
        salari=[{"id": "S1", "dipendente": "VESPA VINCENZO", "anno": 2026,
                 "mese": 3, "importo_busta": 1430.0, "riconciliato": False}],
        movimenti=[
            {"id": "M1", "data": "2026-04-02", "importo": -1000.0,
             "descrizione": "BONIFICO STIPENDIO FAVORE VESPA VINCENZO"},
            {"id": "M2", "data": "2026-04-09", "importo": -430.0,
             "descrizione": "BONIFICO STIPENDIO FAVORE VESPA VINCENZO"},
        ],
    )
    r = _run(associa_bonifici_stipendi(db))
    assert r["bonifici_associati"] == 2
    assert r["righe_stipendio_completate"] == 1
    assert db.salari.docs[0]["importo_bonifico"] == 1430.0
    assert db.salari.docs[0]["saldo"] == 0.0
    assert db.salari.docs[0]["riconciliato"] is True
    assert all(m.get("riconciliato") is True for m in db.movimenti.docs)


def test_busta_zero_non_si_completa_solo_col_nome():
    """Senza importo busta manca una delle due prove richieste."""
    db = _Db(
        salari=[{"id": "S1", "dipendente": "LESINA ANGELA", "anno": 2026, "mese": 4,
                 "importo_busta": 0, "riconciliato": False}],
        movimenti=[{"id": "M1", "data": "2026-04-02", "importo": -1000.0,
                    "descrizione": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. X FAVORE Lesina Angela - ADD.TOT - lesina Angela"}])
    r = _run(associa_bonifici_stipendi(db))
    assert r["bonifici_associati"] == 0
    assert db.salari.docs[0].get("riconciliato") is not True
    assert not db.salari.docs[0].get("importo_bonifico")


def test_stesso_importo_ma_nome_diverso_non_associa():
    db = _Db(
        salari=[{"id": "S1", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
                 "importo_busta": 1200.0, "riconciliato": False}],
        movimenti=[{"id": "M1", "data": "2026-04-02", "importo": -1200.0,
                    "descrizione": "BONIFICO STIPENDIO FAVORE BIANCHI LUCA - MARZO 2026"}],
    )
    r = _run(associa_bonifici_stipendi(db))
    assert r["bonifici_associati"] == 0
    assert db.movimenti.docs[0].get("riconciliato") is not True


def test_stesso_nome_e_importo_su_due_mesi_usa_finestra_data():
    db = _Db(
        salari=[
            {"id": "MAR", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
             "importo_busta": 1200.0, "riconciliato": False},
            {"id": "APR", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 4,
             "importo_busta": 1200.0, "riconciliato": False},
        ],
        movimenti=[{"id": "M1", "data": "2026-04-02", "importo": -1200.0,
                    "descrizione": "BONIFICO STIPENDIO FAVORE ROSSI MARIO"}],
    )
    r = _run(associa_bonifici_stipendi(db))
    assert r["bonifici_associati"] == 1
    assert db.movimenti.docs[0]["stipendio_id"] == "MAR"
    assert db.salari.docs[0]["riconciliato"] is True
    assert db.salari.docs[1].get("riconciliato") is not True


def test_stipendio_id_singolo_limita_la_ricerca():
    db = _Db(
        salari=[{"id": "S1", "dipendente": "MUROLO MARIO", "anno": 2026, "mese": 3,
                 "importo_busta": 604.0, "riconciliato": False},
                {"id": "S2", "dipendente": "RUSSO CARMINE", "anno": 2026, "mese": 3,
                 "importo_busta": 900.0, "riconciliato": False}],
        movimenti=[
            {"id": "M1", "data": "2026-04-03", "importo": -604.0,
             "descrizione": "VS.DISP. RIF. X FAVORE Murolo Mario - ADD.TOT"},
            {"id": "M2", "data": "2026-04-03", "importo": -900.0,
             "descrizione": "VS.DISP. RIF. X FAVORE Russo Carmine - ADD.TOT"},
        ])
    r = _run(associa_bonifici_stipendi(db, stipendio_id="S1"))
    assert r["bonifici_associati"] == 1
    assert db.salari.docs[0]["riconciliato"] is True
    assert not db.salari.docs[1].get("importo_bonifico")


def test_vecchia_etichetta_con_importo_diverso_non_e_verificata():
    riga = {
        "id": "S1", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
        "importo_busta": 1200.0, "importo_bonifico": 1000.0,
        "riconciliato": True, "estratto_conto_id": "M1",
    }
    db = _Db(
        salari=[riga],
        movimenti=[{
            "id": "M1", "data": "2026-04-03", "importo": -1000.0,
            "descrizione": "BONIFICO STIPENDIO FAVORE ROSSI MARIO",
        }],
    )
    assert _run(riconciliazione_salario_verificata(db, riga)) is False


def test_etichetta_con_nome_importo_e_movimento_reale_e_verificata():
    riga = {
        "id": "S1", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
        "importo_busta": 1200.0, "importo_bonifico": 1200.0,
        "riconciliato": True, "estratto_conto_id": "M1",
    }
    db = _Db(
        salari=[riga],
        movimenti=[{
            "id": "M1", "data": "2026-04-03", "importo": -1200.0,
            "descrizione": "BONIFICO STIPENDIO FAVORE ROSSI MARIO",
        }],
    )
    assert _run(riconciliazione_salario_verificata(db, riga)) is True


def test_etichetta_con_due_movimenti_reali_e_verificata():
    riga = {
        "id": "S1", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
        "importo_busta": 1200.0, "importo_bonifico": 1200.0,
        "riconciliato": True, "movimenti_bancari_ids": ["M1", "M2"],
    }
    db = _Db(
        salari=[riga],
        movimenti=[
            {"id": "M1", "data": "2026-04-03", "importo": -800.0,
             "descrizione": "BONIFICO STIPENDIO FAVORE ROSSI MARIO"},
            {"id": "M2", "data": "2026-04-08", "importo": -400.0,
             "descrizione": "BONIFICO STIPENDIO FAVORE ROSSI MARIO"},
        ],
    )
    assert _run(riconciliazione_salario_verificata(db, riga)) is True
