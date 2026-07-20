"""Agente Fiscale shadow: aggregati, prudenza, idempotenza e nessuna azione."""

import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

import app.agents.fiscale_shadow as agent_mod
from app.agents.fiscale_shadow import FiscaleShadow
from app.services.fiscale_shadow_service import leggi_snapshot_fiscale


def _db():
    return AsyncMongoMockClient()["fiscale_shadow_test"]


async def _seed(db):
    await db["f24_unificato"].insert_many([
        {"id": "F1", "status": "da_pagare", "data_scadenza": "2026-07-10", "totale": "100.00", "codice_fiscale": "NON DEVE USCIRE"},
        {"id": "F2", "stato": "da_pagare", "scadenza": "2026-07-25", "totali": {"saldo_finale": "200.50"}},
        {"id": "F3", "status": "paid", "data_scadenza": "2026-07-12", "totale": 999},
        {"id": "F4", "status": "da_pagare", "totale": 80},
    ])
    await db["ritenute_acconto"].insert_many([
        {"id": "R1", "stato": "scaduta_da_versare", "scadenza": "2026-07-16", "importo": 50},
        {"id": "R2", "stato": "da_pagare", "scadenza": "2026-07-30", "importo": 70},
        {"id": "R3", "stato": "pagata_puntuale", "scadenza": "2026-07-16", "importo": 500},
    ])
    await db["liquidazioni_iva"].insert_one({"periodo": "2026-06", "versione": 2, "stato": "CALCOLATA"})


def test_snapshot_solo_aggregati_e_schemi_f24_misti():
    db = _db()
    asyncio.run(_seed(db))
    result = asyncio.run(leggi_snapshot_fiscale(db, date(2026, 7, 20))).to_dict()
    assert result["f24_overdue"]["count"] == 1
    assert result["f24_overdue"]["total"] == "100.00"
    assert result["f24_upcoming"]["total"] == "200.50"
    assert result["withholding_overdue"]["total"] == "50.00"
    assert result["withholding_upcoming"]["total"] == "70.00"
    assert result["records_without_due_date"] == 1
    assert result["previous_vat_status"] == "CALCOLATA"
    assert "NON DEVE USCIRE" not in str(result)
    assert "codice_fiscale" not in str(result)


def test_obblighi_scaduti_generano_l3_idempotente_senza_pagamenti(monkeypatch):
    db = _db()
    asyncio.run(_seed(db))

    async def snapshot(database):
        return await leggi_snapshot_fiscale(database, date(2026, 7, 20))

    monkeypatch.setattr(agent_mod, "leggi_snapshot_fiscale", snapshot)
    asyncio.run(FiscaleShadow().run(db))
    asyncio.run(FiscaleShadow().run(db))
    decisions = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    overdue = next(d for d in decisions if "scaduti" in d["objective"])
    assert overdue["autonomy_level"] == "L3"
    assert overdue["execution_status"] == "pending_approval"
    assert overdue["financial_impact"] == 150.0
    assert len(decisions) == 3
    for collection in ("prima_nota_banca", "f24_pagamenti", "commercialista_log"):
        assert asyncio.run(db[collection].count_documents({})) == 0


def test_completezza_ok_e_nessun_obbligo_non_genera_decisioni(monkeypatch):
    db = _db()
    awaitable = db["liquidazioni_iva"].insert_one({"periodo": "2026-06", "versione": 1, "stato": "CONFERMATA"})
    asyncio.run(awaitable)
    asyncio.run(db["commercialista_log"].insert_one({
        "tipo": "prima_nota_cassa", "anno": 2026, "mese": 6, "success": True,
    }))

    async def snapshot(database):
        return await leggi_snapshot_fiscale(database, date(2026, 7, 20))

    monkeypatch.setattr(agent_mod, "leggi_snapshot_fiscale", snapshot)
    asyncio.run(FiscaleShadow().run(db))
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 0


def test_dati_incompleti_non_vengono_stimati():
    db = _db()
    asyncio.run(db["f24_unificato"].insert_one({
        "status": "da_pagare", "periodo": "06/2026", "totale": 10,
    }))
    result = asyncio.run(leggi_snapshot_fiscale(db, date(2026, 7, 20))).to_dict()
    assert result["f24_overdue"]["count"] == 0
    assert result["f24_upcoming"]["count"] == 0
    assert result["records_without_due_date"] == 1


def test_orchestratore_e_scheduler_registrano_fiscale_shadow(monkeypatch):
    from app.agents.orchestrator import SCHEDULE
    import app.scheduler as scheduler_mod

    assert SCHEDULE["FiscaleShadow"] == 21600

    class _SchedulerFinto:
        def __init__(self):
            self.jobs = []
            self.running = False

        def add_job(self, function, *args, **kwargs):
            self.jobs.append((function, args, kwargs))

        def start(self):
            self.running = True

    scheduler = _SchedulerFinto()
    monkeypatch.setattr(scheduler_mod, "scheduler", scheduler)
    scheduler_mod.start_scheduler()
    job = next(item for item in scheduler.jobs if item[2].get("id") == "ai_fiscale_shadow")
    assert job[1] == ("interval",)
    assert job[2]["hours"] == 6
    assert job[2]["next_run_time"] is not None
