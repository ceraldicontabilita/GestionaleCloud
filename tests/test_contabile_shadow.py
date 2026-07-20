"""Agente Contabile: minimizzazione, fail-closed, idempotenza e scheduler."""

import asyncio
from datetime import datetime, timezone

from mongomock_motor import AsyncMongoMockClient

import app.agents.contabile_shadow as agent_mod
from app.agents.contabile_shadow import ContabileShadow
from app.services.contabile_shadow_service import leggi_snapshot_contabile


def _db():
    return AsyncMongoMockClient()["contabile_shadow_test"]


async def _report(db, checks, eseguito_at="2026-07-20T08:00:00+00:00"):
    await db["collaudo_report"].insert_one({
        "id": "collaudo-sintetico",
        "eseguito_at": eseguito_at,
        "checks": checks,
    })


def test_servizio_espone_solo_aggregati_senza_esempi_o_anagrafiche():
    db = _db()
    asyncio.run(_report(db, [{
        "nome": "fatture_banca_senza_estratto_conto",
        "violazioni": 2,
        "descrizione": "DATO LIBERO DA NON ESPORRE",
        "esempi": [{"fornitore": "PERSONA RISERVATA", "importo": 100}],
    }]))
    snapshot = asyncio.run(leggi_snapshot_contabile(
        db, reference_time=datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    )).to_dict()

    assert snapshot["violazioni_totali"] == 2
    assert snapshot["violazioni_critiche"] == 2
    serializzato = str(snapshot)
    assert "PERSONA RISERVATA" not in serializzato
    assert "DATO LIBERO" not in serializzato
    assert "esempi" not in serializzato


def test_anomalie_creano_una_proposta_l3_senza_scritture_business(monkeypatch):
    db = _db()
    asyncio.run(_report(db, [{
        "nome": "movimenti_prima_nota_malformati", "violazioni": 3,
    }]))

    async def snapshot_fisso(database):
        return await leggi_snapshot_contabile(
            database, reference_time=datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
        )

    monkeypatch.setattr(agent_mod, "leggi_snapshot_contabile", snapshot_fisso)
    asyncio.run(ContabileShadow().run(db))
    asyncio.run(ContabileShadow().run(db))

    decisioni = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    assert len(decisioni) == 1
    assert decisioni[0]["autonomy_level"] == "L3"
    assert decisioni[0]["execution_status"] == "pending_approval"
    assert decisioni[0]["metadata"]["shadow_mode"] is True
    for collection in ("prima_nota_banca", "prima_nota_cassa", "scritture_contabili", "invoices"):
        assert asyncio.run(db[collection].count_documents({})) == 0


def test_report_pulito_e_recente_non_genera_rumore(monkeypatch):
    db = _db()
    asyncio.run(_report(db, [{"nome": "movimenti_prima_nota_malformati", "violazioni": 0}]))

    async def snapshot_fisso(database):
        return await leggi_snapshot_contabile(
            database, reference_time=datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
        )

    monkeypatch.setattr(agent_mod, "leggi_snapshot_contabile", snapshot_fisso)
    asyncio.run(ContabileShadow().run(db))
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 0


def test_report_assente_genera_solo_raccomandazione_l1():
    db = _db()
    asyncio.run(ContabileShadow().run(db))
    decisione = asyncio.run(db["ai_decisions"].find_one({}, {"_id": 0}))
    assert decisione["autonomy_level"] == "L1"
    assert decisione["execution_status"] == "proposed"
    assert decisione["recommended_action"]["type"] == "recommendation"


def test_report_obsoleto_non_autorizza_correzioni(monkeypatch):
    db = _db()
    asyncio.run(_report(db, [{"nome": "badge_status_incoerente", "violazioni": 0}], "2026-07-18T00:00:00+00:00"))

    async def snapshot_fisso(database):
        return await leggi_snapshot_contabile(
            database, reference_time=datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
        )

    monkeypatch.setattr(agent_mod, "leggi_snapshot_contabile", snapshot_fisso)
    asyncio.run(ContabileShadow().run(db))
    decisione = asyncio.run(db["ai_decisions"].find_one({}, {"_id": 0}))
    assert decisione["autonomy_level"] == "L1"
    assert decisione["facts"][0]["report_obsoleto"] is True


def test_orchestratore_e_scheduler_registrano_contabile(monkeypatch):
    from app.agents.orchestrator import SCHEDULE
    import app.scheduler as scheduler_mod

    assert SCHEDULE["ContabileShadow"] == 21600

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
    job = next(item for item in schedulatore.jobs if item[2].get("id") == "ai_contabile_shadow")
    assert job[1] == ("interval",)
    assert job[2]["hours"] == 6
    assert job[2]["next_run_time"] is not None
