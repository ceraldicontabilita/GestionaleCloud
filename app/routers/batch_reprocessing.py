"""
Router per Batch Reprocessing di F24 e Cedolini.
Espone endpoint per il frontend BatchReprocessing.jsx.
"""
import asyncio
import logging
from typing import Dict, Any
from fastapi import APIRouter, Query

from app.database import Database
from app.services.batch_reprocessing import BatchReprocessingService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Batch Reprocessing"])

# Stato globale del job in corso
_job_state: Dict[str, Any] = {
    "running": False,
    "progress": None,
    "result": None,
    "error": None,
}


@router.get("/preview")
async def get_preview() -> Dict[str, Any]:
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
async def get_status() -> Dict[str, Any]:
    """Stato corrente del job di riprocessamento."""
    return _job_state


async def _run_job(service: BatchReprocessingService, method: str, dry_run: bool):
    """Esegue il job in background aggiornando lo stato globale."""
    global _job_state
    try:
        _job_state["running"] = True
        _job_state["error"] = None
        _job_state["progress"] = f"In corso... ({'DRY RUN' if dry_run else 'PRODUZIONE'})"

        if method == "f24":
            result = await service.reprocess_all_f24(dry_run)
        elif method == "cedolini":
            result = await service.reprocess_all_cedolini(dry_run)
        else:
            result = await service.reprocess_all(dry_run)

        _job_state["result"] = result
        _job_state["progress"] = "Completato"
    except Exception as exc:
        logger.exception("Errore batch reprocessing")
        _job_state["error"] = str(exc)
        _job_state["progress"] = "Errore"
    finally:
        _job_state["running"] = False


@router.post("/start")
async def start_reprocessing(dry_run: bool = Query(True)) -> Dict[str, str]:
    """Avvia riprocessamento completo (F24 + Cedolini)."""
    if _job_state["running"]:
        return {"detail": "Job gia in corso"}
    service = BatchReprocessingService()
    asyncio.create_task(_run_job(service, "all", dry_run))
    return {"detail": "Riprocessamento avviato"}


@router.post("/f24-only")
async def start_f24_only(dry_run: bool = Query(True)) -> Dict[str, str]:
    """Avvia riprocessamento solo F24."""
    if _job_state["running"]:
        return {"detail": "Job gia in corso"}
    service = BatchReprocessingService()
    asyncio.create_task(_run_job(service, "f24", dry_run))
    return {"detail": "Riprocessamento F24 avviato"}


@router.post("/cedolini-only")
async def start_cedolini_only(dry_run: bool = Query(True)) -> Dict[str, str]:
    """Avvia riprocessamento solo Cedolini."""
    if _job_state["running"]:
        return {"detail": "Job gia in corso"}
    service = BatchReprocessingService()
    asyncio.create_task(_run_job(service, "cedolini", dry_run))
    return {"detail": "Riprocessamento Cedolini avviato"}
