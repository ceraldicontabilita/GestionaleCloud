"""
Router per Batch Reprocessing di F24 e Cedolini.
Espone endpoint per il frontend BatchReprocessing.jsx.

Tutti gli endpoint sono admin-only: avviano un'operazione che riscrive
documenti in archivio, e prima bastava essere loggati — anche in sola
lettura — per farla partire.

Lo stato del job è PERSISTITO in MongoDB (collezione `job_state`), non in una
variabile globale di processo: così sopravvive a restart e funziona con più worker
uvicorn. Vedi P0.10 / §11.4.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.services.batch_reprocessing import BatchReprocessingService
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Batch Reprocessing"])

COLL_JOB_STATE = "job_state"
JOB_KEY = "batch_reprocessing"
STALE_DOPO_MIN = 30  # un job "running" senza heartbeat da oltre 30 min è morto

_STATO_INIZIALE = {
    "job_id": JOB_KEY,
    "running": False,
    "progress": None,
    "result": None,
    "error": None,
    "updated_at": None,
}


async def _get_state(db) -> Dict[str, Any]:
    doc = await db[COLL_JOB_STATE].find_one({"job_id": JOB_KEY}, {"_id": 0})
    return doc or dict(_STATO_INIZIALE)


async def _set_state(db, patch: Dict[str, Any]) -> None:
    patch = dict(patch)
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db[COLL_JOB_STATE].update_one(
        {"job_id": JOB_KEY},
        {"$set": patch, "$setOnInsert": {"job_id": JOB_KEY}},
        upsert=True,
    )


@router.get("/preview")
async def get_preview(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Anteprima dei documenti disponibili per il riprocessamento."""
    db = Database.get_db()

    f24_counts = {}
    for coll_name in ["f24_models", "f24", "f24_uploaded"]:
        try:
            count = await db[coll_name].count_documents(
                {"pdf_data": {"$exists": True, "$ne": None}}
            )
            if count > 0:
                f24_counts[coll_name] = count
        except Exception:
            pass

    cedolini_counts = {}
    for coll_name in ["cedolini", "payslips", "buste_paga", "extracted_documents"]:
        try:
            count = await db[coll_name].count_documents(
                {"$or": [
                    {"pdf_data": {"$exists": True, "$ne": None}},
                    {"file_base64": {"$exists": True, "$ne": None}},
                    {"pdf_base64": {"$exists": True, "$ne": None}},
                ]}
            )
            if count > 0:
                cedolini_counts[coll_name] = count
        except Exception:
            pass

    f24_totale = sum(f24_counts.values())
    cedolini_totale = sum(cedolini_counts.values())

    return {
        "f24": f24_counts,
        "cedolini": cedolini_counts,
        "f24_totale": f24_totale,
        "cedolini_totale": cedolini_totale,
        "totale": f24_totale + cedolini_totale,
    }


@router.get("/status")
async def get_status(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Stato corrente del job di riprocessamento (persistito su MongoDB)."""
    return await _get_state(Database.get_db())


async def _run_job(service: BatchReprocessingService, method: str, dry_run: bool):
    """Esegue il job in background aggiornando lo stato persistito."""
    db = Database.get_db()
    try:
        await _set_state(db, {
            "running": True,
            "error": None,
            "result": None,
            "progress": f"In corso... ({'DRY RUN' if dry_run else 'PRODUZIONE'})",
        })

        if method == "f24":
            result = await service.reprocess_all_f24(dry_run)
        elif method == "cedolini":
            result = await service.reprocess_all_cedolini(dry_run)
        else:
            result = await service.reprocess_all(dry_run)

        await _set_state(db, {"result": result, "progress": "Completato", "running": False})
    except Exception as exc:
        logger.exception("Errore batch reprocessing")
        await _set_state(db, {"error": str(exc), "progress": "Errore", "running": False})


def _job_stallato(stato: Dict[str, Any]) -> bool:
    """Un job 'running' il cui heartbeat è più vecchio di STALE_DOPO_MIN è
    considerato morto (es. worker crashato): non deve bloccare i job futuri.
    Prima, senza questo controllo, un crash lasciava running=True per sempre."""
    if not stato.get("running"):
        return False
    upd = stato.get("updated_at")
    if not upd:
        return True
    try:
        ts = datetime.fromisoformat(upd)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() > STALE_DOPO_MIN * 60
    except (ValueError, TypeError):
        return True


async def _avvia(method: str, dry_run: bool, label: str) -> Dict[str, str]:
    db = Database.get_db()
    stato = await _get_state(db)
    if stato.get("running") and not _job_stallato(stato):
        return {"detail": "Job gia in corso"}
    service = BatchReprocessingService()
    asyncio.create_task(_run_job(service, method, dry_run))
    return {"detail": label}


@router.post("/start")
async def start_reprocessing(
    dry_run: bool = Query(True),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, str]:
    """Avvia riprocessamento completo (F24 + Cedolini)."""
    return await _avvia("all", dry_run, "Riprocessamento avviato")


@router.post("/f24-only")
async def start_f24_only(
    dry_run: bool = Query(True),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, str]:
    """Avvia riprocessamento solo F24."""
    return await _avvia("f24", dry_run, "Riprocessamento F24 avviato")


@router.post("/cedolini-only")
async def start_cedolini_only(
    dry_run: bool = Query(True),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, str]:
    """Avvia riprocessamento solo Cedolini."""
    return await _avvia("cedolini", dry_run, "Riprocessamento Cedolini avviato")
