"""Acquisti shadow: prezzo/concentrazione senza nomi, scorte o ordini."""

import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

import app.agents.acquisti_shadow as agent_mod
from app.agents.acquisti_shadow import AcquistiShadow
from app.services.acquisti_shadow_service import leggi_snapshot_acquisti


def _db():
    return AsyncMongoMockClient()["acquisti_shadow_test"]


async def _seed(db):
    await db["acquisti_prodotti"].insert_many([
        {"prodotto_id": "P1", "data": "2026-06-01", "prezzo_unitario": 10, "unita_misura": "KG", "fornitore": "RISERVATO"},
        {"prodotto_id": "P1", "data": "2026-06-20", "prezzo_unitario": 10, "unita_misura": "KG", "fornitore": "RISERVATO"},
        {"prodotto_id": "P1", "data": "2026-07-10", "prezzo_unitario": 12, "unita_misura": "KG", "fornitore": "RISERVATO"},
        {"prodotto_id": "P2", "data": "2026-06-01", "prezzo_unitario": 5, "unita_misura": "PZ", "fornitore": "A"},
        {"prodotto_id": "P2", "data": "2026-07-01", "prezzo_unitario": 6, "unita_misura": "KG", "fornitore": "B"},
        {"prodotto_id": "", "data": "2026-07-01", "prezzo_unitario": 3},
    ])


def test_snapshot_aggregato_non_espone_prodotti_o_fornitori():
    db = _db()
    asyncio.run(_seed(db))
    snapshot = asyncio.run(leggi_snapshot_acquisti(db, date(2026, 7, 20))).to_dict()
    assert snapshot["products_observed"] == 2
    assert snapshot["price_increase_products"] == 1
    assert snapshot["max_price_increase_pct"] == 20.0
    assert snapshot["single_supplier_products"] == 1
    assert snapshot["records_excluded"] == 1
    assert snapshot["reorder_supported"] is False
    assert "RISERVATO" not in str(snapshot)


def test_agente_l1_idempotente_non_crea_ordini_o_magazzino(monkeypatch):
    db = _db()
    asyncio.run(_seed(db))

    async def snapshot(database):
        return await leggi_snapshot_acquisti(database, date(2026, 7, 20))

    monkeypatch.setattr(agent_mod, "leggi_snapshot_acquisti", snapshot)
    asyncio.run(AcquistiShadow().run(db))
    asyncio.run(AcquistiShadow().run(db))
    decision = asyncio.run(db["ai_decisions"].find_one({}, {"_id": 0}))
    assert decision["autonomy_level"] == "L1"
    assert decision["execution_status"] == "proposed"
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 1
    for collection in ("ordini", "ordini_acquisto", "warehouse_inventory", "magazzino_movimenti"):
        assert asyncio.run(db[collection].count_documents({})) == 0


def test_scheduler_registra_acquisti_shadow(monkeypatch):
    from app.agents.orchestrator import SCHEDULE
    import app.scheduler as scheduler_mod
    assert SCHEDULE["AcquistiShadow"] == 86400

    class Scheduler:
        def __init__(self): self.jobs, self.running = [], False
        def add_job(self, fn, *args, **kwargs): self.jobs.append((fn, args, kwargs))
        def start(self): self.running = True

    scheduler = Scheduler()
    monkeypatch.setattr(scheduler_mod, "scheduler", scheduler)
    scheduler_mod.start_scheduler()
    job = next(j for j in scheduler.jobs if j[2].get("id") == "ai_acquisti_shadow")
    assert job[2]["hours"] == 24
