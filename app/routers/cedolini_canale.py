"""Bonifica del solo ``canale`` delle buste in archivio (MINI-09.6).

Solo admin. Simulazione per difetto (``dry_run``); il giro parte in sottofondo e
lo stato resta in ``sistema_stato`` (chiave ``canale_cedolini_bonifica``). Un
motore solo: ``services/canale_bonifica``. Non tocca ``netto_fonte`` ne' il netto.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.services import canale_bonifica
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

_job_task: Optional[asyncio.Task] = None


async def _esegui(db, dry_run: bool, limite: int) -> None:
    try:
        await canale_bonifica.giro(db, dry_run=dry_run, limite=limite)
    except Exception as exc:  # noqa: BLE001 - l'esito resta nello stato
        logger.exception("Bonifica del canale dei cedolini fallita: %s", type(exc).__name__)
        await db["sistema_stato"].update_one(
            {"chiave": canale_bonifica.CHIAVE_STATO},
            {"$set": {"errore": f"{type(exc).__name__}: {exc}", "in_corso": False}}, upsert=True)


async def _stato_dati() -> Dict[str, Any]:
    stato = await Database.get_db()["sistema_stato"].find_one({"chiave": canale_bonifica.CHIAVE_STATO}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    stato["stato"] = "in_corso" if _job_task is not None and not _job_task.done() else "completato"
    return stato


@router.post("/canale/bonifica", summary="Canale d'ingresso delle buste gia' in archivio, in sottofondo (dry_run per difetto)")
async def canale_bonifica_avvia(
    dry_run: bool = Query(True, description="Se True conta per canale e non scrive"),
    limite: int = Query(canale_bonifica.LIMITE_PREDEFINITO, ge=1, le=5000,
                        description="Righe scritte per giro (gestionale poi HR); si ripete finche' restanti = 0"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    global _job_task
    if _job_task is not None and not _job_task.done():
        return {"avviato": False, **await _stato_dati()}
    db = Database.get_db()
    await db["sistema_stato"].update_one(
        {"chiave": canale_bonifica.CHIAVE_STATO}, {"$set": {"in_corso": True, "dry_run": dry_run}}, upsert=True)
    _job_task = asyncio.create_task(_esegui(db, dry_run, limite))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run, "limite": limite}


@router.get("/canale/stato", summary="Esito dell'ultimo giro sul canale delle buste")
async def canale_stato(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return await _stato_dati()
