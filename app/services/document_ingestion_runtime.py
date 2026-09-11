"""Runtime bridge tra lo scheduler storico e il coordinatore documentale.

Non riscrive in blocco ``app/scheduler.py``. I job Drive gia' registrati restano
come sveglie compatibili, ma quando sono invocati *dallo scheduler* non eseguono
piu' direttamente il parser: chiamano questo tick, che:

1. costruisce/aggiorna gli slot persistenti da 30 minuti;
2. accoda l'ultima occorrenza giornaliera dovuta per ogni cartella;
3. esegue un solo job tramite il worker globale.

Le chiamate manuali agli stessi ``sync()`` continuano invece a usare il motore
originale, cosi' gli endpoint esistenti non cambiano contratto.
"""

from __future__ import annotations

import inspect
import logging
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from importlib import import_module
from typing import Any, Awaitable, Callable, Dict

from app.services.document_ingestion_coordinator import (
    MAX_SLOTS,
    QUEUE_COLLECTION,
    SCHEDULE_COLLECTION,
    ensure_folder_schedule,
    run_one,
    slot_time_for_day,
)
from app.services.drive_folder_registry import get_configured_entries

logger = logging.getLogger(__name__)

Runner = Callable[[], Awaitable[Dict[str, Any]] | Dict[str, Any]]
_DIRECT_SYNCS: Dict[str, Callable[..., Any]] = {}
_INSTALLED = False

_SPECIALIST_MODULES = {
    "fatture": "app.services.drive_invoice_ingest",
    "cedolini": "app.services.drive_cedolini_ingest",
    "corrispettivi": "app.services.drive_corrispettivi_ingest",
    "quietanze": "app.services.drive_quietanze_ingest",
    "estratti_conto": "app.services.drive_estratti_conto_ingest",
}

_GENERIC_CHANNELS = {
    "bonifici_dipendenti": "bonifico",
    "dichiarazioni_iva": "dichiarazione_iva",
    "cartelle_esattoriali": "cartella_esattoriale",
    "avvisi_bonari": "avviso_bonario",
    "verbali_auto": "verbale",
}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _run_key(area: str, scheduled_for: datetime) -> str:
    local = scheduled_for.astimezone()
    return f"{area}:{local:%Y-%m-%d}:{local:%H%M}"


def _called_from_scheduler() -> bool:
    """Distingue la sveglia APScheduler da endpoint/manuale senza cambiare API."""
    for frame in inspect.stack(context=0)[1:8]:
        filename = (frame.filename or "").replace("\\", "/")
        if filename.endswith("/app/scheduler.py"):
            return True
    return False


def _direct_specialist_runners(db: Any) -> Dict[str, Runner]:
    runners: Dict[str, Runner] = {}
    for area, module_name in _SPECIALIST_MODULES.items():
        direct = _DIRECT_SYNCS.get(area)
        module = import_module(module_name)
        is_configured = getattr(module, "is_configured", None)
        if direct and (not callable(is_configured) or is_configured()):
            runners[area] = lambda direct=direct: direct(db)

    from app.services import drive_documenti_ingest
    for area, channel in _GENERIC_CHANNELS.items():
        if drive_documenti_ingest.is_enabled(channel) and drive_documenti_ingest.is_configured(channel):
            runners[area] = lambda channel=channel: drive_documenti_ingest.sync(db, channel)

    return runners


def runners_for_db(db: Any) -> Dict[str, Runner]:
    """Runner realmente eseguibili dal worker seriale."""
    return _direct_specialist_runners(db)


async def _ensure_runnable_schedule(db: Any, runners: Dict[str, Runner]) -> None:
    configured = get_configured_entries()
    by_area = {str(item.get("area") or "").lower(): item for item in configured}
    folders = []
    for area in sorted(runners):
        item = by_area.get(area)
        if not item or not item.get("folder_id"):
            continue
        folders.append({
            "area": area,
            "folder_id": item.get("folder_id"),
            "label": item.get("label") or area,
            "enabled": True,
        })
    if folders:
        await ensure_folder_schedule(db, folders)


