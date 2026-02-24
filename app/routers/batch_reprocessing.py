"""
Router API per Batch Reprocessing
Endpoint per riprocessare F24 e Cedolini con il parser migliorato.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Dict, Any
import logging
import asyncio

from app.services.batch_reprocessing import BatchReprocessingService, run_batch_reprocessing
from app.database import Database

router = APIRouter(prefix="/batch-reprocess", tags=["Batch Reprocessing"])
logger = logging.getLogger(__name__)

# Stato globale del job di riprocessamento
_current_job = {
    "running": False,
    "progress": None,
    "result": None,
    "error": None
}


async def _run_reprocessing_job(dry_run: bool):
    """Esegue il job di riprocessamento in background."""
    global _current_job
    
    try:
        _current_job["running"] = True
        _current_job["progress"] = "In corso..."
        _current_job["error"] = None
        
        result = await run_batch_reprocessing(dry_run)
        
        _current_job["result"] = result
        _current_job["progress"] = "Completato"
        
    except Exception as e:
        logger.error(f"Errore batch reprocessing: {e}")
        _current_job["error"] = str(e)
        _current_job["progress"] = "Errore"
    finally:
        _current_job["running"] = False


@router.get("/status")
async def get_reprocessing_status() -> Dict[str, Any]:
    """
    Ottieni lo stato corrente del job di riprocessamento.
    """
    return {
        "running": _current_job["running"],
        "progress": _current_job["progress"],
        "result": _current_job["result"],
        "error": _current_job["error"]
    }


@router.post("/start")
async def start_reprocessing(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=True, description="Se True, esegue solo test senza salvare")
) -> Dict[str, Any]:
    """
    Avvia il riprocessamento batch di tutti i documenti.
    
    - **dry_run=True** (default): Esegue solo un test, non salva modifiche
    - **dry_run=False**: Riprocessa e aggiorna tutti i documenti
    
    Il processo viene eseguito in background. Usa /status per monitorare.
    """
    global _current_job
    
    if _current_job["running"]:
        raise HTTPException(
            status_code=409, 
            detail="Un job di riprocessamento è già in corso. Attendi il completamento."
        )
    
    # Reset stato
    _current_job["result"] = None
    _current_job["error"] = None
    
    # Avvia in background
    background_tasks.add_task(_run_reprocessing_job, dry_run)
    
    return {
        "message": f"Riprocessamento avviato {'(DRY RUN - nessuna modifica)' if dry_run else '(MODIFICHE ATTIVE)'}",
        "dry_run": dry_run,
        "status_endpoint": "/api/batch-reprocess/status"
    }


@router.post("/f24-only")
async def reprocess_f24_only(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=True)
) -> Dict[str, Any]:
    """
    Riprocessa solo gli F24 (non i cedolini).
    """
    global _current_job
    
    if _current_job["running"]:
        raise HTTPException(status_code=409, detail="Job già in corso")
    
    async def _run_f24_only():
        global _current_job
        try:
            _current_job["running"] = True
            _current_job["progress"] = "Riprocessamento F24..."
            
            service = BatchReprocessingService()
            result = await service.reprocess_all_f24(dry_run)
            
            _current_job["result"] = result
            _current_job["progress"] = "Completato"
        except Exception as e:
            _current_job["error"] = str(e)
            _current_job["progress"] = "Errore"
        finally:
            _current_job["running"] = False
    
    background_tasks.add_task(_run_f24_only)
    
    return {
        "message": f"Riprocessamento F24 avviato {'(DRY RUN)' if dry_run else ''}",
        "dry_run": dry_run
    }


@router.post("/cedolini-only")
async def reprocess_cedolini_only(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=True)
) -> Dict[str, Any]:
    """
    Riprocessa solo i cedolini (non gli F24).
    """
    global _current_job
    
    if _current_job["running"]:
        raise HTTPException(status_code=409, detail="Job già in corso")
    
    async def _run_cedolini_only():
        global _current_job
        try:
            _current_job["running"] = True
            _current_job["progress"] = "Riprocessamento Cedolini..."
            
            service = BatchReprocessingService()
            result = await service.reprocess_all_cedolini(dry_run)
            
            _current_job["result"] = result
            _current_job["progress"] = "Completato"
        except Exception as e:
            _current_job["error"] = str(e)
            _current_job["progress"] = "Errore"
        finally:
            _current_job["running"] = False
    
    background_tasks.add_task(_run_cedolini_only)
    
    return {
        "message": f"Riprocessamento Cedolini avviato {'(DRY RUN)' if dry_run else ''}",
        "dry_run": dry_run
    }


@router.get("/preview")
async def preview_documents_to_reprocess() -> Dict[str, Any]:
    """
    Anteprima dei documenti che verranno riprocessati.
    Non esegue nessuna modifica, solo conta i documenti.
    """
    db = Database.get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database non connesso")
    
    result = {
        "f24": {},
        "cedolini": {},
        "totale": 0
    }
    
    # Conta F24
    f24_collections = ["f24_models", "f24", "f24_uploaded"]
    for coll_name in f24_collections:
        try:
            count = await db[coll_name].count_documents({
                "pdf_data": {"$exists": True, "$ne": None}
            })
            if count > 0:
                result["f24"][coll_name] = count
                result["totale"] += count
        except Exception:
            pass
    
    # Conta Cedolini
    cedolini_collections = ["cedolini", "payslips", "buste_paga", "extracted_documents"]
    for coll_name in cedolini_collections:
        try:
            count = await db[coll_name].count_documents({
                "$or": [
                    {"pdf_data": {"$exists": True, "$ne": None}},
                    {"file_base64": {"$exists": True, "$ne": None}},
                    {"pdf_base64": {"$exists": True, "$ne": None}}
                ]
            })
            if count > 0:
                result["cedolini"][coll_name] = count
                result["totale"] += count
        except Exception:
            pass
    
    result["f24_totale"] = sum(result["f24"].values())
    result["cedolini_totale"] = sum(result["cedolini"].values())
    
    return result


@router.get("/info")
async def get_batch_info() -> Dict[str, Any]:
    """
    Informazioni sul servizio di batch reprocessing.
    """
    return {
        "service": "Batch Reprocessing Service",
        "version": "1.0.0",
        "description": "Riprocessa tutti i documenti F24 e Cedolini con il parser migliorato Enhanced Parser v2",
        "endpoints": {
            "/preview": "Anteprima documenti da riprocessare (senza modifiche)",
            "/start?dry_run=true": "Avvia riprocessamento completo (test)",
            "/start?dry_run=false": "Avvia riprocessamento completo (salva modifiche)",
            "/f24-only": "Riprocessa solo F24",
            "/cedolini-only": "Riprocessa solo Cedolini",
            "/status": "Stato del job corrente"
        },
        "warning": "Il riprocessamento con dry_run=false modifica i dati nel database!"
    }
