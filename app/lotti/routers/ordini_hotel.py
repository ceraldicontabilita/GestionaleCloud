"""Ordini di dolce/salato ricevuti dalle strutture convenzionate."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.lotti.auth import require_permesso
from app.lotti.servizi.ordini_hotel import (
    aggiorna_ordine,
    associa_lotto,
    lista_ordini,
)


router = APIRouter(prefix="/ordini-hotel", tags=["Ordini Hotel"])


class StatoOrdine(BaseModel):
    stato: Optional[str] = None
    pagamento: Optional[str] = None


class AssociaLotto(BaseModel):
    chiave: str = Field(min_length=1, max_length=180)
    lotto_id: str = Field(min_length=1, max_length=180)


@router.get("")
async def elenco(_ruolo=Depends(require_permesso("produzione"))):
    ordini = await lista_ordini({}, 500)
    return {"ordini": ordini}


@router.get("/riepilogo")
async def riepilogo(_ruolo=Depends(require_permesso("produzione"))):
    ordini = await lista_ordini({"stato": {"$nin": ["consegnato", "annullato"]}}, 500)
    da_incassare = sum(
        float(o.get("totale") or 0) for o in ordini if o.get("pagamento") != "incassato"
    )
    return {"pendenti": len(ordini), "da_incassare": round(da_incassare, 2)}


@router.patch("/{ordine_id}")
async def aggiorna(ordine_id: str, body: StatoOrdine,
                    _ruolo=Depends(require_permesso("produzione"))):
    try:
        ordine = await aggiorna_ordine(
            ordine_id,
            stato=body.stato,
            pagamento=body.pagamento,
            da=str((_ruolo or {}).get("nome") or (_ruolo or {}).get("ruolo") or "operatore_lotti"),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not ordine:
        raise HTTPException(404, "Ordine hotel non trovato")
    return ordine


@router.post("/{ordine_id}/lotti")
async def collega_lotto(ordine_id: str, body: AssociaLotto,
                         _ruolo=Depends(require_permesso("produzione"))):
    try:
        return await associa_lotto(
            ordine_id,
            body.chiave,
            body.lotto_id,
            da=str((_ruolo or {}).get("nome") or (_ruolo or {}).get("ruolo") or "operatore_lotti"),
        )
    except ValueError as exc:
        dettaglio = str(exc)
        raise HTTPException(404 if "non trovato" in dettaglio else 422, dettaglio) from exc
