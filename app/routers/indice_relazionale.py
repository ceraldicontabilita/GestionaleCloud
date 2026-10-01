"""Indice relazionale (MINI-06) e relazioni documentali (DRV-03).

Solo admin. L'indice legge `entity_relations` (sola lettura); i giri sui documenti
sono simulazione per difetto e, oltre i 5 minuti del proxy Render, girano in
sottofondo con lo stato in ``sistema_stato``: ``relazioni_documentali`` (backfill
entita' -> documento Drive) e ``protocollo_collegamenti`` (collegamenti del
protocollo verso entita' sparite, riaggancio per id).
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException
from fastapi.responses import Response

from app.database import Database
from app.services import indice_relazionale as indice
from app.services import protocollo_collegamenti as collegamenti
from app.services import relazioni_documentali as documentali
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

_job_task: Optional[asyncio.Task] = None
_job_collegamenti: Optional[asyncio.Task] = None


def _filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id, documento=None) -> Dict[str, Any]:
    return indice.costruisci_filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id, documento)


@router.get("", summary="Indice relazionale: le relazioni fra entita' e documenti, le piu' recenti per prime")
async def elenco(
    origine_tipo: Optional[str] = Query(None), destinazione_tipo: Optional[str] = Query(None),
    relazione: Optional[str] = Query(None), stato: Optional[str] = Query(None, description="CONFERMATA | DA_VERIFICARE | REVOCATA"),
    entita_id: Optional[str] = Query(None, description="Id su uno dei due lati"),
    documento: Optional[str] = Query(None, description="drive_id di un documento: le entita' che lo hanno per originale"),
    limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    letto = await indice.leggi_righe(Database.get_db(), _filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id, documento))
    righe = sorted(letto["righe"], key=lambda r: (str(r["aggiornata"]), r["relation_key"]), reverse=True)
    pagina = [{**r, "importo": None if r["importo"] is None else f"{r['importo']:.2f}"} for r in righe[offset:offset + limit]]
    return {"riepilogo": indice.riepilogo(righe), "troncata": letto["troncata"],
            "limit": limit, "offset": offset, "righe": pagina}


@router.get("/export", summary="Esporta l'indice in csv, json o xlsx (stessi dati, stessi byte)")
async def esporta(
    formato: str = Query("csv", description="csv | json | xlsx"),
    origine_tipo: Optional[str] = Query(None), destinazione_tipo: Optional[str] = Query(None),
    relazione: Optional[str] = Query(None), stato: Optional[str] = Query(None),
    entita_id: Optional[str] = Query(None), documento: Optional[str] = Query(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Response:
    if formato.lower() not in indice.FORMATI:
        raise HTTPException(status_code=400, detail={
            "code": "FORMATO_NON_VALIDO", "message": "formato: csv, json o xlsx", "details": {"formato": formato}})
    letto = await indice.leggi_righe(Database.get_db(), _filtro(origine_tipo, destinazione_tipo, relazione, stato, entita_id, documento))
    if letto["troncata"]:
        raise HTTPException(status_code=413, detail={
            "code": "ESPORTAZIONE_TROPPO_GRANDE", "message": "restringi i filtri: l'esportazione e' oltre il limite",
            "details": {"limite": indice.LIMITE_LETTURA}})
    corpo, mime, nome = indice.esporta(letto["righe"], formato)
    return Response(content=corpo, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


async def _scrivi_esito(db, chiave: str, esito: Optional[Dict[str, Any]], errore: Optional[str]) -> None:
    campi: Dict[str, Any] = {"errore": errore, "in_corso": False}
    if esito is not None:
        campi["esito"] = esito
    await db["sistema_stato"].update_one({"chiave": chiave}, {"$set": campi}, upsert=True)


async def _esegui(db, dry_run: bool, limite: int) -> None:
    try:
        esito = await documentali.esegui(db, dry_run=dry_run, leggi_hr=documentali.leggi_id_hr, limite=limite)
        await _scrivi_esito(db, documentali.CHIAVE_STATO, esito, None)
    except Exception as exc:  # noqa: BLE001 - l'esito resta nello stato
        logger.exception("Relazioni documentali fallite: %s", type(exc).__name__)
        await _scrivi_esito(db, documentali.CHIAVE_STATO, None, f"{type(exc).__name__}: {exc}")


async def _esegui_collegamenti(db, dry_run: bool) -> None:
    try:
        esito = await collegamenti.esegui(db, dry_run=dry_run)
        await _scrivi_esito(db, collegamenti.CHIAVE_STATO, esito, None)
    except Exception as exc:  # noqa: BLE001 - l'esito resta nello stato
        logger.exception("Bonifica collegamenti del protocollo fallita: %s", type(exc).__name__)
        await _scrivi_esito(db, collegamenti.CHIAVE_STATO, None, f"{type(exc).__name__}: {exc}")


async def _avvia(db, chiave: str, corrente: Optional[asyncio.Task], dry_run: bool,
                 lavoro: Callable[[], Awaitable[None]]):
    if corrente is not None and not corrente.done():
        return None, {"avviato": False, **await _stato_dati(chiave, corrente)}
    await db["sistema_stato"].update_one(
        {"chiave": chiave}, {"$set": {"in_corso": True, "dry_run": dry_run}}, upsert=True)
    return asyncio.create_task(lavoro()), {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def _stato_dati(chiave: str, task: Optional[asyncio.Task]) -> Dict[str, Any]:
    stato = await Database.get_db()["sistema_stato"].find_one({"chiave": chiave}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    stato["stato"] = "in_corso" if task is not None and not task.done() else "completato"
    return stato


@router.post("/relazioni-documentali/backfill", summary="Relazioni entita' -> documento Drive, in sottofondo (dry_run per difetto)")
async def backfill(
    dry_run: bool = Query(True, description="Se True calcola e non scrive"),
    limite: int = Query(documentali.LIMITE_SCRITTURE, ge=1, le=20000,
                        description="Scritture per giro (relazioni e drive_file_id dei cedolini); si ripete finche' restanti = 0"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    global _job_task
    db = Database.get_db()
    task, risposta = await _avvia(db, documentali.CHIAVE_STATO, _job_task, dry_run,
                                  lambda: _esegui(db, dry_run, limite))
    if task is not None:
        _job_task = task
    return risposta


@router.get("/relazioni-documentali/stato", summary="Esito dell'ultimo giro delle relazioni documentali")
async def stato(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return await _stato_dati(documentali.CHIAVE_STATO, _job_task)


@router.post("/protocollo-collegamenti/bonifica",
             summary="Collegamenti del protocollo verso entita' sparite: riaggancio per id (dry_run per difetto)")
async def bonifica_collegamenti(
    dry_run: bool = Query(True, description="Se True elenca i riagganci e non scrive"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    global _job_collegamenti
    db = Database.get_db()
    task, risposta = await _avvia(db, collegamenti.CHIAVE_STATO, _job_collegamenti, dry_run,
                                  lambda: _esegui_collegamenti(db, dry_run))
    if task is not None:
        _job_collegamenti = task
    return risposta


@router.get("/protocollo-collegamenti/stato", summary="Esito dell'ultima bonifica dei collegamenti del protocollo")
async def stato_collegamenti(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return await _stato_dati(collegamenti.CHIAVE_STATO, _job_collegamenti)
