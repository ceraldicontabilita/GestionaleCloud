"""
Gestione Utenti con PIN personale (solo admin).

L'amministratore crea/modifica/elimina utenti con ruolo Operatore o Sola
lettura, ciascuno con un PIN personale. Endpoint tutti riservati all'admin
(dependency richiedi_admin). Il login vero e proprio avviene su /api/pin-login.
"""
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body

from app.database import Database
from app.utils.ruoli import richiedi_admin
from app.services import utenti_pin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Utenti"])


@router.get("/utenti")
async def elenco_utenti(_admin: Dict[str, Any] = Depends(richiedi_admin)):
    """Elenco utenti PIN (senza dati segreti)."""
    db = Database.get_db()
    return {"utenti": await utenti_pin.lista_utenti(db)}


@router.post("/utenti")
async def nuovo_utente(
    payload: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
):
    """Crea un utente con nome, ruolo (operatore|sola_lettura) e PIN."""
    db = Database.get_db()
    try:
        utente = await utenti_pin.crea_utente(
            db,
            nome=payload.get("nome", ""),
            ruolo=payload.get("ruolo", ""),
            pin=str(payload.get("pin", "")).strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "utente": utente}


@router.put("/utenti/{utente_id}")
async def modifica_utente(
    utente_id: str,
    payload: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
):
    """Aggiorna nome, ruolo, stato attivo e/o PIN di un utente."""
    db = Database.get_db()
    pin = payload.get("pin")
    pin = str(pin).strip() if pin not in (None, "") else None
    try:
        ok = await utenti_pin.aggiorna_utente(
            db, utente_id,
            nome=payload.get("nome"),
            ruolo=payload.get("ruolo"),
            attivo=payload.get("attivo"),
            pin=pin,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Utente non trovato o nessuna modifica")
    return {"success": True}


@router.delete("/utenti/{utente_id}")
async def rimuovi_utente(
    utente_id: str,
    _admin: Dict[str, Any] = Depends(richiedi_admin),
):
    """Elimina un utente PIN."""
    db = Database.get_db()
    if not await utenti_pin.elimina_utente(db, utente_id):
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return {"success": True}
