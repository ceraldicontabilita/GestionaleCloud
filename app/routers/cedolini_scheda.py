"""Scheda di una busta paga (vista ``/personale/cedolini/:id``, MINI-08); l'originale si apre da ``/api/originale/cedolino/{id}``.

Montato sotto ``/api/cedolini`` DOPO ``cedolini_versioni``: ``/versioni`` e'
un indirizzo fisso e deve risolversi prima di ``/{cedolino_id}``. Sola
lettura, solo amministratore.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.database import Database
from app.services import cedolino_scheda
from app.utils.dependencies import get_current_admin_user

router = APIRouter()


@router.get("/{cedolino_id}", summary="Scheda della busta: netto, fonte, versioni, canale")
async def scheda_cedolino(
    cedolino_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    dati = await cedolino_scheda.scheda(Database.get_db(), cedolino_id)
    if dati is None:
        raise HTTPException(status_code=404, detail="Busta paga non trovata")
    return dati
