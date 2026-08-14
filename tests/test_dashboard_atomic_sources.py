import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import controllo_gestione
from app.routers.prima_nota_module import stats


def _run(awaitable):
    return asyncio.run(awaitable)


def test_dashboard_separa_bpm_sumup_e_non_trascina_anni_storici(monkeypatch):
    db = AsyncMongoMockClient()["dashboard_financial_sources_test"]
    monkeypatch.setattr(stats.Database, "get_db", staticmethod(lambda: db))
    _run(db["prima_nota_cassa"].insert_many([
        {"id": "c-2025", "data": "2025-12-31", "tipo": "uscita", "importo": 1000.0},
        {"id": "c-2026", "data": "2026-01-02", "tipo": "entrata", "importo": 100.0},
    ]))
    _run(db["prima_nota_banca"].insert_many([
        {"id": "b-2025", "data": "2025-12-31", "tipo": "uscita", "importo": 999.0},
        {"id": "b-in", "data": "2026-02-01", "tipo": "entrata", "importo": 200.0},
        {"id": "b-out", "data": "2026-02-02", "tipo": "uscita", "importo": 50.0},
        {"id": "sumup", "data": "2026-02-03", "tipo": "entrata", "importo": 80.0,
         "conto_contabile": "19.01.05", "source": "accredito_payout"},
        {"id": "credito-pos", "data": "2026-02-04", "tipo": "entrata", "importo": 500.0,
         "source": "trasferimento_pos", "natura": "credito_pos"},
    ]))

    risultato = _run(stats.get_prima_nota_stats(
        data_da="2026-01-01", data_a="2026-12-31",
    ))

    assert risultato["cassa"]["saldo"] == 100.0
    assert risultato["banca"]["saldo"] == 150.0
    assert risultato["sumup"]["saldo"] == 80.0
    assert risultato["totale"]["saldo"] == 330.0
    assert risultato["criterio"] == "movimenti_del_periodo_senza_riporti_storici"


def test_dashboard_annuale_include_il_riporto_manualizzato(monkeypatch):
    db = AsyncMongoMockClient()["dashboard_annual_opening_balance_test"]
    monkeypatch.setattr(stats.Database, "get_db", staticmethod(lambda: db))
    _run(db["prima_nota_saldi_iniziali"].insert_one({
        "id": "saldo-cassa-2026", "tipo": "cassa", "anno": 2026, "importo": -3426.67,
    }))
    _run(db["prima_nota_cassa"].insert_many([
        {"id": "in", "data": "2026-01-02", "tipo": "entrata", "importo": 10000.0},
        {"id": "out", "data": "2026-01-03", "tipo": "uscita", "importo": 1000.0},
    ]))

    risultato = _run(stats.get_prima_nota_stats(
        data_da="2026-01-01", data_a="2026-12-31",
    ))

    assert risultato["cassa"]["riporto"] == -3426.67
    assert risultato["cassa"]["saldo"] == 5573.33
    assert risultato["criterio"] == "saldo_esercizio_con_riporto_manualizzato"
    assert risultato["saldo_conto_certificato"] is True


def test_dashboard_non_somma_fattura_iva_e_pagamento_cassa_due_volte(monkeypatch):
    db = AsyncMongoMockClient()["dashboard_economic_sources_test"]
    monkeypatch.setattr(controllo_gestione.Database, "get_db", staticmethod(lambda: db))
    _run(db["corrispettivi"].insert_one({
        "id": "corr-1", "data": "2026-01-10", "totale": 122.0,
        "totale_imponibile": 100.0, "totale_iva": 22.0,
    }))
    _run(db["corrispettivi"].insert_one({
        "id": "corr-legacy", "data": "2026-01-11", "totale": 97.6,
        "totale_imponibile": 0.0, "imponibile": 80.0, "iva": 17.6,
    }))
    _run(db["invoices"].insert_many([
        {"id": "fatt-1", "invoice_date": "2026-01-12", "tipo_documento": "TD01",
         "total_amount": 61.0, "imponibile": 50.0, "iva": 11.0},
        {"id": "nc-1", "invoice_date": "2026-01-15", "tipo_documento": "TD04",
         "total_amount": 12.2, "imponibile": 10.0, "iva": 2.2},
    ]))
    _run(db["cedolini"].insert_one({
        "id": "ced-1", "anno": 2026, "mese": 1, "costo_azienda": 20.0,
    }))
    _run(db["prima_nota_cassa"].insert_one({
        "id": "pagamento-fatt-1", "data": "2026-01-20", "tipo": "uscita", "importo": 61.0,
    }))

    risultato = _run(controllo_gestione.get_analisi_costi_ricavi(anno=2026, mese=1))

    assert risultato["ricavi"]["totale"] == 180.0
    assert risultato["costi"]["acquisti_merce"] == 40.0
    assert risultato["costi"]["personale"] == 20.0
    assert risultato["costi"]["altre_uscite"] == 0.0
    assert risultato["costi"]["totale"] == 60.0
    assert risultato["margine"]["importo"] == 120.0
    assert risultato["criterio"] == "competenza_imponibile_senza_doppio_conteggio_pagamenti"
    assert risultato["copertura_corrispettivi"] == {
        "dal": "2026-01-10", "al": "2026-01-11", "documenti": 2,
    }
