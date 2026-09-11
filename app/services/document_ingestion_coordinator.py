"""Coordinatore unico degli ingest documentali schedulati.

Obiettivi:
- massimo 48 cartelle operative, una finestra ogni 30 minuti nelle 24 ore;
- lo slot rende una cartella *eleggibile*, non forza l'avvio se un altro job e' attivo;
- un solo worker documentale globale (concurrency=1);
- coda persistente, lease + heartbeat e recupero dopo crash;
- checkpoint/result persistiti per consentire ingest a lotti senza perdere il lavoro;
- fairness: un job parziale torna in coda dietro ai job gia' in attesa.

Il coordinatore non decide come si interpreta un PDF: i runner continuano a essere
le pipeline di dominio esistenti. Qui si governa soltanto quando e con quale
mutua esclusione vengono eseguite.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ROME = ZoneInfo("Europe/Rome")
QUEUE_COLLECTION = "document_ingestion_jobs"
SCHEDULE_COLLECTION = "document_ingestion_schedule"
WORKER_COLLECTION = "document_ingestion_worker"
WORKER_KEY = "document_ingestion_global"
SLOT_MINUTES = 30
MAX_SLOTS = 48
DEFAULT_LEASE_SECONDS = 20 * 60
DEFAULT_HEARTBEAT_SECONDS = 60

Runner = Callable[[], Awaitable[Dict[str, Any]] | Dict[str, Any]]


@dataclass(frozen=True)
class FolderSlot:
    area: str
    slot_index: int
    folder_id: Optional[str] = None
    enabled: bool = True

    @property
    def hour(self) -> int:
        return (self.slot_index * SLOT_MINUTES) // 60

    @property
    def minute(self) -> int:
        return (self.slot_index * SLOT_MINUTES) % 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def slot_time_for_day(day_local: datetime, slot_index: int) -> datetime:
    if slot_index < 0 or slot_index >= MAX_SLOTS:
        raise ValueError(f"slot_index fuori intervallo 0..{MAX_SLOTS - 1}: {slot_index}")
    local = day_local.astimezone(ROME)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(minutes=slot_index * SLOT_MINUTES)


def _stable_slot_order(areas: Iterable[str]) -> list[str]:
    # Ordinamento deterministico: l'assegnazione resta stabile finche' non cambia
    # il catalogo. Le assegnazioni gia' persistite non vengono comunque mutate.
    return sorted({str(area).strip().lower() for area in areas if str(area).strip()})


async def ensure_folder_schedule(
    db: Any,
    folders: Iterable[Mapping[str, Any]],
) -> list[FolderSlot]:
    """Garantisce uno slot distinto a ogni cartella, senza riscrivere quelli esistenti."""
    normalized: dict[str, Mapping[str, Any]] = {}
    for item in folders:
        area = str(item.get("area") or "").strip().lower()
        if not area:
            continue
        normalized[area] = item

    if len(normalized) > MAX_SLOTS:
        raise ValueError(
            f"Sono configurate {len(normalized)} cartelle automatiche: il massimo e' {MAX_SLOTS}."
        )

    existing = await db[SCHEDULE_COLLECTION].find({}, {"_id": 0}).to_list(MAX_SLOTS * 2)
    by_area = {str(row.get("area") or "").lower(): row for row in existing if row.get("area")}
    used_slots = {
        int(row["slot_index"])
        for row in existing
        if isinstance(row.get("slot_index"), int) and 0 <= int(row["slot_index"]) < MAX_SLOTS
    }

    free_slots = [idx for idx in range(MAX_SLOTS) if idx not in used_slots]
    now = _iso(utcnow())

    for area in _stable_slot_order(normalized):
        item = normalized[area]
        current = by_area.get(area)
        if current is None:
            if not free_slots:
                raise ValueError("Nessuno slot da 30 minuti disponibile")
            slot_index = free_slots.pop(0)
            row = {
                "id": f"folder-slot:{area}",
                "area": area,
                "folder_id": item.get("folder_id"),
                "label": item.get("label") or area,
                "slot_index": slot_index,
                "enabled": bool(item.get("enabled", True)),
                "created_at": now,
                "updated_at": now,
            }
            await db[SCHEDULE_COLLECTION].insert_one(row)
            by_area[area] = row
        else:
            patch = {
                "folder_id": item.get("folder_id") or current.get("folder_id"),
                "label": item.get("label") or current.get("label") or area,
                "enabled": bool(item.get("enabled", current.get("enabled", True))),
                "updated_at": now,
            }
            await db[SCHEDULE_COLLECTION].update_one({"area": area}, {"$set": patch})
            current.update(patch)

    slots: list[FolderSlot] = []
    for area, row in by_area.items():
        if area not in normalized:
            continue
        slots.append(
            FolderSlot(
                area=area,
                slot_index=int(row["slot_index"]),
                folder_id=row.get("folder_id"),
                enabled=bool(row.get("enabled", True)),
            )
        )
    return sorted(slots, key=lambda item: item.slot_index)


def _run_key(area: str, scheduled_for: datetime) -> str:
    local = scheduled_for.astimezone(ROME)
    return f"{area}:{local:%Y-%m-%d}:{local:%H%M}"


async def enqueue_due_slots(
    db: Any,
    *,
    now: Optional[datetime] = None,
    grace_minutes: int = 45,
) -> Dict[str, Any]:
    """Accoda gli slot maturati e non ancora rappresentati in coda.

    Il grace period consente a un processo riavviato di recuperare lo slot appena
    perso. Un job gia' creato non viene duplicato grazie alla chiave deterministica.
    """
    now_utc = (now or utcnow()).astimezone(timezone.utc)
    now_local = now_utc.astimezone(ROME)
    rows = await db[SCHEDULE_COLLECTION].find({"enabled": True}, {"_id": 0}).to_list(MAX_SLOTS)
    queued = 0
    existing = 0
    skipped_future = 0

    for row in rows:
        slot_index = int(row.get("slot_index", -1))
        if not 0 <= slot_index < MAX_SLOTS:
            continue
        scheduled_local = slot_time_for_day(now_local, slot_index)
        scheduled_utc = scheduled_local.astimezone(timezone.utc)
        age = now_utc - scheduled_utc
        if age.total_seconds() < 0:
            skipped_future += 1
            continue
        if age > timedelta(minutes=grace_minutes):
            continue

        area = str(row.get("area") or "").strip().lower()
        run_key = _run_key(area, scheduled_utc)
        present = await db[QUEUE_COLLECTION].find_one({"run_key": run_key}, {"_id": 0, "id": 1})
        if present:
            existing += 1
            continue
        payload = {
            "id": str(uuid.uuid4()),
            "run_key": run_key,
            "area": area,
            "folder_id": row.get("folder_id"),
            "slot_index": slot_index,
            "scheduled_for": _iso(scheduled_utc),
            "status": "PENDING",
            "attempt": 0,
            "checkpoint": None,
            "created_at": _iso(now_utc),
            "updated_at": _iso(now_utc),
            "started_at": None,
            "finished_at": None,
            "heartbeat_at": None,
            "lease_until": None,
            "last_error": None,
            "result": None,
        }
        await db[QUEUE_COLLECTION].insert_one(payload)
        queued += 1

    return {
        "status": "ok",
        "queued": queued,
        "already_queued": existing,
        "future_slots": skipped_future,
        "checked": len(rows),
    }


async def recover_expired_jobs(db: Any, *, now: Optional[datetime] = None) -> int:
    """Rimette in coda i RUNNING rimasti senza heartbeat/lease dopo un crash."""
    now_utc = (now or utcnow()).astimezone(timezone.utc)
    rows = await db[QUEUE_COLLECTION].find({"status": "RUNNING"}, {"_id": 0}).to_list(200)
    recovered = 0
    for row in rows:
        lease_raw = row.get("lease_until")
        if not lease_raw:
            expired = True
        else:
            try:
                expired = datetime.fromisoformat(str(lease_raw)).astimezone(timezone.utc) <= now_utc
            except ValueError:
                expired = True
        if not expired:
            continue
        result = await db[QUEUE_COLLECTION].update_one(
            {"id": row["id"], "status": "RUNNING"},
            {"$set": {
                "status": "PENDING",
                "lease_until": None,
                "heartbeat_at": None,
                "updated_at": _iso(now_utc),
                "last_error": row.get("last_error") or "lease_scaduta_recuperata",
            }},
        )
        if getattr(result, "modified_count", 1):
            recovered += 1
    return recovered


async def _claim_worker_lease(
    db: Any,
    *,
    owner: str,
    lease_seconds: int,
) -> bool:
    """Lease globale cross-process. Non sostituisce il lock asyncio locale."""
    now = utcnow()
    current = await db[WORKER_COLLECTION].find_one({"key": WORKER_KEY}, {"_id": 0})
    if current:
        lease_raw = current.get("lease_until")
        active = False
        if lease_raw:
            try:
                active = datetime.fromisoformat(str(lease_raw)).astimezone(timezone.utc) > now
            except ValueError:
                active = False
        if active and current.get("owner") != owner:
            return False
        selector = {"key": WORKER_KEY, "owner": current.get("owner")}
    else:
        selector = {"key": WORKER_KEY}

    # L'adattatore DB del progetto supporta find_one_and_update; il selector
    # impedisce a due owner di sostituirsi se lo stato e' cambiato nel frattempo.
    claimed = await db[WORKER_COLLECTION].find_one_and_update(
        selector,
        {"$set": {
            "key": WORKER_KEY,
            "owner": owner,
            "heartbeat_at": _iso(now),
            "lease_until": _iso(now + timedelta(seconds=lease_seconds)),
            "updated_at": _iso(now),
        }},
        upsert=current is None,
        return_document=True,
    )
    return bool(claimed and claimed.get("owner") == owner)


async def _release_worker_lease(db: Any, owner: str) -> None:
    await db[WORKER_COLLECTION].update_one(
        {"key": WORKER_KEY, "owner": owner},
        {"$set": {
            "owner": None,
            "lease_until": None,
            "heartbeat_at": None,
            "updated_at": _iso(utcnow()),
        }},
    )


async def _next_pending_job(db: Any) -> Optional[Dict[str, Any]]:
    rows = await db[QUEUE_COLLECTION].find(
        {"status": {"$in": ["PENDING", "PARTIAL"]}}, {"_id": 0}
    ).to_list(500)
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            str(row.get("scheduled_for") or ""),
            int(row.get("attempt") or 0),
            str(row.get("created_at") or ""),
        )
    )
    return rows[0]


async def _claim_job(db: Any, job: Mapping[str, Any], *, lease_seconds: int) -> Optional[Dict[str, Any]]:
    now = utcnow()
    previous_status = str(job.get("status") or "PENDING")
    claimed = await db[QUEUE_COLLECTION].find_one_and_update(
        {"id": job["id"], "status": previous_status},
        {"$set": {
            "status": "RUNNING",
            "started_at": job.get("started_at") or _iso(now),
            "heartbeat_at": _iso(now),
            "lease_until": _iso(now + timedelta(seconds=lease_seconds)),
            "updated_at": _iso(now),
        }, "$inc": {"attempt": 1}},
        return_document=True,
    )
    return claimed


async def _heartbeat_loop(
    db: Any,
    *,
    owner: str,
    job_id: str,
    lease_seconds: int,
    interval_seconds: int,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            break
        except asyncio.TimeoutError:
            now = utcnow()
            lease_until = _iso(now + timedelta(seconds=lease_seconds))
            await db[QUEUE_COLLECTION].update_one(
                {"id": job_id, "status": "RUNNING"},
                {"$set": {
                    "heartbeat_at": _iso(now),
                    "lease_until": lease_until,
                    "updated_at": _iso(now),
                }},
            )
            await db[WORKER_COLLECTION].update_one(
                {"key": WORKER_KEY, "owner": owner},
                {"$set": {
                    "heartbeat_at": _iso(now),
                    "lease_until": lease_until,
                    "updated_at": _iso(now),
                }},
            )


_local_worker_lock = asyncio.Lock()


async def run_one(
    db: Any,
    runners: Mapping[str, Runner],
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
) -> Dict[str, Any]:
    """Esegue al massimo un job. Mai due cartelle in parallelo."""
    if _local_worker_lock.locked():
        return {"status": "busy_local"}

    async with _local_worker_lock:
        await recover_expired_jobs(db)
        owner = f"worker:{uuid.uuid4()}"
        if not await _claim_worker_lease(db, owner=owner, lease_seconds=lease_seconds):
            return {"status": "busy_global"}

        try:
            pending = await _next_pending_job(db)
            if pending is None:
                return {"status": "idle"}
            claimed = await _claim_job(db, pending, lease_seconds=lease_seconds)
            if not claimed:
                return {"status": "race_lost"}

            area = str(claimed.get("area") or "")
            runner = runners.get(area)
            if runner is None:
                await db[QUEUE_COLLECTION].update_one(
                    {"id": claimed["id"], "status": "RUNNING"},
                    {"$set": {
                        "status": "ERROR",
                        "last_error": f"runner_non_configurato:{area}",
                        "finished_at": _iso(utcnow()),
                        "lease_until": None,
                        "updated_at": _iso(utcnow()),
                    }},
                )
                return {"status": "error", "area": area, "reason": "runner_non_configurato"}

            stop = asyncio.Event()
            heartbeat = asyncio.create_task(
                _heartbeat_loop(
                    db,
                    owner=owner,
                    job_id=claimed["id"],
                    lease_seconds=lease_seconds,
                    interval_seconds=max(5, heartbeat_seconds),
                    stop=stop,
                )
            )
            try:
                value = runner()
                result = await value if inspect.isawaitable(value) else value
                result = dict(result or {})
                partial = bool(result.get("partial") or result.get("has_more"))
                final_status = "PARTIAL" if partial else "DONE"
                patch = {
                    "status": final_status,
                    "result": result,
                    "checkpoint": result.get("checkpoint", claimed.get("checkpoint")),
                    "finished_at": None if partial else _iso(utcnow()),
                    "heartbeat_at": None,
                    "lease_until": None,
                    "updated_at": _iso(utcnow()),
                    "last_error": None,
                }
                if partial:
                    # Il job parziale viene ricreato in coda con una data di
                    # creazione nuova: in presenza di altre cartelle pendenti
                    # queste ottengono il worker prima del lotto successivo.
                    patch["scheduled_for"] = _iso(utcnow() + timedelta(seconds=1))
                    patch["created_at"] = _iso(utcnow())
                await db[QUEUE_COLLECTION].update_one(
                    {"id": claimed["id"], "status": "RUNNING"}, {"$set": patch}
                )
                return {"status": final_status.lower(), "area": area, "job_id": claimed["id"], "result": result}
            except Exception as exc:  # noqa: BLE001 - il worker deve sopravvivere al singolo canale
                logger.exception("Ingest documentale fallito per area=%s", area)
                await db[QUEUE_COLLECTION].update_one(
                    {"id": claimed["id"], "status": "RUNNING"},
                    {"$set": {
                        "status": "ERROR",
                        "last_error": str(exc)[:4000],
                        "finished_at": _iso(utcnow()),
                        "heartbeat_at": None,
                        "lease_until": None,
                        "updated_at": _iso(utcnow()),
                    }},
                )
                return {"status": "error", "area": area, "job_id": claimed["id"], "error": str(exc)}
            finally:
                stop.set()
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
        finally:
            await _release_worker_lease(db, owner)


async def queue_and_run_one(
    db: Any,
    runners: Mapping[str, Runner],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    queued = await enqueue_due_slots(db, now=now)
    worker = await run_one(db, runners)
    return {"queue": queued, "worker": worker}


async def get_status(db: Any) -> Dict[str, Any]:
    schedule = await db[SCHEDULE_COLLECTION].find({}, {"_id": 0}).to_list(MAX_SLOTS)
    queue = await db[QUEUE_COLLECTION].find(
        {"status": {"$in": ["PENDING", "PARTIAL", "RUNNING", "ERROR"]}}, {"_id": 0}
    ).to_list(500)
    worker = await db[WORKER_COLLECTION].find_one({"key": WORKER_KEY}, {"_id": 0})
    counts: Dict[str, int] = {}
    for row in queue:
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return {
        "slots": sorted(schedule, key=lambda row: int(row.get("slot_index", 999))),
        "queue_counts": counts,
        "worker": worker,
        "slot_minutes": SLOT_MINUTES,
        "max_slots": MAX_SLOTS,
    }
