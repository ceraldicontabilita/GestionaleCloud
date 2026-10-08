"""Piano tributi: i tributi attesi nell'anno e il loro stato (solo admin).

Montato dentro il router F24 (``/api/f24``), prima della rotta dinamica:

* ``GET  /api/f24/piano-tributi?anno=2026`` (o ``2024-2026``, ``tutti``) — griglia voci x periodi;
* la ricerca di un codice tributo resta ``GET /api/f24-riconciliazione/verifica-codice``;
* ``GET  /api/f24/piano-tributi/voci`` — le voci del piano;
* ``PUT  /api/f24/piano-tributi/voci/{id}`` — attiva/disattiva, scadenze, mesi;
* ``POST /api/f24/piano-tributi/voci`` — voce nuova su codici scelti.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
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
    anno: Optional[str] = Query(None, description="2026, 2024-2026, 2024,2026 oppure tutti"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    try:
        return await piano.griglia_anni(Database.get_db(), anno)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/piano-tributi/excel", summary="Scadenzario dei tributi in Excel (un versamento per riga)")
async def scadenzario_excel(
    request: Request,
    anno: Optional[str] = Query(None, description="2026, 2024-2026, 2024,2026 oppure tutti"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Response:
    from app.services import scadenzario_excel as xl

    db = Database.get_db()
    try:
        registro = await piano.registro_f24.carica_registro(db)
        anni = piano.anni_richiesti(anno, piano._modelli_con_righe(registro), datetime.now(timezone.utc).date())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    righe = await xl.righe_scadenzario(db, None if (anno or "").strip().lower() == "tutti" else anni)
    contenuto = xl.costruisci_xlsx(righe, base_url=str(request.base_url))
    return Response(
        content=contenuto,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{xl.nome_file(anno)}"'},
    )


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


@router.get("/piano-tributi/stipendi-da-pagare", summary="Netti dell'Elenco netti del consulente e stato dei bonifici")
async def stipendi_da_pagare(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Sola lettura: l'ultimo elenco netti canonico contro i pagamenti che HR ha gia' depositato."""
    from app.services import elenchi_netti
    from app.services.hr_pagamenti_deposito import _db_hr

    db_hr = _db_hr()
    indici: Dict[str, Any] = {}
    if db_hr is not None:
        from app.hr.routers.dipendenti_cloud import _indici_dipendenti
        indici = await _indici_dipendenti(db_hr)
    esito = await elenchi_netti.stipendi_da_pagare(Database.get_db(), db_hr, indici)
    esito["hr_disponibile"] = db_hr is not None
    return esito
