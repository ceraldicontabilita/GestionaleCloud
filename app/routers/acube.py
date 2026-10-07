"""A-Cube: fatture passive via API (vedi ``app/services/acube.py``).

- ``POST /api/acube/webhook`` — pubblico, protetto dal segreto nell'header.
- tutto il resto richiede la sessione; le azioni di configurazione l'admin.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response

from app.database import Database
from app.services import acube
from app.utils.dependencies import get_current_admin_user, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _errore(exc: acube.AcubeErrore) -> HTTPException:
    return HTTPException(status_code=exc.stato, detail=str(exc))


async def _acquisisci_in_background(uuid: str) -> None:
    db = Database.get_db()
    try:
        esito = await acube.acquisisci(db, uuid, via="webhook")
        logger.info("[acube] webhook %s -> %s", uuid, esito.get("stato"))
    except Exception as exc:
        # Il controllo giornaliero la ripesca: nessuna fattura persa.
        logger.warning("[acube] webhook %s non acquisito: %s: %s", uuid, type(exc).__name__, exc)


@router.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks,
                  authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    db = Database.get_db()
    if not await acube.webhook_autorizzato(db, authorization):
        raise HTTPException(status_code=401, detail="Webhook A-Cube non autorizzato")
    try:
        corpo = await request.json()
    except Exception:
        corpo = None
    uuid = acube.uuid_dal_corpo(corpo)
    if not uuid:
        # 200: un corpo senza fattura non va ritentato per dieci ore.
        return {"ricevuto": True, "uuid": None}
    background.add_task(_acquisisci_in_background, uuid)
    return {"ricevuto": True, "uuid": uuid}


@router.get("/stato")
async def stato(_user=Depends(get_current_user)) -> Dict[str, Any]:
    return await acube.stato(Database.get_db())


@router.post("/verifica-accesso")
async def verifica_accesso(_user=Depends(get_current_admin_user)) -> Dict[str, Any]:
    ok, messaggio = await acube.verifica_accesso()
    return {"ok": ok, "messaggio": messaggio, "ambiente": acube.ambiente()}


@router.post("/registra-webhook")
async def registra_webhook(_user=Depends(get_current_admin_user)) -> Dict[str, Any]:
    try:
        return await acube.registra_webhook(Database.get_db())
    except acube.AcubeErrore as exc:
        raise _errore(exc)


@router.post("/controlla")
async def controlla(giorni: int = Query(acube.GIORNI_CONTROLLO, ge=1, le=30),
                   _user=Depends(get_current_admin_user)) -> Dict[str, Any]:
    try:
        return await acube.controlla(Database.get_db(), giorni)
    except acube.AcubeErrore as exc:
        raise _errore(exc)


@router.post("/simula")
async def simula(_user=Depends(get_current_admin_user)) -> Dict[str, Any]:
    try:
        return await acube.simula_fattura_passiva()
    except acube.AcubeErrore as exc:
        raise _errore(exc)


@router.get("/fatture")
async def fatture(limite: int = Query(50, ge=1, le=500),
                  _user=Depends(get_current_user)) -> Dict[str, Any]:
    db = Database.get_db()
    righe = await db[acube.REGISTRO].find({}, {"_id": 0}).sort("registrata_il", -1).limit(limite).to_list(limite)
    totale = await db[acube.REGISTRO].count_documents({})
    return {"fatture": righe, "totale": totale}


@router.get("/fatture/{uuid}/vista")
async def vista(uuid: str, formato: str = Query("html", pattern="^(html|pdf|xml)$"),
                _user=Depends(get_current_user)) -> Response:
    db = Database.get_db()
    riga = await db[acube.REGISTRO].find_one({"uuid": uuid}, {"_id": 0, "uuid": 1, "sdi_file_name": 1})
    if not riga:
        raise HTTPException(status_code=404, detail="Fattura A-Cube non presente nel registro")
    try:
        r = await acube.leggi(uuid, formato)
    except acube.AcubeErrore as exc:
        raise _errore(exc)
    tipi = {"html": "text/html; charset=utf-8", "pdf": "application/pdf", "xml": "application/xml"}
    nome = (riga.get("sdi_file_name") or uuid).rsplit(".", 1)[0]
    return Response(content=r.content, media_type=tipi[formato],
                    headers={"Content-Disposition": f'inline; filename="{nome}.{formato}"',
                             "Cache-Control": "no-store"})
