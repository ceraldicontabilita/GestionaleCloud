"""Avvio coordinato degli import Drive esposti dalla pagina Documenti.

Tutti i canali passano dalla stessa coda del coordinatore documentale. Il click
manuale non apre piu' task concorrenti per fatture/cedolini/quietanze/etc.:
accoda i canali configurati e un unico worker li esegue in sequenza.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from app.services import (
    drive_cedolini_ingest,
    drive_corrispettivi_ingest,
    drive_documenti_ingest,
    drive_estratti_conto_ingest,
    drive_invoice_ingest,
    drive_quietanze_ingest,
)
from app.services.document_ingestion_coordinator import QUEUE_COLLECTION, run_one

logger = logging.getLogger(__name__)
_tasks: Dict[str, asyncio.Task] = {}

RunnerFactory = Callable[[], Awaitable[Dict[str, Any]]]


def _consume_task_result(name: str, task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Sincronizzazione Drive %s terminata con errore", name)


def _start_task(name: str, factory: Callable[[], Awaitable[Any]]) -> str:
    current = _tasks.get(name)
    if current is not None and not current.done():
        return "running"
    _tasks[name] = asyncio.create_task(factory())
    _tasks[name].add_done_callback(lambda task: _consume_task_result(name, task))
    return "started"


def build_runners(db: Any) -> Dict[str, RunnerFactory]:
    """Runner atomici riusati dal manuale e dal futuro tick schedulato."""
    runners: Dict[str, RunnerFactory] = {}

    if drive_invoice_ingest.is_configured():
        runners["fatture"] = lambda: drive_invoice_ingest.sync(db)
    if drive_cedolini_ingest.is_configured():
        runners["cedolini"] = lambda: drive_cedolini_ingest.sync(db)
    if drive_corrispettivi_ingest.is_configured():
        runners["corrispettivi"] = lambda: drive_corrispettivi_ingest.sync(db)
    if drive_quietanze_ingest.is_configured():
        runners["quietanze"] = lambda: drive_quietanze_ingest.sync(db)
    if drive_estratti_conto_ingest.is_configured():
        runners["estratti_conto"] = lambda: drive_estratti_conto_ingest.sync(db)

    for channel in drive_documenti_ingest.CANALI:
        if not (
            drive_documenti_ingest.is_enabled(channel)
            and drive_documenti_ingest.is_configured(channel)
        ):
            continue
        # Gli alias del registro sono nomi di dominio; il runner resta il
        # canale tecnico esistente per non duplicare parser o logica.
        area = {
            "bonifico": "bonifici_dipendenti",
            "dichiarazione_iva": "dichiarazioni_iva",
            "cartella_esattoriale": "cartelle_esattoriali",
            "avviso_bonario": "avvisi_bonari",
            "verbale": "verbali_auto",
        }.get(channel, channel)
        runners[area] = lambda channel=channel: drive_documenti_ingest.sync(db, channel)

    return runners


async def _enqueue_manual_jobs(db: Any, runners: Dict[str, RunnerFactory]) -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat()
    for area in runners:
        # Se lo stesso area e' gia' pendente/running non creiamo un doppione.
        existing = await db[QUEUE_COLLECTION].find_one(
            {"area": area, "status": {"$in": ["PENDING", "PARTIAL", "RUNNING"]}},
            {"_id": 0, "id": 1, "status": 1},
        )
        if existing:
            statuses[area] = str(existing.get("status") or "queued").lower()
            continue
        await db[QUEUE_COLLECTION].insert_one({
            "id": str(uuid.uuid4()),
            "run_key": f"manual:{area}:{uuid.uuid4()}",
            "area": area,
            "folder_id": None,
            "slot_index": None,
            "scheduled_for": now,
            "status": "PENDING",
            "attempt": 0,
            "checkpoint": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "heartbeat_at": None,
            "lease_until": None,
            "last_error": None,
            "result": None,
            "source": "manual_drive_sync",
        })
        statuses[area] = "queued"
    return statuses


async def _drain_manual_queue(db: Any) -> Dict[str, Any]:
    runners = build_runners(db)
    statuses = await _enqueue_manual_jobs(db, runners)
    results = []

    # Un solo run_one per iterazione. Se il worker e' gia' occupato da uno
    # scheduler, il manuale resta persistito in PENDING e verra' preso dopo.
    for _ in range(max(1, len(runners) * 3)):
        outcome = await run_one(db, runners)
        results.append(outcome)
        if outcome.get("status") in {"idle", "busy_local", "busy_global"}:
            break
        # Se un job e' PARTIAL lo lasciamo in coda, ma non cicliamo all'infinito
        # nello stesso click: la fairness del coordinatore dara' spazio agli altri.
        if outcome.get("status") == "partial":
            continue

    return {"status": "ok", "channels": statuses, "worker_results": results}


def start_all(db: Any) -> Dict[str, str]:
    """Accoda tutti i canali configurati; non crea import concorrenti."""
    runners = build_runners(db)
    if not runners:
        return {"documenti": "not_configured"}
    state = _start_task("all_serialized", lambda: _drain_manual_queue(db))
    return {area: ("queued" if state == "started" else "running") for area in runners}


async def start_all_after_response(db: Any) -> None:
    """Hook per FastAPI BackgroundTasks: la risposta HTTP parte prima del lavoro."""
    start_all(db)
