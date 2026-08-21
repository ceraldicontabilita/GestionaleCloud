"""Accrediti SumUp: chiudono un credito, non creano ricavi.

L'errore che questi test impediscono e' il piu' grave possibile in questo
flusso: registrare l'accredito da 98 come una seconda vendita, gonfiando i
ricavi di un importo gia' dichiarato dal corrispettivo XML.
"""
import asyncio

import pytest
from app.services.sheets_document_store import MemorySheetsClient

from app.services import sumup_payout, sumup_sync
from app.services.scritture_contabili import registra_chiusura_pos_reale
from app.services.sumup_payout import calcola_commissione, componenti_del_payout

MERCHANT = "MFNRDMC4"
PAYOUT = "PID1772679"


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return MemorySheetsClient()["sumup_payout_test"]


@pytest.fixture(autouse=True)
def _credenziali(monkeypatch):
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_API_KEY", "sup_sk_test",
                        raising=False)
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_MERCHANT_CODE", MERCHANT,
                        raising=False)


def _tx(tid, importo, *, giorno="2026-08-06", tipo="PAYMENT",
        stato="SUCCESSFUL", payout=PAYOUT):
    return {
        "chiave": f"{MERCHANT}:{tid}", "transaction_id": tid,
        "tipo": tipo, "stato": stato, "data": giorno, "importo": importo,
        "payout_id": payout, "valuta": "EUR",
    }


def _payout(netto, *, pid=PAYOUT, data="2026-08-07T05:00:00Z"):
    return {"id": pid, "amount": netto, "date": data,
            "currency": "EUR", "status": "SUCCESSFUL"}


# --- Formula ---------------------------------------------------------------

def test_la_commissione_e_la_differenza_fra_lordo_e_versato():
    assert calcola_commissione(
        vendite=100.0, rimborsi=0.0, chargeback=0.0, netto=98.0) == 2.0


def test_rimborsi_e_chargeback_non_diventano_commissione():
    """Riducono l'accredito, ma non sono un costo di commissione."""
    assert calcola_commissione(
        vendite=100.0, rimborsi=30.0, chargeback=20.0, netto=48.0) == 2.0


def test_le_componenti_si_leggono_dal_payout_id_non_dall_importo():
    transazioni = [
        _tx("t1", 60.0), _tx("t2", 40.0),
        _tx("t9", 500.0, payout="ALTRO"),      # altro accredito
        _tx("t8", 70.0, stato="FAILED"),       # non riuscita
    ]
    componenti = componenti_del_payout(transazioni, PAYOUT)
    assert componenti["vendite"] == 100.0
    assert componenti["transazioni"] == 2
    assert componenti["giorni"] == ["2026-08-06"]


def test_un_payout_puo_coprire_piu_giornate():
    transazioni = [
        _tx("t1", 60.0, giorno="2026-08-05"),
        _tx("t2", 40.0, giorno="2026-08-06"),
    ]
    componenti = componenti_del_payout(transazioni, PAYOUT)
    assert componenti["giorni"] == ["2026-08-05", "2026-08-06"]
    assert componenti["vendite"] == 100.0


# --- Scritture -------------------------------------------------------------

def _scenario_utente(db):
    """Vendite 100, commissioni 2, accredito 98."""
    _run(db.sumup_transactions.insert_many([_tx("t1", 60.0), _tx("t2", 40.0)]))
    _run(registra_chiusura_pos_reale(db, "2026-08-06", 100.0, gestore="sumup"))


def test_l_accredito_e_una_scrittura_composta_che_quadra():
    """100 di credito chiuso = 98 sulla Mastercard + 2 di commissioni."""
    db = _db()
    _scenario_utente(db)
    esito = _run(sumup_payout.registra_payout(db, _payout(98.0)))

    assert esito["quadra"] is True
    assert esito["commissione"] == 2.0
    assert esito["stato_riconciliazione"] == "riconciliato"
    assert esito["scrittura"]["quadra"] is True

    per_source = {r["source"]: r for r in
                  _run(db.prima_nota_banca.find({}).to_list(50))}

    apertura = per_source["trasferimento_pos"]
    chiusura = per_source["chiusura_credito_pos"]
    accredito = per_source["accredito_payout"]
    commissioni = per_source["commissioni_sumup"]

    assert (apertura["tipo"], apertura["importo"]) == ("entrata", 100.0)
    assert (chiusura["tipo"], chiusura["importo"]) == ("uscita", 100.0)
    assert (accredito["tipo"], accredito["importo"]) == ("entrata", 98.0)
    assert (commissioni["tipo"], commissioni["importo"]) == ("uscita", 2.0)

    # Le tre righe dell'operazione condividono il settlement_id.
    settlement = esito["scrittura"]["settlement_id"]
    assert {chiusura["settlement_id"], accredito["settlement_id"],
            commissioni["settlement_id"]} == {settlement}

    # Il credito si azzera da solo: apertura + chiusura = 0.
    assert apertura["importo"] - chiusura["importo"] == 0.0


def test_il_payout_non_tocca_bpm_ma_la_mastercard():
    db = _db()
    _scenario_utente(db)
    _run(sumup_payout.registra_payout(db, _payout(98.0)))

    accredito = _run(db.prima_nota_banca.find_one({"source": "accredito_payout"}))
    assert accredito["conto_contabile"] == "19.01.05"      # Mastercard SumUp
    assert accredito["conto_nome"] == "Mastercard SumUp"
    assert accredito["conto_contabile"] != "19.01.01"      # mai BPM


