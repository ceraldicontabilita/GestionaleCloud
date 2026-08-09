import asyncio

from app.services.reconciliation_orchestrator import (
    riconcilia_documenti_e_pagamenti,
)


def test_orchestratore_include_paypal_fatture_banca_e_cbill(monkeypatch):
    calls = []

    async def record(name, result, *args, **kwargs):
        calls.append((name, kwargs))
        return result

    async def assegni_intenti(*args, **kwargs):
        return await record("assegni_intenti", {}, *args, **kwargs)

    async def assegni_auto(*args, **kwargs):
        return await record("assegni_auto", {}, *args, **kwargs)

    async def bonifici(*args, **kwargs):
        return await record("bonifici", {}, *args, **kwargs)

    async def salari(*args, **kwargs):
        return await record("salari", {}, *args, **kwargs)

    async def f24(*args, **kwargs):
        return await record("f24", {}, *args, **kwargs)

    async def paypal_fatture(*args, **kwargs):
        return await record("paypal_fatture", {"collegati": 1}, *args, **kwargs)

    async def paypal_banca(*args, **kwargs):
        return await record("paypal_banca", {"riconciliati": 1}, *args, **kwargs)

    async def cbill(*args, **kwargs):
        return await record("cbill", {"associati": 1}, *args, **kwargs)

    async def finanziamenti(*args, **kwargs):
        return await record("finanziamenti", {"apporti_nuovi": 1}, *args, **kwargs)

    async def proiezione(*args, **kwargs):
        return await record("proiezione", {"proiettati": 4}, *args, **kwargs)

    monkeypatch.setattr(
        "app.services.assegni_fattura_intent.riprocessa_intenti_assegni",
        assegni_intenti,
    )
    monkeypatch.setattr(
        "app.routers.bank.assegni_auto_match.run_auto_match", assegni_auto,
    )
    monkeypatch.setattr(
        "app.services.bonifici_pdf_ingest.riprocessa_bonifici_pendenti",
        bonifici,
    )
    monkeypatch.setattr(
        "app.services.stipendi_bonifici.associa_bonifici_stipendi", salari,
    )
    monkeypatch.setattr(
        "app.services.f24_bank_reconciliation.riconcilia_f24_tributi_banca",
        f24,
    )
    monkeypatch.setattr(
        "app.routers.paypal_statements.riprocessa_collegamenti_paypal",
        paypal_fatture,
    )
    monkeypatch.setattr(
        "app.routers.paypal_statements._auto_riconcilia", paypal_banca,
    )
    monkeypatch.setattr("app.routers.pagopa.auto_associa_ricevute_db", cbill)
    monkeypatch.setattr(
        "app.services.finanziamenti_soci.scan_finanziamenti_da_ec",
        finanziamenti,
    )
    monkeypatch.setattr(
        "app.services.proiezione_bancaria.proietta_movimenti_bancari_semantici",
        proiezione,
    )

    result = asyncio.run(
        riconcilia_documenti_e_pagamenti(object(), anno=2026)
    )

    assert [name for name, _ in calls].count("paypal_fatture") == 2
    assert result["paypal"]["banca"] == {"riconciliati": 1}
    assert result["cbill_pagopa"] == {"associati": 1}
    assert result["finanziamenti_soci"] == {"apporti_nuovi": 1}
    assert result["proiezione_banca"] == {"proiettati": 4}
    paypal_ranges = [
        kwargs for name, kwargs in calls if name == "paypal_fatture"
    ]
    assert paypal_ranges == [
        {"start_date": "2026-01-01", "end_date": "2026-12-31"},
        {"start_date": "2026-01-01", "end_date": "2026-12-31"},
    ]

