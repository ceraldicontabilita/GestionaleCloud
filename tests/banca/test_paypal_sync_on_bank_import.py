import asyncio

from app.services.reconciliation_orchestrator import on_estratto_conto_importato_riprocessa


def test_bank_import_syncs_historical_paypal_before_matching(monkeypatch):
    calls = []

    async def sync(db, start, end):
        calls.append(("sync", start, end))
        return {"period_start": start.isoformat(), "total": 2}

    async def reconcile(db, *, anno=None, movimento_ids=None):
        calls.append(("reconcile", anno, movimento_ids))
        return {"paypal": {"banca": {"riconciliati": 1}}}

    monkeypatch.setattr("app.config.settings.PAYPAL_CLIENT_ID", "test-id")
    monkeypatch.setattr("app.config.settings.PAYPAL_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr("app.services.paypal_api_sync.sync_paypal_period", sync)
    monkeypatch.setattr(
        "app.services.reconciliation_orchestrator.riconcilia_documenti_e_pagamenti",
        reconcile,
    )

    result = asyncio.run(on_estratto_conto_importato_riprocessa({"movimenti": [
        {"id": "a", "data": "2025-04-10", "descrizione": "SDD PayPal Europe", "tipo": "uscita"},
        {"id": "b", "data": "2025-04-15", "descrizione": "BON.DA PAYPAL", "tipo": "entrata"},
        {"id": "c", "data": "2025-05-01", "descrizione": "Assegno 123", "tipo": "uscita"},
    ]}, object()))

    assert [call[0] for call in calls] == ["sync", "reconcile"]
    assert calls[0][1].isoformat() == "2025-04-01T00:00:00+00:00"
    assert calls[0][2].isoformat() == "2025-04-30T23:59:59+00:00"
    assert calls[1] == ("reconcile", 2025, ["a", "b", "c"])
    assert result["paypal_api"]["stato"] == "sincronizzato"
    assert result["paypal"]["banca"]["riconciliati"] == 1


def test_other_movements_do_not_trigger_paypal_sync(monkeypatch):
    async def reconcile(db, *, anno=None, movimento_ids=None):
        return {"anno": anno}

    monkeypatch.setattr(
        "app.services.reconciliation_orchestrator.riconcilia_documenti_e_pagamenti",
        reconcile,
    )
    result = asyncio.run(on_estratto_conto_importato_riprocessa({"movimenti": [
        {"id": "a", "data": "2026-08-13", "descrizione": "Giroconto da Mastercard SumUp"},
    ]}, object()))
    assert result["paypal_api"]["stato"] == "nessun_movimento_paypal"


def test_paypal_api_failure_does_not_hide_bank_import(monkeypatch):
    async def failing_sync(db, start, end):
        raise RuntimeError("API indisponibile")

    async def reconcile(db, *, anno=None, movimento_ids=None):
        return {"matched_existing_evidence": 1}

    monkeypatch.setattr("app.config.settings.PAYPAL_CLIENT_ID", "test-id")
    monkeypatch.setattr("app.config.settings.PAYPAL_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr("app.services.paypal_api_sync.sync_paypal_period", failing_sync)
    monkeypatch.setattr(
        "app.services.reconciliation_orchestrator.riconcilia_documenti_e_pagamenti",
        reconcile,
    )
    result = asyncio.run(on_estratto_conto_importato_riprocessa({"movimenti": [
        {"id": "a", "data": "2026-01-20", "descrizione": "SDD CORE PayPal"},
    ]}, object()))
    assert result["matched_existing_evidence"] == 1
    assert result["paypal_api"] == {
        "stato": "errore", "periodi": [],
        "errori": [{"mese": "2026-01", "tipo": "RuntimeError"}],
    }
