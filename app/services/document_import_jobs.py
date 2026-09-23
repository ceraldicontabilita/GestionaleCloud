"""Coda in-process per import documentali voluminosi.

Il file viene ricevuto e validato dalla rotta autenticata, mentre il lavoro
Drive/Supabase prosegue dopo la risposta HTTP. Lo stato e' persistito nell'archivio:
se il processo viene riavviato, un nuovo upload dello stesso file riprende il
job usando lo stesso identificativo e le chiavi operazione dell'importer
impediscono scritture duplicate.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from app.services.pos_terminal_import import importa_pos_terminal_file


logger = logging.getLogger(__name__)

COLLECTION = "document_import_jobs"
_ACTIVE_TASKS: dict[str, asyncio.Task] = {}
_PENDING_JOBS: dict[str, Dict[str, Any]] = {}
_POS_IMPORT_LOCK = asyncio.Lock()
_JOB_START_DELAY_SECONDS = 0.25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_id_for_content(content: bytes) -> str:
    return f"DOC-IMPORT-{hashlib.sha256(content).hexdigest()[:32]}"


def public_job(record: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not record:
        return None
    return {
        key: record.get(key)
        for key in (
            "id", "job_id", "status", "filename", "document_type",
            "content_sha256", "attempts", "created_at", "started_at",
            "completed_at", "failed_at", "updated_at", "result", "error",
        )
        if record.get(key) is not None
    }


async def _save_job(db, job_id: str, values: Dict[str, Any]) -> None:
    pending = _PENDING_JOBS.setdefault(job_id, {"id": job_id, "job_id": job_id})
    pending.update(values)
    pending["updated_at"] = _now()
    await db[COLLECTION].update_one(
        {"id": job_id},
        {"$set": dict(pending)},
        upsert=True,
    )


async def _run_job(
    db, *, job_id: str, filename: str,
    runner: Callable[[], Awaitable[Dict[str, Any]]],
) -> None:
    """Un solo esecutore per ogni import accodato (POS, archivi ZIP)."""
    try:
        async with _POS_IMPORT_LOCK:
            await _save_job(db, job_id, {
                "status": "running", "started_at": _now(), "error": None,
            })
            result = await runner()
            await _save_job(db, job_id, {
                "status": "completed", "completed_at": _now(),
                "result": result, "error": None,
            })
            logger.info("Import documentale asincrono completato: %s", filename)
    except Exception as exc:
        logger.exception(
            "Import documentale asincrono fallito: %s (%s)", filename, type(exc).__name__,
        )
        try:
            await _save_job(db, job_id, {
                "status": "failed", "failed_at": _now(),
                "error": (str(exc) or type(exc).__name__)[:2000],
            })
        except Exception as exc_stato:
            logger.exception(
                "Impossibile registrare il fallimento del job %s (%s)",
                job_id, type(exc_stato).__name__,
            )


async def _run_pos_job(
    db, *, job_id: str, content: bytes, filename: str,
    drive_file_id: str | None = None,
) -> None:
    await _run_job(
        db, job_id=job_id, filename=filename,
        runner=lambda: importa_pos_terminal_file(
            db, content, filename, drive_file_id=drive_file_id,
        ),
    )


def _forget_task(job_id: str, task: asyncio.Task) -> None:
    current = _ACTIVE_TASKS.get(job_id)
    if current is task:
        _ACTIVE_TASKS.pop(job_id, None)
        _PENDING_JOBS.pop(job_id, None)


async def _after_ack(job: Callable[[], Awaitable[None]]) -> None:
    """Lascia al gateway il tempo di inviare il 202 prima di scrivere nell'archivio."""
    await asyncio.sleep(_JOB_START_DELAY_SECONDS)
    await job()


