"""Piano tributi: i tributi attesi nell'anno e il loro stato (solo admin).

Montato dentro il router F24 (``/api/f24``), prima della rotta dinamica:

* ``GET  /api/f24/piano-tributi?anno=2026`` — griglia voci x periodi;
* la ricerca di un codice tributo resta ``GET /api/f24-riconciliazione/verifica-codice``;
* ``GET  /api/f24/piano-tributi/voci`` — le voci del piano;
* ``PUT  /api/f24/piano-tributi/voci/{id}`` — attiva/disattiva, scadenze, mesi;
* ``POST /api/f24/piano-tributi/voci`` — voce nuova su codici scelti.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import Database
from app.services import piano_tributi as piano
from app.utils.dependencies import get_current_admin_user

router = APIRouter()


class ModificaVoce(BaseModel):
    attivo: Optional[bool] = None
    etichetta: Optional[str] = Field(None, max_length=120)
    scadenze: Optional[List[List[int]]] = None
    mesi: Optional[List[int]] = None
    nota: Optional[str] = Field(None, max_length=500)
    obbligatorio: Optional[bool] = None


class NuovaVoce(BaseModel):
    etichetta: Optional[str] = Field(None, max_length=120)
    gruppo: Optional[str] = Field(None, max_length=60)
    codici: List[str] = Field(default_factory=list)
    periodo: str = "mese"
    mesi: Optional[List[int]] = None
    anno_offset: int = Field(0, ge=-1, le=0)
    scadenze: Optional[List[List[int]]] = None
    obbligatorio: bool = True


@router.get("/piano-tributi", summary="Piano tributi dell'anno: attesi, arrivati, pagati")
async def griglia_piano(
    anno: Optional[int] = Query(None, ge=2019, le=2100),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    anno = anno or datetime.now(timezone.utc).year
    return await piano.griglia(Database.get_db(), anno)


@router.get("/piano-tributi/voci", summary="Voci del piano tributi")
async def elenco_voci(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return {"voci": await piano.voci_piano(Database.get_db())}


@router.put("/piano-tributi/voci/{voce_id}", summary="Modifica una voce del piano")
async def modifica_voce(
    voce_id: str, body: ModificaVoce,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    try:
        voce = await piano.aggiorna_voce(
            Database.get_db(), voce_id, body.model_dump(exclude_none=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voce del piano non trovata") from exc
    except (ValueError, TypeError, IndexError) as exc:
        raise HTTPException(status_code=422, detail=f"Scadenza non valida: {exc}") from exc
    return {"voce": voce}


@router.post("/piano-tributi/voci", summary="Aggiunge una voce al piano")
async def nuova_voce(
    body: NuovaVoce, _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    try:
        return {"voce": await piano.aggiungi_voce(Database.get_db(), body.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
