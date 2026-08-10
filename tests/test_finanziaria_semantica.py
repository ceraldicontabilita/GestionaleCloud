"""Regressioni semantiche della pagina Finanziaria.

La variazione dei flussi dell'anno e la disponibilita contabile finale hanno
grane diverse: la seconda include i riporti iniziali. Non devono essere
presentate come lo stesso saldo.
"""

import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import finanziaria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_summary_distingue_flussi_riporti_e_disponibilita(monkeypatch):
    db = AsyncMongoMockClient()["test_finanziaria"]
    _run(db["prima_nota_cassa"].insert_many([
        {"data": "2026-01-10", "tipo": "entrata", "importo": 100.0,
         "categoria": "Corrispettivi", "source": "manuale", "status": "active"},
        {"data": "2026-01-11", "tipo": "uscita", "importo": 40.0,
         "categoria": "Fatture", "source": "manuale", "status": "active"},
        {"data": "2026-01-12", "tipo": "uscita", "importo": 20.0,
         "categoria": "Versamento Banca", "source": "trasferimento_interno", "status": "active"},
    ]))
    _run(db["prima_nota_banca"].insert_many([
        {"data": "2026-01-10", "tipo": "entrata", "importo": 300.0,
         "categoria": "Corrispettivi POS", "source": "corrispettivo_pos", "status": "active"},
        {"data": "2026-01-11", "tipo": "uscita", "importo": 50.0,
         "categoria": "Fatture", "source": "manuale", "status": "active"},
        {"data": "2026-01-12", "tipo": "entrata", "importo": 20.0,
         "categoria": "Versamento Banca", "source": "trasferimento_interno", "status": "active"},
    ]))
    async def saldi_canonici(_db, collection, _query, _anno):
        if collection == "prima_nota_cassa":
            return {"saldo_precedente": 10.0, "saldo": 50.0}
        return {"saldo_precedente": -100.0, "saldo": 170.0}

    monkeypatch.setattr(finanziaria.Database, "get_db", staticmethod(lambda: db))
    # Mongomock non implementa $convert; il motore di saldo canonico ha test
    # dedicati, qui si verifica come Finanziaria usa i valori restituiti.
    monkeypatch.setattr(finanziaria, "aggrega_saldo_prima_nota", saldi_canonici)

    result = _run(finanziaria.get_financial_summary(anno=2026))

    # Il credito POS lordo da 300 resta prova di riconciliazione ma non è una
    # disponibilità bancaria reale; la Finanziaria conta solo l'entrata Cassa.
    assert result["total_income"] == 100.0
    assert result["total_expenses"] == 90.0
    assert result["balance"] == result["flow_balance"] == 10.0
    assert result["opening_balance"] == -90.0
    assert result["saldo_cassa"] == 50.0
    assert result["saldo_banca"] == 170.0
    assert result["saldo_totale"] == result["available_balance"] == 220.0
    assert result["balance"] != result["saldo_totale"]


def test_summary_non_inventa_crediti_clienti(monkeypatch):
    db = AsyncMongoMockClient()["test_finanziaria_crediti"]
    monkeypatch.setattr(finanziaria.Database, "get_db", staticmethod(lambda: db))

    result = _run(finanziaria.get_financial_summary(anno=2026))

    assert result["receivables"] is None
    assert result["receivables_available"] is False
    assert "fonte canonica" in result["receivables_note"]
