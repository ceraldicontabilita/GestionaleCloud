"""Interroga avviso bonario + aggancio addebiti/quietanze ↔ F24 (PR 11/12).

Montato dentro il router F24 (``/api/f24``):

* ``POST /api/f24/avviso-bonario/controllo`` — per ogni riga dell'avviso
  (codice tributo, periodo, importo) il controllo incrociato con righe F24,
  quietanze, addebiti bancari e ritenute dei cedolini HR. Sola lettura.
* ``POST /api/f24/riconcilia-addebiti?dry_run=true`` — aggancio idempotente
  addebito I24 ↔ F24 (data ±3 gg + importo esatto) e quietanza ↔ F24
  (protocollo, oppure data + importo esatto). Solo admin; con ``dry_run``
  restituisce le proposte senza scrivere.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import Database
from app.services import f24_controllo_incrociato as controllo
from app.utils.dependencies import get_current_admin_user, get_current_user

router = APIRouter()


class RigaAvvisoBonario(BaseModel):
    codice_tributo: str = Field(min_length=1, description="Es. 1001, 3802, DM10")
    periodo: str = Field(min_length=4, description="MM/AAAA oppure AAAA")
    importo: float = Field(description="Importo richiesto dall'avviso")
    anno_imposta: Optional[int] = Field(None, ge=2000, le=2100)
    descrizione: Optional[str] = None


class AvvisoBonarioRequest(BaseModel):
    righe: List[RigaAvvisoBonario] = Field(min_length=1)
    numero_avviso: Optional[str] = None
    data_avviso: Optional[str] = None
    includi_cedolini_hr: bool = True


@router.post("/avviso-bonario/controllo", summary="Interroga un avviso bonario: controllo incrociato per riga")
async def controllo_avviso_bonario(
    body: AvvisoBonarioRequest,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    try:
        return await controllo.controlla_avviso(
            db, [r.model_dump() for r in body.righe],
            includi_cedolini_hr=body.includi_cedolini_hr,
            numero_avviso=body.numero_avviso, data_avviso=body.data_avviso,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/riconcilia-addebiti", summary="Aggancia addebiti I24 e quietanze ai modelli F24 (idempotente)")
async def riconcilia_addebiti_f24(
    dry_run: bool = Query(True, description="true = solo proposte, nessuna scrittura"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    return await controllo.riconcilia_addebiti(db, dry_run=dry_run)
