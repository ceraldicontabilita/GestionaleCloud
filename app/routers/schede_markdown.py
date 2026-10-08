"""Schede Markdown delle letture (cedolini): consultazione, eliminazione, ricarica.

Montato sotto ``/api/schede``. Tutto riservato all'amministratore: le schede
contengono dati personali dei dipendenti.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.database import Database
from app.services import schede_markdown as schede
from app.utils.ruoli import richiedi_admin

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(richiedi_admin)])

_MARKDOWN = "text/markdown; charset=utf-8"


@router.get("/cedolino/registro/{anno}", response_class=PlainTextResponse)
async def registro_cedolini(anno: int) -> PlainTextResponse:
    """Il registro Markdown dei cedolini di un anno."""
    db = Database.get_db()
    registro = await db[schede.REGISTRI].find_one({"id": f"{schede.TIPO_CEDOLINO}:{anno}"}, {"_id": 0})
    if not registro:
        registro = {"markdown": schede.registro_markdown(schede.TIPO_CEDOLINO, anno, [])}
    return PlainTextResponse(registro["markdown"], media_type=_MARKDOWN)


@router.get("/cedolino/{sha256}", response_class=PlainTextResponse)
async def scheda_cedolino(sha256: str) -> PlainTextResponse:
    """La scheda Markdown di un PDF di cedolini, per impronta SHA-256."""
    db = Database.get_db()
    scheda = await db[schede.SCHEDE].find_one(
        {"id": f"{schede.TIPO_CEDOLINO}:{sha256.lower()}"}, {"_id": 0, "markdown": 1},
    )
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    return PlainTextResponse(scheda["markdown"], media_type=_MARKDOWN)


@router.post("/cedolino/{sha256}/elimina")
async def elimina_scheda_cedolino(sha256: str, motivo: str = Query(..., min_length=3)) -> Dict[str, Any]:
    """Il cedolino e' stato tolto: la scheda resta marcata e il registro perde le sue righe."""
    esito = await schede.togli_scheda(Database.get_db(), sha256.lower(), motivo=motivo)
    if esito["esito"] == "non_trovata":
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    return esito


async def _ricarica_in_background(anno: Optional[int], dry_run: bool) -> None:
    db = Database.get_db()
    stato = {"chiave": schede.CHIAVE_RICARICA, "fase": "in_corso", "anno": anno, "dry_run": dry_run,
             "iniziata_il": datetime.now(timezone.utc).isoformat()}
    await db["sistema_stato"].update_one({"chiave": schede.CHIAVE_RICARICA}, {"$set": stato}, upsert=True)
    try:
        esito = await schede.ricarica_cedolini(db, anno=anno, dry_run=dry_run)
        esito["errori"] = esito["errori"][:200]
        stato = {"fase": "completata", "esito": esito}
    except Exception as exc:
        logger.exception("[schede] ricarica cedolini fallita")
        stato = {"fase": "errore", "errore": f"{type(exc).__name__}: {exc}"}
    stato["finita_il"] = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one({"chiave": schede.CHIAVE_RICARICA}, {"$set": stato})


@router.post("/cedolino/ricarica")
async def ricarica_cedolini(anno: Optional[int] = None, dry_run: bool = True) -> Dict[str, Any]:
    """Riscrive i cedolini dalle schede, in background; ``dry_run`` (predefinito) conta soltanto."""
    db = Database.get_db()
    stato = await db["sistema_stato"].find_one({"chiave": schede.CHIAVE_RICARICA}, {"_id": 0}) or {}
    if stato.get("fase") == "in_corso":
        raise HTTPException(status_code=409, detail="Ricarica gia' in corso")
    asyncio.create_task(_ricarica_in_background(anno, dry_run))
    return {"avviata": True, "anno": anno, "dry_run": dry_run}


@router.get("/cedolino/ricarica/stato")
async def stato_ricarica() -> Dict[str, Any]:
    db = Database.get_db()
    return await db["sistema_stato"].find_one({"chiave": schede.CHIAVE_RICARICA}, {"_id": 0}) or {"fase": "mai_avviata"}
