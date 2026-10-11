"""Le 71 procedure ritirate restano spente anche senza la allowlist di Render."""

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from apscheduler.triggers.date import DateTrigger

import app.scheduler as scheduler_module
from app.scheduler_policy import RETIRED_PERIODIC_JOBS


KEPT_JOBS = {"drive_cartella_unica", "import_cartelle_drive", "enable_banking_giro", "gmail_full_scan", "mittenti_email_sync"}
ROOT = Path(__file__).resolve().parents[2]


def test_inventory_covers_all_periodic_registrations():
    periodic_ids = set()
    for path in (
        "app/scheduler.py", "app/hr/services/paghe_scheduler.py",
        "app/hr/services/scadenze_scheduler.py", "app/lotti/routers/scheduler.py",
    ):
        for node in ast.walk(ast.parse((ROOT / path).read_text())):
            if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "add_job":
                continue
            job_id = next((k.value for k in node.keywords if k.arg == "id"), None)
            if not isinstance(job_id, ast.Constant):
                continue  # inoltro della classe base
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value == "date":
                continue  # i due avvii singoli non sono procedure periodiche
            periodic_ids.add(job_id.value)
    assert len(RETIRED_PERIODIC_JOBS) == 69
    assert len(periodic_ids) == 74
    assert periodic_ids == RETIRED_PERIODIC_JOBS | KEPT_JOBS


@pytest.mark.parametrize("allowlist", [None, "", ", ", ",".join(sorted(RETIRED_PERIODIC_JOBS | KEPT_JOBS))])
def test_cannot_reactivate_retired_jobs_with_environment(monkeypatch, allowlist):
    if allowlist is None:
        monkeypatch.delenv("SCHEDULER_JOB_ALLOWLIST", raising=False)
    else:
        monkeypatch.setenv("SCHEDULER_JOB_ALLOWLIST", allowlist)
    monkeypatch.setenv("ENABLE_SCHEDULER", "true")
    scheduler = scheduler_module.SchedulerConLease(timezone="Europe/Rome")
    callback = AsyncMock()
    for job_id in RETIRED_PERIODIC_JOBS:
        assert scheduler.add_job(callback, "interval", seconds=1, id=job_id) is None
    assert scheduler.get_jobs() == []
    callback.assert_not_called()


@pytest.mark.parametrize("allowlist", [None, ",".join(sorted(KEPT_JOBS)), "drive_cartella_unica"])
def test_real_erp_start_registers_only_allowed_jobs(monkeypatch, caplog, allowlist):
    if allowlist is None:
        monkeypatch.delenv("SCHEDULER_JOB_ALLOWLIST", raising=False)
    else:
        monkeypatch.setenv("SCHEDULER_JOB_ALLOWLIST", allowlist)
    monkeypatch.delenv("ENABLE_BANKING_DAL", raising=False)
    scheduler = scheduler_module.SchedulerConLease(timezone="Europe/Rome")
    monkeypatch.setattr(scheduler_module, "scheduler", scheduler)
    # Avvio APScheduler reale in pausa: nessun callback puo' accedere ai dati.
    original_start = scheduler.start
    monkeypatch.setattr(scheduler, "start", lambda: original_start(paused=True))
    caplog.set_level("INFO", logger="app.scheduler")

    async def start_and_stop():
        scheduler_module.start_scheduler()
        try:
            jobs = scheduler.get_jobs()
            periodic = {job.id for job in jobs if not isinstance(job.trigger, DateTrigger)}
            expected = KEPT_JOBS if allowlist is None else set(allowlist.split(","))
            assert periodic == expected
            assert not {job.id for job in jobs} & RETIRED_PERIODIC_JOBS
            if allowlist is None:
                assert scheduler.get_job("calendario_conferma_massiva") is not None
            assert "Job effettivamente registrati" in caplog.text
            assert "Gmail Full Scan (tutte cartelle):" not in caplog.text
        finally:
            scheduler.shutdown(wait=False)
            await asyncio.sleep(0)

    asyncio.run(start_and_stop())


def test_hr_and_lotti_start_and_catchup_remain_off(monkeypatch):
    from app.hr.services import paghe_scheduler, scadenze_scheduler
    from app.lotti.routers import scheduler as lotti

    monkeypatch.delenv("SCHEDULER_JOB_ALLOWLIST", raising=False)
    monkeypatch.setenv("ENABLE_SCHEDULER", "true")
    scheduler = Mock(running=False)
    monkeypatch.setattr(lotti, "scheduler", scheduler)
    monkeypatch.setattr(lotti, "scheduler_started", False)
    monkeypatch.setattr(paghe_scheduler, "_scheduler", None)
    monkeypatch.setattr(scadenze_scheduler, "_scheduler", None)
    create_task = Mock(side_effect=AssertionError("Nessun recupero automatico all'avvio"))
    sleep = AsyncMock(side_effect=AssertionError("Il blocco deve precedere l'attesa"))
    monkeypatch.setattr(lotti.asyncio, "create_task", create_task)
    monkeypatch.setattr(lotti.asyncio, "sleep", sleep)

    async def verify():
        assert paghe_scheduler.start_scheduler() is None
        assert scadenze_scheduler.start_scheduler() is None
        result = await lotti.start_scheduler(_admin={})
        assert result["success"] is False
        assert "disattivate definitivamente" in result["message"]
        await lotti._catchup_jobs_mancanti()
        await lotti._lettura_articoli_ai_dopo_avvio()

    asyncio.run(verify())
    scheduler.add_job.assert_not_called()
    scheduler.start.assert_not_called()
    create_task.assert_not_called()
    sleep.assert_not_called()
    assert not lotti.scheduler_started


def test_manual_command_still_runs_retired_job_callback(monkeypatch):
    from app.lotti.routers import scheduler as lotti

    callback = AsyncMock()
    monkeypatch.setattr(lotti, "job_aggiorna_riferimenti_fatture", callback)
    result = asyncio.run(lotti.run_aggiorna_fatture_now(_admin={}))
    assert result["success"] is True
    callback.assert_awaited_once()
