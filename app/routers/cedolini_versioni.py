"""Versioni della stessa busta nel registro ``cedolini``: rapporto e applicazione.

Un motore solo (``services/cedolini_versioni``): la definitiva batte la
stampa di controllo, la «Variante N» piu' alta batte le precedenti, due netti
senza marcatore restano ``da_decidere`` per il titolare. Qui si legge
l'archivio (sola lettura) e si applica a lotti in sottofondo, con lo stato in
``sistema_stato`` (chiave ``cedolini_versioni``).
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.services import cedolini_versioni
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

_job_task: Optional[asyncio.Task] = None


@router.get("/versioni", summary="Buste con piu' versioni e netti diversi: chi vale e chi decide il titolare")
async def versioni_rapporto(
    dry_run: bool = Query(True, description="Sempre in sola lettura: il rapporto non scrive"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await cedolini_versioni.rapporto_archivio(Database.get_db())


async def _esegui(db, dry_run: bool) -> None:
    try:
        await cedolini_versioni.giro(db, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - l'esito resta nello stato
        logger.exception("Giro versioni cedolini fallito")
        await db["sistema_stato"].update_one(
            {"chiave": cedolini_versioni.CHIAVE_STATO},
            {"$set": {"errore": f"{type(exc).__name__}: {exc}"}}, upsert=True)


@router.post("/versioni/applica", summary="Applica le decisioni sulle versioni, un lotto per volta, in sottofondo")
async def versioni_applica(
    dry_run: bool = Query(True, description="Se True valuta il lotto senza scrivere"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Oltre i 5 minuti il proxy Render taglia la richiesta: il giro parte in
    sottofondo e l'esito si legge da ``GET /versioni/stato``. Mai su righe
    pagate o con Prima Nota salari."""
    global _job_task
    if _job_task is not None and not _job_task.done():
        return {"avviato": False, **await versioni_stato_dati()}
    _job_task = asyncio.create_task(_esegui(Database.get_db(), dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def versioni_stato_dati() -> Dict[str, Any]:
    stato = await Database.get_db()["sistema_stato"].find_one(
        {"chiave": cedolini_versioni.CHIAVE_STATO}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    stato["stato"] = "in_corso" if _job_task is not None and not _job_task.done() else "completato"
    return stato


@router.get("/versioni/stato", summary="Esito dell'ultimo giro sulle versioni")
async def versioni_stato(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return await versioni_stato_dati()
