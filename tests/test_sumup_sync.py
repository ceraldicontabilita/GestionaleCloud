"""Sincronizzazione SumUp: idempotenza, giorno locale, rimborsi.

Il rischio contabile non e' sbagliare un totale: e' contarlo due volte. Qui
si proteggono i tre punti dove puo' succedere — la risincronizzazione, il
rimborso che compare in due forme, e il fuso orario che sposta una vendita
serale al giorno dopo.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import sumup_sync
from app.services.sumup_sync import (
    _parametri_intervallo,
    _url_pagina_successiva,
    aggrega_per_giorno,
    giorno_locale,
    normalizza_transazione,
)

MERCHANT = "MFNRDMC4"


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return AsyncMongoMockClient()["sumup_sync_test"]


def _tx(tid, importo, *, timestamp="2026-08-06T10:00:00Z", tipo="PAYMENT",
        stato="SUCCESSFUL", rimborsato=None, riferimento=None):
    grezza = {
        "id": tid, "amount": importo, "timestamp": timestamp,
        "type": tipo, "status": stato, "currency": "EUR",
    }
    if rimborsato is not None:
        grezza["refunded_amount"] = rimborsato
    if riferimento is not None:
        grezza["related_transaction_id"] = riferimento
    return grezza


def _norm(*grezze):
    return [normalizza_transazione(g, MERCHANT) for g in grezze]


# --- Giorno contabile ------------------------------------------------------

@pytest.mark.parametrize(("istante", "atteso"), [
    ("2026-08-06T21:30:00Z", "2026-08-06"),   # 23:30 italiane, stesso giorno
    ("2026-08-06T22:30:00Z", "2026-08-07"),   # 00:30 italiane, giorno dopo
    ("2026-01-15T23:30:00Z", "2026-01-16"),   # ora solare: +1
    ("2026-08-06T00:30:00Z", "2026-08-06"),
])
def test_il_giorno_e_quello_del_negozio_non_utc(istante, atteso):
    assert giorno_locale(istante) == atteso


def test_un_istante_senza_fuso_e_letto_come_utc():
    """SumUp dichiara UTC: non va mai usato il fuso del server."""
    assert giorno_locale("2026-08-06T22:30:00") == "2026-08-07"


def test_intervallo_api_usa_i_parametri_ufficiali_e_il_fuso_del_negozio():
    params = _parametri_intervallo("2026-08-06", "2026-08-06")
    assert params == {
        "oldest_time": "2026-08-05T22:00:00Z",
        "newest_time": "2026-08-06T22:00:00Z",
        "order": "ascending",
        "limit": 100,
    }
    assert "start_date" not in params
    assert "end_date" not in params


def test_intervallo_api_rispetta_anche_l_ora_solare():
    params = _parametri_intervallo("2026-01-15", "2026-01-15")
    assert params["oldest_time"] == "2026-01-14T23:00:00Z"
    assert params["newest_time"] == "2026-01-15T23:00:00Z"


def test_link_paginazione_sumup_relativo_diventa_assoluto():
    base = "https://api.sumup.com/v2.1/merchants/M1/transactions/history"
    assert _url_pagina_successiva(
        base, "limit=100&oldest_ref=ABC&order=ascending"
    ) == (
        "https://api.sumup.com/v2.1/merchants/M1/transactions/history"
        "?limit=100&oldest_ref=ABC&order=ascending"
    )
    assert _url_pagina_successiva(base, "?oldest_ref=XYZ") == f"{base}?oldest_ref=XYZ"


# --- Normalizzazione -------------------------------------------------------

def test_una_transazione_senza_id_o_data_viene_scartata():
    assert normalizza_transazione({"amount": 10}, MERCHANT) is None
    assert normalizza_transazione(
        {"amount": 10, "timestamp": "2026-08-06T10:00:00Z"}, MERCHANT) is None
    assert normalizza_transazione({"id": "t1", "amount": 10}, MERCHANT) is None


def test_la_chiave_comprende_l_esercente():
    """Due conti SumUp diversi possono avere lo stesso transaction_id."""
    tx = normalizza_transazione(_tx("t1", 10), MERCHANT)
    assert tx["chiave"] == f"{MERCHANT}:t1"


# --- Aggregazione ----------------------------------------------------------

def test_piu_transazioni_nello_stesso_giorno_si_sommano():
    giornate = aggrega_per_giorno(_norm(
        _tx("t1", 40.0), _tx("t2", 35.50), _tx("t3", 24.50)))
    assert giornate["2026-08-06"]["vendite"] == 100.0
    assert giornate["2026-08-06"]["netto"] == 100.0
    assert giornate["2026-08-06"]["transazioni"] == 3


def test_le_transazioni_non_riuscite_non_entrano_nel_totale():
    giornate = aggrega_per_giorno(_norm(
        _tx("t1", 100.0),
        _tx("t2", 50.0, stato="FAILED"),
        _tx("t3", 30.0, stato="CANCELLED"),
        _tx("t4", 20.0, stato="PENDING"),
    ))
    assert giornate["2026-08-06"]["netto"] == 100.0
    assert giornate["2026-08-06"]["transazioni"] == 1


def test_il_rimborso_non_viene_sottratto_due_volte():
    """Il reso compare sia come evento REFUND sia come refunded_amount sul
    pagamento: sommarli entrambi toglierebbe 20 invece di 10."""
    giornate = aggrega_per_giorno(_norm(
        _tx("t1", 100.0, rimborsato=10.0),
        _tx("r1", 10.0, tipo="REFUND", riferimento="t1"),
    ))
    assert giornate["2026-08-06"]["vendite"] == 100.0
    assert giornate["2026-08-06"]["rimborsi"] == 10.0
    assert giornate["2026-08-06"]["netto"] == 90.0


def test_il_rimborso_senza_evento_dedicato_conta_lo_stesso():
    giornate = aggrega_per_giorno(_norm(_tx("t1", 100.0, rimborsato=10.0)))
    assert giornate["2026-08-06"]["rimborsi"] == 10.0
    assert giornate["2026-08-06"]["netto"] == 90.0


def test_il_rimborso_totale_azzera_la_giornata():
    giornate = aggrega_per_giorno(_norm(
        _tx("t1", 100.0),
        _tx("r1", 100.0, tipo="REFUND", riferimento="t1"),
    ))
    assert giornate["2026-08-06"]["netto"] == 0.0


def test_il_reso_pesa_sul_giorno_in_cui_e_avvenuto():
    """Il denaro esce quando si rimborsa, non quando si era venduto."""
    giornate = aggrega_per_giorno(_norm(
        _tx("t1", 100.0, timestamp="2026-08-05T10:00:00Z"),
        _tx("r1", 30.0, tipo="REFUND", riferimento="t1",
            timestamp="2026-08-06T10:00:00Z"),
    ))
    assert giornate["2026-08-05"]["netto"] == 100.0
    assert giornate["2026-08-06"]["netto"] == -30.0


def test_il_chargeback_resta_fuori_dal_venduto():
    """Incide sull'accredito, non su quanto e' passato dal terminale."""
    giornate = aggrega_per_giorno(_norm(
        _tx("t1", 100.0),
        _tx("c1", 25.0, tipo="CHARGEBACK"),
    ))
    assert giornate["2026-08-06"]["netto"] == 100.0
    assert giornate["2026-08-06"]["chargeback"] == 25.0


# --- Sincronizzazione ------------------------------------------------------

def _sincronizza(db, grezze, dal="2026-08-06", al="2026-08-06"):
    return _run(sumup_sync.sincronizza(db, dal, al, grezze=grezze))


@pytest.fixture(autouse=True)
def _credenziali(monkeypatch):
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_API_KEY", "sup_sk_test",
                        raising=False)
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_MERCHANT_CODE", MERCHANT,
                        raising=False)


def test_risincronizzare_non_duplica_nulla():
    db = _db()
    grezze = [_tx("t1", 60.0), _tx("t2", 40.0)]

    primo = _sincronizza(db, grezze)
    secondo = _sincronizza(db, grezze)

    assert primo["transazioni"]["nuove"] == 2
    assert secondo["transazioni"]["nuove"] == 0
    assert secondo["transazioni"]["aggiornate"] == 2
    assert secondo["giornate"][0]["action"] == "noop"

    assert len(_run(db.sumup_transactions.find({}).to_list(50))) == 2
    chiusure = _run(db.chiusure_pos_manuali.find({}).to_list(50))
    assert len(chiusure) == 1
    assert chiusure[0]["importo"] == 100.0
    assert chiusure[0]["gestore"] == "sumup"

    uscite = _run(db.prima_nota_cassa.find(
        {"source": "corrispettivo_import"}).to_list(50))
    assert len(uscite) == 1
    assert uscite[0]["importo"] == 100.0


def test_una_pagina_arrivata_prima_resta_nel_totale():
    """La seconda sincronizzazione riaggrega da database, non dal solo
    scaricato: altrimenti l'ultima pagina cancellerebbe le precedenti."""
    db = _db()
    _sincronizza(db, [_tx("t1", 60.0)])
    _sincronizza(db, [_tx("t2", 40.0)])

    chiusure = _run(db.chiusure_pos_manuali.find({}).to_list(50))
    assert len(chiusure) == 1
    assert chiusure[0]["importo"] == 100.0


