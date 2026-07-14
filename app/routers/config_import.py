"""Endpoint per l'anno di importazione attivo (vedi app.services.config_import).
Admin-only: cambia il comportamento di canali di import automatici che
scrivono in Prima Nota/scadenzario — non un'impostazione da esporre a
utenti non amministratori.
"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from app.database import Database
from app.services.config_import import get_anno_importazione_attivo, set_anno_importazione_attivo
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
