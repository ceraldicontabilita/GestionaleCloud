"""GC-02h — anteprima e segno delle registrazioni HACCP senza firma verificata.

La regola sta in `servizi/haccp_attendibilita.py`. Qui solo due ingressi,
entrambi riservati all'amministratore: l'anteprima (sola lettura) e il segno,
che per difetto e' una simulazione e scrive davvero solo con
`dry_run=false&conferma=SEGNA`.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.lotti.auth import request_actor, require_admin
from app.lotti.db import database as db
from app.lotti.servizi import haccp_attendibilita

router = APIRouter(prefix="/haccp-attendibilita", tags=["HACCP attendibilita'"])

CONFERMA = "SEGNA"


@router.get("/anteprima")
async def anteprima_non_attendibili(_admin=Depends(require_admin)):
    """Quante registrazioni verrebbero segnate, per collezione, anno e categoria."""
    return await haccp_attendibilita.anteprima(db)


@router.post("/segna")
async def segna_non_attendibili(
    request: Request,
    dry_run: bool = Query(default=True, description="Simulazione: non scrive niente"),
    conferma: str = Query(default="", description=f"Per scrivere davvero: {CONFERMA}"),
    _admin=Depends(require_admin),
):
    """Mette il segno `non_attendibili` sui documenti. I valori non si toccano."""
    if not dry_run and conferma != CONFERMA:
        raise HTTPException(
            status_code=400,
            detail=f"Per scrivere serve conferma={CONFERMA}: senza, usa dry_run=true.",
        )
    return await haccp_attendibilita.segna(db, request_actor(request), dry_run=dry_run)
