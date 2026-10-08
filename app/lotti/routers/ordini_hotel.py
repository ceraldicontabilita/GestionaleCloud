"""Ordini di dolce/salato ricevuti dalle strutture convenzionate."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.lotti.auth import require_permesso
from app.lotti.servizi.consegna_hotel import consegna_e_invia
from app.lotti.servizi.lotto_acquaviva import sposta_fattura_in_uso, stato_fattura_in_uso
from app.lotti.servizi.ordini_hotel import (
    aggiorna_ordine,
    associa_lotto,
    lista_ordini,
)


router = APIRouter(prefix="/ordini-hotel", tags=["Ordini Hotel"])


class StatoOrdine(BaseModel):
    stato: Optional[str] = None
    pagamento: Optional[str] = None


class SpostaFattura(BaseModel):
    azione: str = Field(pattern="^(successiva|precedente)$")


class Consegna(BaseModel):
    solo_pdf: bool = False


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


@router.get("/acquaviva/fattura-in-uso")
async def fattura_acquaviva_in_uso(_ruolo=Depends(require_permesso("produzione"))):
    """Fattura Acquaviva da cui nascono i lotti automatici, con la precedente e la successiva."""
    return await stato_fattura_in_uso()


@router.post("/acquaviva/fattura-in-uso")
async def sposta_fattura_acquaviva(body: SpostaFattura, _ruolo=Depends(require_permesso("produzione"))):
    try:
        return await sposta_fattura_in_uso(
            body.azione, da=str((_ruolo or {}).get("nome") or (_ruolo or {}).get("ruolo") or "operatore_lotti"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


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


@router.post("/{ordine_id}/consegna")
async def consegna(ordine_id: str, body: Consegna, _ruolo=Depends(require_permesso("produzione"))):
    """Ordine consegnato all'albergatore + PDF alla sua email (`solo_pdf`: solo il rinvio, senza cambiare stato)."""
    try:
        esito = await consegna_e_invia(
            ordine_id, solo_pdf=body.solo_pdf,
            da=str((_ruolo or {}).get("nome") or (_ruolo or {}).get("ruolo") or "operatore_lotti"))
    except ValueError as exc:
        dettaglio = str(exc)
        raise HTTPException(404 if "non trovato" in dettaglio else 422, dettaglio) from exc
    return {"ordine": esito["ordine"], "email_inviata": esito["email_inviata"], "a": esito["a"],
            "errore": esito["errore"]}
