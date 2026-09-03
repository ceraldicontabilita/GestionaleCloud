"""Prezzi comunicati direttamente dai fornitori per i cataloghi.

Il valore e la sua provenienza restano separati dai prezzi realmente pagati
estratti dalle fatture XML. In questo modo un preventivo/listino non diventa
per errore evidenza contabile di un acquisto.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.lotti.auth import require_admin
from app.lotti.db import database as db


router = APIRouter(prefix="/cataloghi", tags=["cataloghi_prezzi"])


class PrezzoFornitoreUpdate(BaseModel):
    fonte: str
    prezzo: float = Field(ge=0, le=1_000_000)
    prodotto_id: Optional[str] = ""
    codice_articolo: Optional[str] = ""
    fornitore: Optional[str] = ""


def _filtro_prodotto(payload: PrezzoFornitoreUpdate) -> tuple[str, dict]:
    fonte = (payload.fonte or "").strip().lower()
    if fonte in {"saima", "mepa"}:
        filtro = {"fonte": fonte}
        if payload.prodotto_id:
            filtro["id"] = payload.prodotto_id
        elif payload.codice_articolo:
            filtro["codice_articolo"] = payload.codice_articolo
        else:
            raise HTTPException(422, "ID o codice articolo obbligatorio")
        return "dizionario_ingredienti", filtro

    if fonte in {"acquaviva", "alpha"}:
        if not payload.prodotto_id:
            raise HTTPException(422, "ID prodotto obbligatorio")
        return "acquaviva_prodotti", {"id": payload.prodotto_id}

    fornitore = (payload.fornitore or fonte).strip().lower()
    if not fornitore or not payload.codice_articolo:
        raise HTTPException(422, "Fornitore e codice articolo obbligatori")
    return "catalogo_forno_prodotti", {
        "fornitore": fornitore,
        "codice_articolo": payload.codice_articolo,
    }


@router.put("/prezzo")
async def salva_prezzo_fornitore(
    payload: PrezzoFornitoreUpdate,
    _admin=Depends(require_admin),
):
    collezione, filtro = _filtro_prodotto(payload)
    aggiornato_il = datetime.now(timezone.utc).isoformat()
    result = await getattr(db, collezione).update_one(
        filtro,
        {"$set": {
            "prezzo_fornitore": float(payload.prezzo),
            "prezzo_fornitore_data": aggiornato_il,
            "prezzo_fornitore_fonte": "comunicato_dal_fornitore",
            "prezzo_fornitore_iva_esclusa": True,
        }},
    )
    if not result.matched_count:
        raise HTTPException(404, "Prodotto catalogo non trovato")
    return {
        "ok": True,
        "prezzo_fornitore": float(payload.prezzo),
        "prezzo_fornitore_data": aggiornato_il,
        "fonte": "comunicato_dal_fornitore",
        "iva_esclusa": True,
    }
