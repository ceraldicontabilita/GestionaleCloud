"""Amministrazione del modulo HR: stato dati e migrazione da AppDipendenti.

Tutto sotto ``/api/hr/admin`` (solo admin). La DSN della sorgente non viene
mai accettata dalla richiesta: e' letta dall'env ``APPDIPENDENTI_DB_URL``
configurata su Render, cosi' nessuna credenziale passa dal browser.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, status

from app.hr.migrazione_appdipendenti import migra, stato_destinazione

logger = logging.getLogger(__name__)
router = APIRouter()

_jobs: Dict[str, Dict[str, Any]] = {}


@router.get("/stato-dati", summary="Conteggi delle collezioni HR nel registro unico")
async def stato_dati() -> Dict[str, Any]:
    return await stato_destinazione()


async def _esegui(job_id: str, tabelle: Optional[List[str]], dry_run: bool) -> None:
    job = _jobs[job_id]
    job["status"] = "running"

    def _progress(nome: str, n: int) -> None:
        job["avanzamento"][nome] = n

    try:
        job["esito"] = await migra(os.environ["APPDIPENDENTI_DB_URL"], tabelle=tabelle, dry_run=dry_run, progress=_progress)
        job["status"] = "done" if job["esito"]["coincide"] else "mismatch"
    except Exception as exc:
        logger.exception("Migrazione AppDipendenti fallita")
        job["status"] = "failed"
        job["errore"] = str(exc)[:500]
    finally:
        job["finito_il"] = datetime.now(timezone.utc).isoformat()


@router.post("/migrazione-appdipendenti", summary="Avvia la migrazione dei dati AppDipendenti")
async def avvia_migrazione(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    if not os.environ.get("APPDIPENDENTI_DB_URL"):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "APPDIPENDENTI_DB_URL non configurata su Render")
    if any(j["status"] == "running" for j in _jobs.values()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Una migrazione e' gia' in corso")
    tabelle = payload.get("tabelle") or None
    if tabelle is not None and not isinstance(tabelle, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tabelle deve essere una lista")
    dry_run = bool(payload.get("dry_run", False))
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id, "status": "queued", "dry_run": dry_run, "tabelle": tabelle,
        "avanzamento": {}, "avviato_il": datetime.now(timezone.utc).isoformat(),
    }
    asyncio.create_task(_esegui(job_id, tabelle, dry_run))
    return _jobs[job_id]


@router.get("/migrazione-appdipendenti/{job_id}", summary="Stato di una migrazione")
async def stato_migrazione(job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Migrazione non trovata")
    return job
