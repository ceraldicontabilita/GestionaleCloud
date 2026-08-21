"""Crediti shadow: aging aggregato, bozze non inviate e schedulazione."""

import asyncio
from datetime import date

from app.services.sheets_document_store import MemorySheetsClient

import app.agents.crediti_shadow as agent_mod
from app.agents.crediti_shadow import CreditiShadow
from app.services.crediti_shadow_service import leggi_snapshot_crediti


def _db():
    return MemorySheetsClient()["crediti_shadow_test"]


async def _seed(db):
    await db["fatture_emesse"].insert_many([
        {
            "data_scadenza": "2026-05-10", "totale": "100.00",
            "importo_pagato": "20.00", "cliente": "NOME RISERVATO",
        },
        {"due_date": "2026-06-15", "importo_residuo": "50.00"},
        {"scadenza": "2026-08-01", "total_amount": "200.00"},
        {"data_scadenza": "2026-05-01", "totale": 999, "pagato": True},
        {"data_scadenza": "2026-05-02", "totale": 30, "tipo_documento": "TD04"},
        {"totale": 40},
        {"data_scadenza": "2026-05-03"},
        {"data_scadenza": "2026-05-04", "totale": 10, "importo_pagato": 10},
    ])


def test_snapshot_crediti_aggregato_esclude_note_e_dati_personali():
    db = _db()
    asyncio.run(_seed(db))
    result = asyncio.run(leggi_snapshot_crediti(db, date(2026, 7, 20))).to_dict()
    assert result["overdue"] == {"count": 2, "total": "130.00"}
    assert result["not_due"] == {"count": 1, "total": "200.00"}
    assert result["oldest_due_date"] == "2026-05-10"
    assert result["max_days_overdue"] == 71
    assert result["overdue_by_month"] == [
        {"month": "2026-05", "count": 1, "total": "80.00"},
        {"month": "2026-06", "count": 1, "total": "50.00"},
    ]
    assert result["records_without_due_date"] == 1
    assert result["records_without_amount"] == 1
    assert result["credit_notes_excluded"] == 1
    assert result["reminder_draft_supported"] is True
    assert result["reminder_send_supported"] is False
    assert "NOME RISERVATO" not in str(result)


def test_agente_crea_bozza_l3_e_qualita_l1_senza_inviare(monkeypatch):
    db = _db()
    asyncio.run(_seed(db))

    async def snapshot(database):
        return await leggi_snapshot_crediti(database, date(2026, 7, 20))

    monkeypatch.setattr(agent_mod, "leggi_snapshot_crediti", snapshot)
    asyncio.run(CreditiShadow().run(db))
    asyncio.run(CreditiShadow().run(db))

    decisions = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    overdue = next(d for d in decisions if d["semantic_key"] == "crediti:scaduti")
    quality = next(d for d in decisions if d["semantic_key"] == "crediti:qualita")
    assert overdue["autonomy_level"] == "L3"
    assert overdue["execution_status"] == "pending_approval"
    assert overdue["recommended_action"]["send"] is False
    assert overdue["metadata"]["outbound_enabled"] is False
    assert overdue["occurrence_count"] == 2
    assert quality["autonomy_level"] == "L1"
    assert quality["execution_status"] == "proposed"
    assert len(decisions) == 2
    assert "NOME RISERVATO" not in str(decisions)
    for collection in ("email_outbox", "gmail_outbox", "pec_outbox", "solleciti_inviati"):
        assert asyncio.run(db[collection].count_documents({})) == 0


def test_nessun_credito_o_dato_incompleto_non_crea_decisioni(monkeypatch):
    db = _db()
    asyncio.run(db["fatture_emesse"].insert_one({
        "data_scadenza": "2026-05-10", "totale": 100, "pagato": True,
    }))

    async def snapshot(database):
        return await leggi_snapshot_crediti(database, date(2026, 7, 20))

    monkeypatch.setattr(agent_mod, "leggi_snapshot_crediti", snapshot)
    asyncio.run(CreditiShadow().run(db))
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 0


def test_scheduler_registra_crediti_shadow(monkeypatch):
    from app.agents.orchestrator import SCHEDULE
    import app.scheduler as scheduler_mod

    assert SCHEDULE["CreditiShadow"] == 86400

    class Scheduler:
        def __init__(self):
            self.jobs, self.running = [], False

        def add_job(self, fn, *args, **kwargs):
            self.jobs.append((fn, args, kwargs))

        def start(self):
            self.running = True

    scheduler = Scheduler()
    monkeypatch.setattr(scheduler_mod, "scheduler", scheduler)
    scheduler_mod.start_scheduler()
    job = next(j for j in scheduler.jobs if j[2].get("id") == "ai_crediti_shadow")
    assert job[2]["hours"] == 24
    assert job[2]["next_run_time"] is not None
