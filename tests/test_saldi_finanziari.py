"""Schede finanziarie separate: BPM, Mastercard SumUp, crediti per circuito.

Decisione utente 07/08/2026: un credito POS non e' denaro sul conto. Ma il
denaro non deve nemmeno sparire — e' esattamente il bug del 16/07/2026, che
tolse ~204.000 EUR dai saldi bancari escludendo i trasferimenti POS. Qui si
verifica che l'importo escluso dal conto reale ricompaia, per intero, nella
scheda del credito.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module.common import saldi_finanziari
from app.services import conti_pos, sumup_payout, sumup_sync
from app.services.scritture_contabili import registra_chiusura_pos_reale

DATA = "2026-08-06"
MERCHANT = "MFNRDMC4"
PAYOUT = "PID1772679"


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return AsyncMongoMockClient()["saldi_finanziari_test"]


@pytest.fixture(autouse=True)
def _credenziali(monkeypatch):
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_API_KEY", "sup_sk_test",
                        raising=False)
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_MERCHANT_CODE", MERCHANT,
                        raising=False)


def _scheda(saldi, nome):
    for voce in saldi["conti_reali"] + saldi["crediti_pos"]:
        if voce["nome"] == nome:
            return voce
    raise AssertionError(f"scheda '{nome}' assente da {saldi}")


# --- Il piano dei conti ----------------------------------------------------

def test_i_conti_del_circuito_esistono_nel_piano_ufficiale():
    """conti_pos verifica il piano all'import: qui si fissa la mappatura."""
    assert conti_pos.conto_credito("sumup") == "15.07.02"
    assert conti_pos.conto_commissioni("sumup") == "75.01.07.02"
    assert conti_pos.conto_accredito("sumup") == "19.01.05"
    assert conti_pos.conto_credito("nexi") == "15.07.01"
    assert conti_pos.conto_commissioni("nexi") == "75.01.07.01"
    assert conti_pos.conto_accredito("nexi") == "19.01.01"


def test_un_circuito_ignoto_finisce_su_altri_costi_bancari():
    assert conti_pos.conto_commissioni("circuito-nuovo") == "75.01.07.04"


def test_i_sottoconti_commissioni_confluiscono_nei_costi():
    from app.services.piano_conti_ufficiale import sezione_di

    for codice in ("75.01.07.01", "75.01.07.02",
                   "75.01.07.03", "75.01.07.04"):
        sezione, gruppo, _ = sezione_di(codice)
        assert (sezione, gruppo) == ("CE", "costi")


# --- Separazione dei saldi -------------------------------------------------

def test_il_credito_pos_non_entra_nel_saldo_bpm():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi"))

    saldi = _run(saldi_finanziari(db))
    assert _scheda(saldi, "Banca BPM")["saldo"] == 0.0
    assert _scheda(saldi, "Crediti verso Nexi/Numia")["saldo"] == 500.0


def test_il_denaro_escluso_dal_conto_reale_non_sparisce():
    """La lezione del bug del 16/07/2026: separare non deve voler dire perdere."""
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi"))
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))

    saldi = _run(saldi_finanziari(db))
    assert saldi["crediti_pos_aperti"] == 600.0
    assert saldi["disponibilita_liquide"] == 0.0


def test_i_crediti_restano_distinti_per_circuito():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi"))
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))

    saldi = _run(saldi_finanziari(db))
    assert _scheda(saldi, "Crediti verso Nexi/Numia")["saldo"] == 500.0
    assert _scheda(saldi, "Crediti verso SumUp")["saldo"] == 100.0


def test_una_riga_storica_senza_conto_appartiene_a_bpm():
    """In produzione nessuna riga ha ancora conto_contabile."""
    db = _db()
    _run(db.prima_nota_banca.insert_one({
        "id": "storico", "data": DATA, "tipo": "entrata", "importo": 1000.0,
        "categoria": "Bonifico", "source": "estratto_conto",
    }))
    saldi = _run(saldi_finanziari(db))
    assert _scheda(saldi, "Banca BPM")["saldo"] == 1000.0
    assert _scheda(saldi, "Mastercard SumUp")["saldo"] == 0.0


def test_il_payout_sposta_il_denaro_dal_credito_alla_mastercard():
    """Il momento in cui il credito diventa liquidita', su un conto suo."""
    db = _db()
    _run(db.sumup_transactions.insert_many([{
        "chiave": f"{MERCHANT}:t1", "transaction_id": "t1", "tipo": "PAYMENT",
        "stato": "SUCCESSFUL", "data": DATA, "importo": 100.0,
        "payout_id": PAYOUT, "valuta": "EUR",
    }]))
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))

    prima = _run(saldi_finanziari(db))
    assert _scheda(prima, "Crediti verso SumUp")["saldo"] == 100.0
    assert _scheda(prima, "Mastercard SumUp")["saldo"] == 0.0

    _run(sumup_payout.registra_payout(db, {
        "id": PAYOUT, "amount": 98.0, "date": "2026-08-07T05:00:00Z",
        "currency": "EUR", "status": "PAID",
    }))

    dopo = _run(saldi_finanziari(db))
    # Il credito si chiude, la Mastercard incassa il netto, BPM resta ferma.
    assert _scheda(dopo, "Crediti verso SumUp")["saldo"] == 0.0
    assert _scheda(dopo, "Mastercard SumUp")["saldo"] == 98.0
    assert _scheda(dopo, "Banca BPM")["saldo"] == 0.0


def test_la_mastercard_non_viene_sommata_a_bpm():
    db = _db()
    _run(db.prima_nota_banca.insert_many([
        {"id": "bpm", "data": DATA, "tipo": "entrata", "importo": 1000.0,
         "categoria": "Bonifico", "source": "estratto_conto",
         "conto_contabile": "19.01.01"},
        {"id": "msc", "data": DATA, "tipo": "entrata", "importo": 98.0,
         "categoria": "Accrediti POS", "source": "accredito_payout",
         "conto_contabile": "19.01.05", "natura": "liquidita"},
    ]))
    saldi = _run(saldi_finanziari(db))
    assert _scheda(saldi, "Banca BPM")["saldo"] == 1000.0
    assert _scheda(saldi, "Mastercard SumUp")["saldo"] == 98.0
    # Concorrono insieme alle disponibilita', ma restano visibili distinti.
    assert saldi["disponibilita_liquide"] == 1098.0


def test_la_commissione_non_pesa_su_nessun_conto_di_tesoreria():
    """La trattenuta non e' mai transitata: e' solo un costo economico."""
    db = _db()
    _run(db.prima_nota_banca.insert_one({
        "id": "comm", "data": DATA, "tipo": "uscita", "importo": 2.0,
        "categoria": "Commissioni e spese bancarie",
        "source": "commissioni_sumup", "natura": "costo",
        "conto_contabile": "75.01.07.02",
    }))
    saldi = _run(saldi_finanziari(db))
    assert saldi["disponibilita_liquide"] == 0.0
    assert saldi["crediti_pos_aperti"] == 0.0
