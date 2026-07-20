"""Agente Tesoreria: aggregati minimizzati, shadow mode e idempotenza."""

import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

import app.agents.tesoreria_shadow as agente_mod
from app.agents.tesoreria_shadow import TesoreriaShadow
from app.services.tesoreria_shadow_service import leggi_snapshot_tesoreria


def _db():
    return AsyncMongoMockClient()["tesoreria_shadow_test"]


async def _semina(db):
    await db["scadenziario_fornitori"].insert_many([
        {
            "id": "scaduta-1",
            "data_scadenza": "2026-07-10",
            "importo_rata": "100.00",
            "pagato": False,
            "stato": "aperta",
            "fornitore": "DATO CHE NON DEVE USCIRE",
        },
        {
            "id": "futura-1",
            "data_scadenza": "2026-07-25",
            "importo_rata": "200.00",
            "pagato": False,
            "stato": "aperta",
            "fornitore": "ALTRO DATO CHE NON DEVE USCIRE",
        },
        {
            "id": "futura-2",
            "data_scadenza": "2026-08-15",
            "importo_residuo": "1.300,50",
            "pagato": False,
            "stato": "aperta",
        },
        {
            "id": "gia-pagata",
            "data_scadenza": "2026-07-22",
            "importo": 999,
            "pagato": True,
            "stato": "pagata",
        },
    ])


def test_servizio_restituisce_solo_aggregati_minimizzati():
    db = _db()
    asyncio.run(_semina(db))
    snapshot = asyncio.run(leggi_snapshot_tesoreria(
        db, reference_date=date(2026, 7, 20), horizon_days=30
    )).to_dict()

    assert snapshot["overdue"]["count"] == 1
    assert snapshot["overdue"]["total"] == "100.00"
    assert snapshot["upcoming"]["count"] == 2
    assert snapshot["upcoming"]["total"] == "1500.50"
    assert "fornitore" not in str(snapshot).lower()


def test_agente_crea_due_decisioni_shadow_senza_azioni_di_business(monkeypatch):
    db = _db()
    asyncio.run(_semina(db))

    async def snapshot_fisso(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_fisso)
    asyncio.run(TesoreriaShadow().run(db))

    decisioni = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    assert len(decisioni) == 2
    scaduta = next(d for d in decisioni if "scadute" in d["objective"])
    futura = next(d for d in decisioni if "prossimi" in d["objective"])
    assert scaduta["execution_status"] == "pending_approval"
    assert futura["execution_status"] == "proposed"
    assert all(d["metadata"]["shadow_mode"] is True for d in decisioni)
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0
    assert asyncio.run(db["operazioni_da_confermare"].count_documents({})) == 0


def test_riesecuzione_stessa_fotografia_non_duplica(monkeypatch):
    db = _db()
    asyncio.run(_semina(db))

    async def snapshot_fisso(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_fisso)
    asyncio.run(TesoreriaShadow().run(db))
    asyncio.run(TesoreriaShadow().run(db))

    assert asyncio.run(db["ai_decisions"].count_documents({})) == 2
    assert asyncio.run(db["ai_decision_events"].count_documents({"event": "decisione_creata"})) == 2


def test_nessuna_scadenza_non_genera_decisioni(monkeypatch):
    db = _db()

    async def snapshot_vuoto(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_vuoto)
    asyncio.run(TesoreriaShadow().run(db))
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 0


def test_scheduler_registra_tesoreria_shadow_ogni_ora(monkeypatch):
    import app.scheduler as scheduler_mod

    class _SchedulerFinto:
        def __init__(self):
            self.jobs = []
            self.running = False

        def add_job(self, funzione, *args, **kwargs):
            self.jobs.append((funzione, args, kwargs))

        def start(self):
            self.running = True

    schedulatore = _SchedulerFinto()
    monkeypatch.setattr(scheduler_mod, "scheduler", schedulatore)
    scheduler_mod.start_scheduler()

    job = next(item for item in schedulatore.jobs if item[2].get("id") == "ai_tesoreria_shadow")
    assert job[1] == ("interval",)
    assert job[2]["hours"] == 1
    assert job[2]["next_run_time"] is not None
    assert schedulatore.running is True
