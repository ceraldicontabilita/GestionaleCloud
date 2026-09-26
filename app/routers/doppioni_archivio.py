"""Doppioni d'archivio (cedolini, Prima Nota salari, quietanze F24, bonifici, F24).

Montato sotto ``/api/doppioni``, solo amministratore. ``dry_run`` (predefinito)
conta e mostra esempi; ``dry_run=false`` sposta le copie nelle collezioni
``<collezione>_quarantena``, la «cartella da eliminare». Gira in background:
lo stato si legge da ``/stato``.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.database import Database
from app.services import doppioni_archivio
from app.utils.ruoli import richiedi_admin

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(richiedi_admin)])
CHIAVE = "doppioni_archivio"


async def _in_background(dry_run: bool, actor: str) -> None:
    db = Database.get_db()
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE},
        {"$set": {"chiave": CHIAVE, "fase": "in_corso", "dry_run": dry_run, "actor": actor,
                  "iniziata_il": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    try:
        esito = await doppioni_archivio.ripulisci(db, dry_run=dry_run, actor=actor)
        stato = {"fase": "completata", "esito": esito}
    except Exception as exc:
        logger.exception("[doppioni] pulizia non completata")
        stato = {"fase": "errore", "errore": f"{type(exc).__name__}: {exc}"}
    stato["finita_il"] = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one({"chiave": CHIAVE}, {"$set": stato})


@router.post("/ripulisci")
async def ripulisci(dry_run: bool = True, utente: Dict[str, Any] = Depends(richiedi_admin)) -> Dict[str, Any]:
    db = Database.get_db()
    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE}, {"_id": 0}) or {}
    if stato.get("fase") == "in_corso":
        raise HTTPException(status_code=409, detail="Pulizia gia' in corso")
    actor = utente.get("sub") or utente.get("username") or "admin"
    asyncio.create_task(_in_background(dry_run, actor))
    return {"avviata": True, "dry_run": dry_run}


@router.get("/stato")
async def stato() -> Dict[str, Any]:
    db = Database.get_db()
    return await db["sistema_stato"].find_one({"chiave": CHIAVE}, {"_id": 0}) or {"fase": "mai_avviata"}
