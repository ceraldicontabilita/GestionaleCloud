"""Scrittura canonica di una consegna al banco, condivisa dai flussi vivi."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.lotti.db import database as db


_LOG = logging.getLogger("uvicorn.error")


class VenditaBancoIn(BaseModel):
    prodotto_id: str
    prodotto_nome: str
    reparto: str = "rosticceria"
    pezzi_prodotti: int
    foto_url: Optional[str] = None
    data: Optional[str] = None
    lotto_id: Optional[str] = None
    numero_lotto: Optional[str] = None
    operatore_nome: Optional[str] = None
    operatore_id: Optional[str] = None
    consumo_immediato: bool = False


async def registra_vendita_banco(
    payload: VenditaBancoIn, *, operation_id: Optional[str] = None,
) -> dict:
    """Registra una consegna; l'ID operazione del lotto rende sicuro il retry."""
    vendita_id = (str(uuid.uuid5(uuid.NAMESPACE_URL, operation_id))
                  if operation_id else str(uuid.uuid4()))
    doc = {
        "id": vendita_id,
        "prodotto_id": payload.prodotto_id,
        "prodotto_nome": payload.prodotto_nome,
        "reparto": payload.reparto,
        "foto_url": payload.foto_url,
        "pezzi_prodotti": payload.pezzi_prodotti,
        "pezzi_invenduto": 0 if payload.consumo_immediato else None,
        "pezzi_venduti": payload.pezzi_prodotti if payload.consumo_immediato else None,
        "data": payload.data or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "lotto_id": payload.lotto_id or None,
        "numero_lotto": payload.numero_lotto or None,
        "operatore_nome": payload.operatore_nome or None,
        "operatore_id": payload.operatore_id or None,
        "consumo_immediato": payload.consumo_immediato,
        "creato_at": datetime.now(timezone.utc).isoformat(),
        "invenduto_at": None,
        "stato": "chiuso" if payload.consumo_immediato else "aperto",
    }
    if operation_id:
        doc["_id"] = vendita_id
    try:
        await db.vendite_banco.insert_one(doc)
    except DuplicateKeyError:
        if not operation_id:
            raise
        precedente = await db.vendite_banco.find_one({"_id": vendita_id}, {"_id": 0})
        if precedente is None:
            raise
        return precedente
    doc.pop("_id", None)
    try:
        from app.lotti.utils.activity_log import registra_attivita

        await registra_attivita(
            payload.operatore_nome, "vendita_banco",
            f"{payload.operatore_nome or 'Operatore'} ha inviato al banco "
            f"{payload.pezzi_prodotti}× {payload.prodotto_nome}",
            payload.reparto or "",
            extra={"prodotto": payload.prodotto_nome, "pezzi": payload.pezzi_prodotti},
        )
    except Exception:
        _LOG.debug("[vendita_banco] attività non registrata")
    return doc