async def _enqueue_latest_due_occurrences(db: Any, runners: Dict[str, Runner]) -> Dict[str, int]:
    """Accoda l'ultima lettura giornaliera dovuta, anche dopo riavvio/notte.

    Se una cartella ha ancora un job aperto non creiamo il job del giorno
    successivo: la scansione e' incrementale e quel job, quando riparte, vede
    comunque tutti i file nuovi. In questo modo l'arretrato non esplode.
    """
    from zoneinfo import ZoneInfo

    rome = ZoneInfo("Europe/Rome")
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(rome)
    rows = await db[SCHEDULE_COLLECTION].find({"enabled": True}, {"_id": 0}).to_list(MAX_SLOTS)
    stats = {"queued": 0, "already_open": 0, "already_seen": 0, "without_runner": 0}

    for row in rows:
        area = str(row.get("area") or "").lower()
        if area not in runners:
            stats["without_runner"] += 1
            continue
        slot_index = int(row.get("slot_index", -1))
        if not 0 <= slot_index < MAX_SLOTS:
            continue

        scheduled_local = slot_time_for_day(now_local, slot_index)
        if scheduled_local > now_local:
            scheduled_local -= timedelta(days=1)
        scheduled_utc = scheduled_local.astimezone(timezone.utc)
        run_key = f"{area}:{scheduled_local:%Y-%m-%d}:{scheduled_local:%H%M}"

        open_job = await db[QUEUE_COLLECTION].find_one(
            {"area": area, "status": {"$in": ["PENDING", "PARTIAL", "RUNNING"]}},
            {"_id": 0, "id": 1},
        )
        if open_job:
            stats["already_open"] += 1
            continue
        seen = await db[QUEUE_COLLECTION].find_one({"run_key": run_key}, {"_id": 0, "id": 1})
        if seen:
            stats["already_seen"] += 1
            continue

        now_iso = _iso(now_utc)
        await db[QUEUE_COLLECTION].insert_one({
            "id": str(uuid.uuid4()),
            "run_key": run_key,
            "area": area,
            "folder_id": row.get("folder_id"),
            "slot_index": slot_index,
            "scheduled_for": _iso(scheduled_utc),
            "status": "PENDING",
            "attempt": 0,
            "checkpoint": None,
            "created_at": now_iso,
            "updated_at": now_iso,
            "started_at": None,
            "finished_at": None,
            "heartbeat_at": None,
            "lease_until": None,
            "last_error": None,
            "result": None,
            "source": "daily_folder_slot",
        })
        stats["queued"] += 1
    return stats


async def coordinator_tick(db: Any) -> Dict[str, Any]:
    runners = runners_for_db(db)
    if not runners:
        return {"status": "no_runners"}
    await _ensure_runnable_schedule(db, runners)
    queue = await _enqueue_latest_due_occurrences(db, runners)
    worker = await run_one(db, runners)
    return {"status": "ok", "queue": queue, "worker": worker}


def install_legacy_scheduler_bridge() -> None:
    """Converte i vecchi sync Drive in sveglie del coordinatore solo da scheduler."""
    global _INSTALLED
    if _INSTALLED:
        return

    for area, module_name in _SPECIALIST_MODULES.items():
        module = import_module(module_name)
        original = getattr(module, "sync", None)
        if not callable(original):
            continue
        _DIRECT_SYNCS[area] = original

        @wraps(original)
        async def bridged_sync(db, *args, __original=original, **kwargs):
            if not _called_from_scheduler():
                value = __original(db, *args, **kwargs)
                return await value if inspect.isawaitable(value) else value
            return await coordinator_tick(db)

        module.sync = bridged_sync

    # Anche il vecchio job di solo indice (ogni 15 min) diventa una sveglia
    # di sicurezza. La chiamata manuale a get_status resta puramente read-only.
    try:
        index_module = import_module("app.services.drive_document_index")
        original_status = getattr(index_module, "get_status", None)
        if callable(original_status):
            @wraps(original_status)
            def bridged_status(*args, __original=original_status, **kwargs):
                # get_status e' sincrono e lo scheduler lo esegue in to_thread;
                # non possiamo await qui. Lasciamo quindi la sveglia ai sync
                # specialistici e preserviamo la semantica read-only.
                return __original(*args, **kwargs)
            index_module.get_status = bridged_status
    except Exception:
        logger.exception("Impossibile installare il bridge indice Drive")

    _INSTALLED = True
    logger.info("Bridge scheduler documentale installato: Drive serializzato tramite coda persistente")
