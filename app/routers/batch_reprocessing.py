"""API amministrative per la rielaborazione dei documenti gia acquisiti.

La rielaborazione ordinaria lavora dinamicamente sull'archivio documentale e
non e piu limitata a F24 e cedolini. Gli endpoint specializzati restano per
compatibilita e manutenzione mirata.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.services.batch_reprocessing import BatchReprocessingService
from app.services.ripielaborazione_documenti import RielaborazioneDocumentiService
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Rielaborazione documenti"])

COLL_JOB_STATE = "job_state"
JOB_KEY = "batch_reprocessing"
STALE_DOPO_MIN = 30

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
    """Conta dinamicamente tutte le categorie con originale rielaborabile."""
    return await RielaborazioneDocumentiService().anteprima()


@router.get("/status")
async def get_status(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await _get_state(Database.get_db())


async def _run_universale(dry_run: bool, categoria: Optional[str]) -> None:
    db = Database.get_db()
    try:
        await _set_state(db, {
            "running": True,
            "error": None,
            "result": None,
            "progress": f"Rielaborazione in corso ({'SIMULAZIONE' if dry_run else 'ESECUZIONE'})",
        })
        result = await RielaborazioneDocumentiService(db).rielabora(
            dry_run=dry_run,
            categoria=categoria,
        )
        await _set_state(db, {"result": result, "progress": "Completato", "running": False})
    except Exception as exc:
        logger.exception("Errore rielaborazione universale")
        await _set_state(db, {"error": str(exc), "progress": "Errore", "running": False})


async def _run_specializzato(method: str, dry_run: bool) -> None:
    db = Database.get_db()
    try:
        await _set_state(db, {
            "running": True,
            "error": None,
            "result": None,
            "progress": f"Rielaborazione specializzata ({'SIMULAZIONE' if dry_run else 'ESECUZIONE'})",
        })
        service = BatchReprocessingService()
        if method == "f24":
            result = await service.reprocess_all_f24(dry_run)
        else:
            result = await service.reprocess_all_cedolini(dry_run)
        await _set_state(db, {"result": result, "progress": "Completato", "running": False})
    except Exception as exc:
        logger.exception("Errore rielaborazione specializzata")
        await _set_state(db, {"error": str(exc), "progress": "Errore", "running": False})


def _job_stallato(stato: Dict[str, Any]) -> bool:
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


async def _puo_partire() -> Optional[Dict[str, str]]:
    stato = await _get_state(Database.get_db())
    if stato.get("running") and not _job_stallato(stato):
        return {"detail": "Rielaborazione gia in corso"}
    return None


@router.post("/start")
async def start_reprocessing(
    dry_run: bool = Query(True),
    categoria: Optional[str] = Query(None, max_length=120),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, str]:
    """Rielabora tutti i documenti o una categoria scelta dinamicamente."""
    blocco = await _puo_partire()
    if blocco:
        return blocco
    asyncio.create_task(_run_universale(dry_run, categoria))
    return {"detail": "Rielaborazione documenti avviata"}


@router.post("/f24-only")
async def start_f24_only(
    dry_run: bool = Query(True),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, str]:
    blocco = await _puo_partire()
    if blocco:
        return blocco
    asyncio.create_task(_run_specializzato("f24", dry_run))
    return {"detail": "Rielaborazione F24 avviata"}


@router.post("/cedolini-only")
async def start_cedolini_only(
    dry_run: bool = Query(True),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, str]:
    blocco = await _puo_partire()
    if blocco:
        return blocco
    asyncio.create_task(_run_specializzato("cedolini", dry_run))
    return {"detail": "Rielaborazione cedolini avviata"}