async def _enqueue(
    db, *, content: bytes, filename: str, document_type: str,
    job: Callable[[str], Awaitable[None]],
) -> Dict[str, Any]:
    """Accoda un import riusando il job deterministico del contenuto."""
    digest = hashlib.sha256(content).hexdigest()
    job_id = job_id_for_content(content)
    existing = await db[COLLECTION].find_one({"id": job_id}, {"_id": 0})
    active = _ACTIVE_TASKS.get(job_id)

    if existing and existing.get("status") == "completed":
        return {"queued": False, **(public_job(existing) or {})}
    if active is not None and not active.done():
        visible = _PENDING_JOBS.get(job_id) or existing or {"job_id": job_id}
        return {"queued": True, **(public_job(visible) or {"job_id": job_id})}

    attempts = int((existing or {}).get("attempts") or 0) + 1
    created_at = (existing or {}).get("created_at") or _now()
    queued_record = {
        "id": job_id,
        "job_id": job_id,
        "operation_id": f"document-import:{digest}",
        "status": "queued",
        "filename": filename,
        "document_type": document_type,
        "content_sha256": digest,
        "attempts": attempts,
        "created_at": created_at,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "result": None,
        "error": None,
        "updated_at": _now(),
    }
    _PENDING_JOBS[job_id] = queued_record
    task = asyncio.create_task(
        _after_ack(lambda: job(job_id)),
        name=f"document-import-{job_id}",
    )
    _ACTIVE_TASKS[job_id] = task
    task.add_done_callback(lambda done: _forget_task(job_id, done))
    return {
        "queued": True,
        **(public_job(queued_record) or {"job_id": job_id, "status": "queued"}),
    }


async def enqueue_pos_import(
    db, *, content: bytes, filename: str, drive_file_id: str | None = None,
) -> Dict[str, Any]:
    """Accoda un export POS, riusando il job deterministico del file."""
    return await _enqueue(
        db, content=content, filename=filename, document_type="pos_terminal",
        job=lambda job_id: _run_pos_job(
            db, job_id=job_id, content=content, filename=filename,
            drive_file_id=drive_file_id,
        ),
    )


async def enqueue_import(
    db, *, content: bytes, filename: str, document_type: str,
    process: Callable[[str, bytes], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Accoda un import voluminoso (archivio ZIP, estratto conto): centinaia
    di righe superano i 5 minuti del proxy Render e i 2 del browser, e un
    upload interrotto si fermava a meta'. ``process`` e' l'elaborazione
    canonica dell'upload (la stessa di sempre), passata dalla rotta per non
    importare il router da qui."""
    return await _enqueue(
        db, content=content, filename=filename, document_type=document_type,
        job=lambda job_id: _run_job(
            db, job_id=job_id, filename=filename,
            runner=lambda: process(filename, content),
        ),
    )


MESSAGGIO_INTERROTTO = (
    "Import interrotto da un riavvio del servizio: ricarica lo stesso file, "
    "i documenti gia' importati vengono saltati."
)


async def segna_interrotti_all_avvio(db) -> int:
    """Un job «in corso» all'avvio non ha piu' nessuno che lo lavora: il
    contenuto viveva nella memoria del processo spento. Senza questo la pagina
    lo seguiva per sempre (23/09/2026: due ZIP «running» dopo tre deploy)."""
    interrotti = 0
    for job in await db[COLLECTION].find(
        {"status": {"$in": ["queued", "running"]}}, {"_id": 0, "id": 1},
    ).to_list(None):
        if not job.get("id") or job["id"] in _ACTIVE_TASKS:
            continue
        await db[COLLECTION].update_one({"id": job["id"]}, {"$set": {
            "status": "failed", "failed_at": _now(), "updated_at": _now(),
            "error": MESSAGGIO_INTERROTTO,
        }})
        interrotti += 1
    return interrotti


async def get_import_job(db, job_id: str) -> Dict[str, Any] | None:
    active = _ACTIVE_TASKS.get(job_id)
    pending = _PENDING_JOBS.get(job_id)
    if pending is not None and active is not None and not active.done():
        return public_job(pending)
    return public_job(
        await db[COLLECTION].find_one({"id": job_id}, {"_id": 0})
    )


async def wait_for_import_job(job_id: str) -> None:
    """Attende il task locale; usato dai test e dagli shutdown controllati."""
    task = _ACTIVE_TASKS.get(job_id)
    if task is not None:
        await task
