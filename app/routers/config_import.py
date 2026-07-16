"""Endpoint per l'anno di importazione attivo (vedi app.services.config_import).
Admin-only: cambia il comportamento di canali di import automatici che
scrivono in Prima Nota/scadenzario — non un'impostazione da esporre a
utenti non amministratori.
"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from app.database import Database
from app.services.config_import import (
    get_anno_importazione_attivo, set_anno_importazione_attivo, importa_anno_da_drive,
)
from app.utils.ruoli import richiedi_admin

router = APIRouter(tags=["Config Import"])


@router.get("/anno")
async def leggi_anno_importazione_attivo() -> Dict[str, Any]:
    db = Database.get_db()
    anno = await get_anno_importazione_attivo(db)
    return {"anno": anno}


@router.put("/anno")
async def imposta_anno_importazione_attivo(
    data: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    anno = data.get("anno")
    try:
        anno = int(anno)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Campo 'anno' mancante o non valido")
    try:
        return await set_anno_importazione_attivo(Database.get_db(), anno)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/importa-anno")
async def importa_anno(
    data: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Import "pulito per anno" dal bottone in Admin: imposta l'anno attivo,
    lancia i sync Drive (fatture + corrispettivi) e promuove nel flusso
    attivo i documenti dell'anno già in archivio storico."""
    anno = data.get("anno")
    try:
        anno = int(anno)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Campo 'anno' mancante o non valido")
    if anno < 2000 or anno > 2100:
        raise HTTPException(status_code=400, detail="Anno non valido")
    return await importa_anno_da_drive(Database.get_db(), anno)
