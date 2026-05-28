"""
API REST per la whitelist mittenti email attendibili.

Solo da questi mittenti il gestionale importa documenti via Gmail in modo
automatico. Le fatture XML, anche se arrivano da mittenti in whitelist,
NON vengono mai importate via Gmail (regola CLAUDE.md): vengono messe in
quarantena con alert "fattura trovata in email -- usare upload manuale".
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import Database
from app.services import mittenti_attendibili as servizio

router = APIRouter()


class MittentePayload(BaseModel):
    email: str = Field(..., description="Indirizzo email o pattern (es. '@adm.gov.it')")
    descrizione: str = ""
    categoria_default: str = "altro"
    modulo_destinazione: Optional[str] = None
    attivo: bool = True


@router.get("/categorie")
async def elenca_categorie():
    """Categorie supportate + modulo destinazione di default."""
    return {
        "categorie": servizio.CATEGORIE_DOCUMENTO,
        "moduli_default": servizio.MODULO_DESTINAZIONE_DEFAULT,
    }


@router.get("")
async def lista_mittenti(solo_attivi: bool = False):
    """Elenco mittenti attendibili."""
    db = Database.get_db()
    items = await servizio.elenca_mittenti(db, solo_attivi=solo_attivi)
    return {"totale": len(items), "mittenti": items}


@router.post("")
async def crea_o_aggiorna_mittente(payload: MittentePayload):
    """Inserisce o aggiorna (upsert per email) un mittente attendibile."""
    db = Database.get_db()
    try:
        res = await servizio.upsert_mittente(
            db,
            email=payload.email,
            descrizione=payload.descrizione,
            categoria_default=payload.categoria_default,
            modulo_destinazione=payload.modulo_destinazione,
            attivo=payload.attivo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"errore": str(exc)})
    return {"ok": True, **res}


@router.post("/{email}/disattiva")
async def disattiva(email: str):
    db = Database.get_db()
    ok = await servizio.disattiva_mittente(db, email)
    if not ok:
        raise HTTPException(status_code=404, detail={"errore": "mittente_non_trovato"})
    return {"ok": True}


@router.post("/{email}/riattiva")
async def riattiva(email: str):
    db = Database.get_db()
    ok = await servizio.riattiva_mittente(db, email)
    if not ok:
        raise HTTPException(status_code=404, detail={"errore": "mittente_non_trovato"})
    return {"ok": True}


@router.delete("/{email}")
async def elimina(email: str):
    """Eliminazione hard (sconsigliata: meglio disattivare)."""
    db = Database.get_db()
    ok = await servizio.elimina_mittente(db, email)
    if not ok:
        raise HTTPException(status_code=404, detail={"errore": "mittente_non_trovato"})
    return {"ok": True}


@router.post("/seed-iniziale")
async def seed_iniziale():
    """Crea i mittenti tipici italiani (AdER, AdE, INPS, INAIL, Vicedomini).

    Idempotente: chiama upsert su ogni voce, non duplica nulla.
    """
    db = Database.get_db()
    creati = await servizio.seed_mittenti_iniziali(db)
    return {"ok": True, "nuovi_inseriti": creati}
