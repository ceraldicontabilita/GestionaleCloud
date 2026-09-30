"""Interroga avviso bonario (PR 11/12).

Montato dentro il router F24 (``/api/f24``):

* ``POST /api/f24/avviso-bonario/controllo`` — per ogni riga dell'avviso
  (codice tributo, periodo, importo) il controllo incrociato con righe F24,
  quietanze, addebiti bancari e ritenute dei cedolini HR. Sola lettura.

L'aggancio addebito ↔ pagamento non e' piu' qui: e' il motore a livelli
``f24_controllo_incrociato.riconcilia_f24_banca``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import Database
from app.services import f24_controllo_incrociato as controllo
from app.utils.dependencies import get_current_user

router = APIRouter()


class RigaAvvisoBonario(BaseModel):
    codice_tributo: str = Field(min_length=1, description="Es. 1001, 3802, DM10")
    periodo: str = Field(min_length=4, description="MM/AAAA oppure AAAA")
    importo: float = Field(description="Importo richiesto dall'avviso")
    anno_imposta: Optional[int] = Field(None, ge=2000, le=2100)
    descrizione: Optional[str] = None
    importo_sanzioni: Optional[float] = Field(None, description="Sanzioni richieste per la riga")
    importo_interessi: Optional[float] = Field(None, description="Interessi richiesti per la riga")
    data_versamento_ade: Optional[str] = Field(None, description="Data del versamento secondo l'Agenzia")


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
