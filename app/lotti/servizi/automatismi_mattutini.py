"""Orchestratore persistente e idempotente degli automatismi mattutini Lotti.

Scheduler interno, recupero all'avvio e workflow GitHub usano lo stesso ingresso.
Il documento ``scheduler_executions`` con chiave job/data impedisce esecuzioni
doppie anche quando Render si risveglia mentre GitHub ritenta la chiamata.
"""

from datetime import datetime, timedelta, timezone
from time import monotonic
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from app.lotti.db import database as db


TZ_ROMA = ZoneInfo("Europe/Rome")
JOB_NAME = "haccp_morning"
LEASE_MINUTES = 30


def _ora_roma(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ_ROMA)


async def _claim(data_iso: str, source: str, actor: dict | None) -> tuple[bool, dict]:
    execution_id = f"{JOB_NAME}:{data_iso}"
    now = datetime.now(timezone.utc)
    doc = {
        "_id": execution_id,
        "job": JOB_NAME,
        "date": data_iso,
        "status": "running",
        "attempt": 1,
        "source": source,
        "requested_by": actor or {"id": source, "nome": source, "ruolo": "automazione"},
        "started_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "modules": {},
    }
    try:
        await db.scheduler_executions.insert_one(doc)
        return True, doc
    except DuplicateKeyError:
        existing = await db.scheduler_executions.find_one({"_id": execution_id}) or {}
        if existing.get("status") == "success":
            return False, existing

        stale_before = (now - timedelta(minutes=LEASE_MINUTES)).isoformat()
        result = await db.scheduler_executions.update_one(
            {
                "_id": execution_id,
                "$or": [
                    {"status": {"$in": ["failed", "partial"]}},
                    {"status": "running", "updated_at": {"$lt": stale_before}},
                ],
            },
            {
                "$set": {
                    "status": "running",
                    "source": source,
                    "requested_by": doc["requested_by"],
                    "started_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "error": None,
                },
                "$inc": {"attempt": 1},
            },
        )
        if result.modified_count:
            return True, await db.scheduler_executions.find_one({"_id": execution_id})
        return False, existing


async def _run_module(execution_id: str, name: str, fn) -> dict:
    started = monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = await fn()
        item = {
            "status": "success",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round((monotonic() - started) * 1000),
            "result": result,
        }
    except Exception as exc:
        item = {
            "status": "failed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round((monotonic() - started) * 1000),
            "error": str(exc),
        }
    await db.scheduler_executions.update_one(
        {"_id": execution_id},
        {"$set": {f"modules.{name}": item, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return item


async def run_morning_automation(
    source: str = "internal_scheduler",
    actor: dict | None = None,
    now: datetime | None = None,
) -> dict:
    local_now = _ora_roma(now)
    if source == "external_workflow" and (local_now.hour, local_now.minute) < (6, 45):
        return {
            "ok": True,
            "skipped": True,
            "reason": "too_early_europe_rome",
            "local_time": local_now.isoformat(),
        }

    data_iso = local_now.date().isoformat()
    acquired, execution = await _claim(data_iso, source, actor)
    if not acquired:
        running = execution.get("status") == "running"
        return {
            "ok": execution.get("status") == "success" or running,
            "skipped": True,
            "reason": "already_successful" if execution.get("status") == "success" else "already_running",
            "execution": {k: v for k, v in execution.items() if k != "_id"},
        }

    execution_id = execution["_id"]

    async def daily_haccp():
        from app.lotti.routers.haccp_auto import verifica_e_popola_oggi, marca_giorni_non_rilevati

        generated = await verifica_e_popola_oggi()
        missed = await marca_giorni_non_rilevati()
        return {"generazione": generated, "recupero_mancati": missed}

    async def employee_tasks():
        from app.lotti.routers.task_dipendenti import genera_task_giornalieri

        return await genera_task_giornalieri()

    async def reorder():
        from app.lotti.routers.ordini_fornitori import esegui_riordino_automatico

        return await esegui_riordino_automatico()

    modules = {
        "daily_haccp": await _run_module(execution_id, "daily_haccp", daily_haccp),
        "employee_tasks": await _run_module(execution_id, "employee_tasks", employee_tasks),
        "reorder": await _run_module(execution_id, "reorder", reorder),
    }
    failures = [name for name, item in modules.items() if item["status"] != "success"]
    status = "success" if not failures else "partial"
    finished = datetime.now(timezone.utc).isoformat()
    await db.scheduler_executions.update_one(
        {"_id": execution_id},
        {"$set": {
            "status": status,
            "finished_at": finished,
            "updated_at": finished,
            "failures": failures,
        }},
    )
    await db.scheduler_logs.insert_one({
        "job": "haccp_daily",
        "execution_id": execution_id,
        "timestamp": finished,
        "date": data_iso,
        "source": source,
        "success": status == "success",
        "status": status,
        "failures": failures,
        "modules": {name: item["status"] for name, item in modules.items()},
    })
    final = await db.scheduler_executions.find_one({"_id": execution_id}, {"_id": 0})
    return {"ok": status == "success", "skipped": False, "execution": final}


async def get_morning_status(data_iso: str | None = None) -> dict:
    data_iso = data_iso or _ora_roma().date().isoformat()
    execution = await db.scheduler_executions.find_one(
        {"_id": f"{JOB_NAME}:{data_iso}"}, {"_id": 0}
    )
    return {
        "date": data_iso,
        "timezone": "Europe/Rome",
        "expected_at": "07:00",
        "ok": bool(execution and execution.get("status") == "success"),
        "execution": execution,
    }