def test_la_commissione_va_sul_sottoconto_del_circuito():
    db = _db()
    _scenario_utente(db)
    _run(sumup_payout.registra_payout(db, _payout(98.0)))

    costo = _run(db.prima_nota_banca.find_one({"source": "commissioni_sumup"}))
    assert costo["conto_contabile"] == "75.01.07.02"
    assert costo["conto_nome"] == "Costi commissioni SumUp"
    assert costo["categoria"] == "Commissioni e spese bancarie"
    assert costo["circuito"] == "SUMUP"
    assert costo["payout_id"] == PAYOUT
    assert costo["giorni_coperti"] == ["2026-08-06"]
    # Non e' un prelievo dalla Mastercard: la trattenuta non ci e' mai passata.
    assert costo["natura"] == "costo"


def test_il_credito_smette_di_essere_in_transito():
    db = _db()
    _scenario_utente(db)
    _run(sumup_payout.registra_payout(db, _payout(98.0)))

    credito = _run(db.prima_nota_banca.find_one({"source": "trasferimento_pos"}))
    assert credito["in_transito"] is False
    assert credito["riconciliato"] is True
    assert credito["payout_id"] == PAYOUT


def test_rielaborare_lo_stesso_payout_non_duplica_la_commissione():
    db = _db()
    _scenario_utente(db)
    _run(sumup_payout.registra_payout(db, _payout(98.0)))
    _run(sumup_payout.registra_payout(db, _payout(98.0)))

    costi = _run(db.prima_nota_banca.find(
        {"source": "commissioni_sumup"}).to_list(50))
    assert len(costi) == 1
    assert len(_run(db.sumup_payouts.find({}).to_list(50))) == 1


def test_un_payout_senza_transazioni_non_aggancia_nulla():
    """Associarlo 'per importo simile' e' esattamente l'errore da evitare."""
    db = _db()
    _run(registra_chiusura_pos_reale(db, "2026-08-06", 100.0, gestore="sumup"))
    esito = _run(sumup_payout.registra_payout(db, _payout(98.0)))

    assert esito["stato_riconciliazione"] == "payout_senza_transazioni"
    assert esito["crediti_chiusi"] == 0
    assert _run(db.prima_nota_banca.find_one({"source": "commissioni_sumup"})) is None
    credito = _run(db.prima_nota_banca.find_one({"source": "trasferimento_pos"}))
    assert credito["in_transito"] is True


def test_una_trattenuta_anomala_non_diventa_costo_in_automatico():
    db = _db()
    _scenario_utente(db)
    esito = _run(sumup_payout.registra_payout(db, _payout(40.0)))

    assert esito["stato_riconciliazione"] == "commissioni_da_verificare"
    assert _run(db.prima_nota_banca.find_one({"source": "commissioni_sumup"})) is None
    credito = _run(db.prima_nota_banca.find_one({"source": "trasferimento_pos"}))
    assert credito["in_transito"] is True


def test_un_payout_failed_non_scrive_e_non_chiude_il_credito():
    db = _db()
    _scenario_utente(db)
    payout = {**_payout(98.0), "status": "FAILED"}

    esito = _run(sumup_payout.registra_payout(db, payout))

    assert esito["stato_riconciliazione"] == "payout_fallito"
    assert esito["scrittura"] == {}
    assert esito["crediti_chiusi"] == 0
    credito = _run(db.prima_nota_banca.find_one({"source": "trasferimento_pos"}))
    assert credito["in_transito"] is True
    assert _run(db.prima_nota_banca.find_one({"source": "accredito_payout"})) is None


def test_rettifica_failed_resta_prova_senza_scritture():
    db = _db()
    gruppo = {
        "payout_id": "RET-FAILED",
        "date": "2026-08-08",
        "deduction_amount": 10.0,
        "status": "FAILED",
        "tipi": ["REFUND_DEDUCTION"],
        "record_ids": ["r1"],
    }

    esito = _run(sumup_payout.registra_rettifica_payout(
        db, gruppo, transazioni=[_tx("t1", 10.0)]
    ))

    assert esito["stato_riconciliazione"] == "rettifica_da_verificare"
    assert esito["scritture"] == {}
    assert _run(db.prima_nota_banca.find_one({"settlement_id": "sumup:RET-FAILED"})) is None


def test_il_payout_di_piu_giorni_chiude_tutti_i_crediti_coperti():
    db = _db()
    _run(db.sumup_transactions.insert_many([
        _tx("t1", 60.0, giorno="2026-08-05"),
        _tx("t2", 40.0, giorno="2026-08-06"),
    ]))
    _run(registra_chiusura_pos_reale(db, "2026-08-05", 60.0, gestore="sumup"))
    _run(registra_chiusura_pos_reale(db, "2026-08-06", 40.0, gestore="sumup"))

    esito = _run(sumup_payout.registra_payout(db, _payout(98.0)))
    assert esito["crediti_chiusi"] == 2
    assert esito["commissione"] == 2.0

    crediti = _run(db.prima_nota_banca.find(
        {"source": "trasferimento_pos"}).to_list(50))
    assert all(c["in_transito"] is False for c in crediti)


def test_il_payout_non_tocca_i_crediti_nexi():
    db = _db()
    _scenario_utente(db)
    _run(registra_chiusura_pos_reale(db, "2026-08-06", 500.0, gestore="nexi"))
    _run(sumup_payout.registra_payout(db, _payout(98.0)))

    nexi = _run(db.prima_nota_banca.find_one(
        {"source": "trasferimento_pos", "gestore": "numia"}))
    assert nexi["in_transito"] is True
    assert nexi.get("payout_id") is None
