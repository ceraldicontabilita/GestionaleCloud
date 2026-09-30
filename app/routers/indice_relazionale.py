"""Indice relazionale (MINI-06) e relazioni documentali (DRV-03, parte minima).

Solo admin. L'indice legge `entity_relations` (sola lettura); il backfill dei
documenti e' simulazione per difetto e, oltre i 5 minuti del proxy Render, gira
in sottofondo con lo stato in ``sistema_stato`` (chiave ``relazioni_documentali``).
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.database import Database
from app.services import indice_relazionale as indice
from app.services import relazioni_documentali as documentali
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

_job_task: Optional[asyncio.Task] = None


def _filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id) -> Dict[str, Any]:
    return indice.costruisci_filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id)


@router.get("", summary="Indice relazionale: le relazioni fra entita' e documenti, le piu' recenti per prime")
async def elenco(
    origine_tipo: Optional[str] = Query(None), destinazione_tipo: Optional[str] = Query(None),
    relazione: Optional[str] = Query(None), stato: Optional[str] = Query(None, description="CONFERMATA | DA_VERIFICARE | REVOCATA"),
    entita_id: Optional[str] = Query(None, description="Id su uno dei due lati"),
    limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    letto = await indice.leggi_righe(Database.get_db(), _filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id))
    righe = sorted(letto["righe"], key=lambda r: (str(r["aggiornata"]), r["relation_key"]), reverse=True)
    pagina = [{**r, "importo": None if r["importo"] is None else f"{r['importo']:.2f}"} for r in righe[offset:offset + limit]]
    return {"riepilogo": indice.riepilogo(righe), "troncata": letto["troncata"],
            "limit": limit, "offset": offset, "righe": pagina}


@router.get("/export", summary="Esporta l'indice in csv, json o xlsx (stessi dati, stessi byte)")
async def esporta(
    formato: str = Query("csv", description="csv | json | xlsx"),
    origine_tipo: Optional[str] = Query(None), destinazione_tipo: Optional[str] = Query(None),
    relazione: Optional[str] = Query(None), stato: Optional[str] = Query(None),
    entita_id: Optional[str] = Query(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Response:
    if formato.lower() not in indice.FORMATI:
        raise HTTPException(status_code=400, detail={
            "code": "FORMATO_NON_VALIDO", "message": "formato: csv, json o xlsx", "details": {"formato": formato}})
    letto = await indice.leggi_righe(Database.get_db(), _filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id))
    if letto["troncata"]:
        raise HTTPException(status_code=413, detail={
            "code": "ESPORTAZIONE_TROPPO_GRANDE", "message": "restringi i filtri: l'esportazione e' oltre il limite",
            "details": {"limite": indice.LIMITE_LETTURA}})
    corpo, mime, nome = indice.esporta(letto["righe"], formato)
    return Response(content=corpo, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


async def _esegui(db, dry_run: bool) -> None:
    try:
        esito = await documentali.esegui(db, dry_run=dry_run)
        await db["sistema_stato"].update_one(
            {"chiave": documentali.CHIAVE_STATO}, {"$set": {"esito": esito, "errore": None, "in_corso": False}}, upsert=True)
    except Exception as exc:  # noqa: BLE001 - l'esito resta nello stato
        logger.exception("Relazioni documentali fallite: %s", type(exc).__name__)
        await db["sistema_stato"].update_one(
            {"chiave": documentali.CHIAVE_STATO},
            {"$set": {"errore": f"{type(exc).__name__}: {exc}", "in_corso": False}}, upsert=True)


@router.post("/relazioni-documentali/backfill", summary="Relazioni entita' -> documento Drive, in sottofondo (dry_run per difetto)")
async def backfill(
    dry_run: bool = Query(True, description="Se True calcola e non scrive"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    global _job_task
    if _job_task is not None and not _job_task.done():
        return {"avviato": False, **await _stato_dati()}
    db = Database.get_db()
    await db["sistema_stato"].update_one(
        {"chiave": documentali.CHIAVE_STATO}, {"$set": {"in_corso": True, "dry_run": dry_run}}, upsert=True)
    _job_task = asyncio.create_task(_esegui(db, dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def _stato_dati() -> Dict[str, Any]:
    stato = await Database.get_db()["sistema_stato"].find_one({"chiave": documentali.CHIAVE_STATO}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    stato["stato"] = "in_corso" if _job_task is not None and not _job_task.done() else "completato"
    return stato


@router.get("/relazioni-documentali/stato", summary="Esito dell'ultimo giro delle relazioni documentali")
async def stato(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return await _stato_dati()
