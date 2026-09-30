"""Scheda e originale di una busta paga (vista ``/personale/cedolini/:id``, MINI-08).

Montato sotto ``/api/cedolini`` DOPO ``cedolini_versioni``: ``/versioni`` e'
un indirizzo fisso e deve risolversi prima di ``/{cedolino_id}``. Sola
lettura, solo amministratore.
"""
import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.database import Database
from app.services import cedolino_scheda
from app.services.f24_originale import carica_originale
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


@router.get("/{cedolino_id}/pdf", summary="Originale PDF della busta")
async def pdf_cedolino(
    cedolino_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Response:
    doc = await Database.get_db()["cedolini"].find_one({"id": cedolino_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Busta paga non trovata")
    try:
        contenuto = await carica_originale(doc, tipo="cedolino")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Originale non disponibile: {type(exc).__name__}: {exc}") from exc
    if not contenuto:
        raise HTTPException(status_code=404, detail="PDF non disponibile per questa busta")
    nome = re.sub(r'[\r\n"]+', " ", str(doc.get("filename") or doc.get("pdf_filename") or "cedolino.pdf")).strip()
    return Response(content=contenuto, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nome}"'})