def test_l_api_sostituisce_la_chiusura_manuale_senza_secondo_movimento():
    from app.services.scritture_contabili import registra_chiusura_pos_reale

    db = _db()
    _run(registra_chiusura_pos_reale(db, "2026-08-06", 95.0, gestore="sumup"))
    _sincronizza(db, [_tx("t1", 100.0)])

    chiusure = _run(db.chiusure_pos_manuali.find({}).to_list(50))
    assert len(chiusure) == 1
    assert chiusure[0]["importo"] == 100.0

    uscite = _run(db.prima_nota_cassa.find(
        {"source": "corrispettivo_import"}).to_list(50))
    assert len(uscite) == 1
    assert uscite[0]["importo"] == 100.0


def test_nexi_e_sumup_nello_stesso_giorno_restano_distinti():
    from app.services.scritture_contabili import (
        chiusura_pos_del_giorno,
        registra_chiusura_pos_reale,
    )

    db = _db()
    _run(registra_chiusura_pos_reale(db, "2026-08-06", 500.0, gestore="nexi"))
    _sincronizza(db, [_tx("t1", 100.0)])

    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 600.0
    uscite = _run(db.prima_nota_cassa.find(
        {"source": "corrispettivo_import"}).to_list(50))
    assert {u["circuito"]: u["importo"] for u in uscite} == {
        "NUMIA": 500.0, "SUMUP": 100.0}


def test_senza_credenziali_si_ferma_invece_di_scrivere_a_vuoto(monkeypatch):
    monkeypatch.setattr(sumup_sync.settings, "SUMUP_API_KEY", "", raising=False)
    db = _db()
    with pytest.raises(sumup_sync.SumUpNonConfigurato):
        _sincronizza(db, [_tx("t1", 100.0)])
    assert _run(db.chiusure_pos_manuali.find({}).to_list(10)) == []
