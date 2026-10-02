"""GC-02h — anteprima e segno delle registrazioni HACCP senza firma verificata.

La regola sta in `servizi/haccp_attendibilita.py`. Qui solo due ingressi,
entrambi riservati all'amministratore: l'anteprima (sola lettura) e il segno,
che per difetto e' una simulazione e scrive davvero solo con
`dry_run=false&conferma=SEGNA`.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.lotti.auth import request_actor, require_admin, require_permesso
from app.lotti.db import database as db
from app.lotti.servizi import haccp_attendibilita
from app.lotti.routers.chiusure import get_tutte_chiusure

router = APIRouter(prefix="/haccp-attendibilita", tags=["HACCP attendibilita'"])

CONFERMA = "SEGNA"
CONFERMA_CHIUSURE = "INSERISCI_CHIUSO"


@router.get("/anteprima")
async def anteprima_non_attendibili(_admin=Depends(require_admin)):
    """Quante registrazioni verrebbero segnate, per collezione, anno e categoria."""
    return await haccp_attendibilita.anteprima(db)


@router.post("/segna")
async def segna_non_attendibili(
    request: Request,
    dry_run: bool = Query(default=True, description="Simulazione: non scrive niente"),
    conferma: str = Query(default="", description=f"Per scrivere davvero: {CONFERMA}"),
    _ruolo=Depends(require_permesso("haccp_registri")),
):
    """Mette il segno `non_attendibili` sui documenti. I valori non si toccano."""
    if not dry_run and conferma != CONFERMA:
        raise HTTPException(
            status_code=400,
            detail=f"Per scrivere serve conferma={CONFERMA}: senza, usa dry_run=true.",
        )
    return await haccp_attendibilita.segna(db, request_actor(request), dry_run=dry_run)


@router.post("/regolarizza-chiusure")
async def regolarizza_chiusure(
    request: Request,
    anno: int = Query(..., ge=2000, le=2100),
    dry_run: bool = Query(default=True),
    conferma: str = Query(default=""),
    _ruolo=Depends(require_permesso("haccp_registri")),
):
    """Scrive «Chiuso» sulle temperature importate e non firmate dei giorni chiusi."""
    if not dry_run and conferma != CONFERMA_CHIUSURE:
        raise HTTPException(
            status_code=400,
            detail=f"Per scrivere serve conferma={CONFERMA_CHIUSURE}.",
        )
    calendario = await get_tutte_chiusure(anno)
    chiuse = {
        data: info for data, info in calendario["chiusure_dict"].items()
        if info.get("is_chiuso", True)
    }
    return await haccp_attendibilita.regolarizza_temperature_chiusure(
        db, anno, chiuse, request_actor(request), dry_run=dry_run,
    )
