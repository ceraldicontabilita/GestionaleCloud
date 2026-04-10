"""
PIN Manager — Gestione PIN operatori
Endpoint per impostare, verificare e resettare i PIN dei dipendenti.
I PIN vengono salvati come hash bcrypt in dipendenti.pin
"""
from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone
import bcrypt
import logging

from app.database import Database, Collections

router = APIRouter()
logger = logging.getLogger(__name__)


def _hash_pin(pin: str) -> str:
    """Hash del PIN con bcrypt."""
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(pin.encode('utf-8'), salt).decode('utf-8')


def _verifica_pin(pin: str, hashed: str) -> bool:
    """Verifica PIN contro hash."""
    try:
        return bcrypt.checkpw(pin.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


@router.get("/pin/lista")
async def lista_dipendenti_pin() -> Dict[str, Any]:
    """
    Lista tutti i dipendenti con stato PIN (ha_pin: true/false).
    Non restituisce mai il PIN o l'hash.
    """
    db = Database.get_db()
    dipendenti = await db[Collections.DIPENDENTI].find(
        {"attivo": {"$ne": False}},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1,
         "mansione": 1, "pin": 1}
    ).sort("nome_completo", 1).to_list(200)

    result = []
    for d in dipendenti:
        result.append({
            "id":            d.get("id"),
            "nome_completo": d.get("nome_completo") or
                             f"{d.get('nome', '')} {d.get('cognome', '')}".strip(),
            "mansione":      d.get("mansione", ""),
            "ha_pin":        bool(d.get("pin")),
        })

    totale     = len(result)
    con_pin    = sum(1 for d in result if d["ha_pin"])
    senza_pin  = totale - con_pin

    return {
        "dipendenti":  result,
        "totale":      totale,
        "con_pin":     con_pin,
        "senza_pin":   senza_pin,
    }


@router.post("/pin/imposta/{dipendente_id}")
async def imposta_pin(
    dipendente_id: str,
    body: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Imposta o aggiorna il PIN di un dipendente.
    Il PIN deve essere di 4 cifre numeriche.
    """
    db = Database.get_db()

    pin = str(body.get("pin") or "").strip()

    # Validazione
    if not pin:
        raise HTTPException(400, "PIN mancante")
    if not pin.isdigit():
        raise HTTPException(400, "Il PIN deve contenere solo cifre")
    if len(pin) != 4:
        raise HTTPException(400, "Il PIN deve essere di esattamente 4 cifre")

    # Verifica che il dipendente esista
    dipendente = await db[Collections.DIPENDENTI].find_one({"id": dipendente_id})
    if not dipendente:
        raise HTTPException(404, "Dipendente non trovato")

    nome = dipendente.get("nome_completo") or \
           f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()

    # Hasha e salva
    pin_hash = _hash_pin(pin)
    await db[Collections.DIPENDENTI].update_one(
        {"id": dipendente_id},
        {"$set": {
            "pin":            pin_hash,
            "pin_updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    logger.info(f"[PINManager] PIN impostato per {nome} ({dipendente_id})")
    return {"success": True, "messaggio": f"PIN impostato per {nome}"}


@router.post("/pin/verifica/{dipendente_id}")
async def verifica_pin(
    dipendente_id: str,
    body: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Verifica il PIN di un dipendente.
    Usato dal tablet per il login operatore.
    """
    db = Database.get_db()

    pin = str(body.get("pin") or "").strip()
    if not pin:
        raise HTTPException(400, "PIN mancante")

    dipendente = await db[Collections.DIPENDENTI].find_one(
        {"id": dipendente_id},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1,
         "cognome": 1, "mansione": 1, "pin": 1}
    )
    if not dipendente:
        raise HTTPException(404, "Dipendente non trovato")

    pin_hash = dipendente.get("pin") or ""
    if not pin_hash:
        raise HTTPException(400, "Nessun PIN configurato per questo dipendente")

    valido = _verifica_pin(pin, pin_hash)
    if not valido:
        return {"valido": False, "messaggio": "PIN non corretto"}

    nome = dipendente.get("nome_completo") or \
           f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()

    return {
        "valido":        True,
        "dipendente_id": dipendente_id,
        "nome":          nome,
        "mansione":      dipendente.get("mansione", ""),
    }


@router.delete("/pin/reset/{dipendente_id}")
async def reset_pin(dipendente_id: str) -> Dict[str, Any]:
    """Rimuove il PIN di un dipendente (admin only)."""
    db = Database.get_db()

    dipendente = await db[Collections.DIPENDENTI].find_one({"id": dipendente_id})
    if not dipendente:
        raise HTTPException(404, "Dipendente non trovato")

    nome = dipendente.get("nome_completo") or \
           f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()

    await db[Collections.DIPENDENTI].update_one(
        {"id": dipendente_id},
        {"$unset": {"pin": ""}, "$set": {"pin_updated_at": None}}
    )

    logger.info(f"[PINManager] PIN rimosso per {nome}")
    return {"success": True, "messaggio": f"PIN rimosso per {nome}"}


@router.post("/pin/imposta-bulk")
async def imposta_pin_bulk(
    body: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Imposta i PIN per più dipendenti in una sola chiamata.
    Body: {"dipendenti": [{"id": "xxx", "pin": "1234"}, ...]}
    """
    db = Database.get_db()
    entries: List[Dict] = body.get("dipendenti") or []

    if not entries:
        raise HTTPException(400, "Lista dipendenti vuota")

    ok = []
    errori = []

    for entry in entries:
        dip_id = entry.get("id") or ""
        pin    = str(entry.get("pin") or "").strip()

        if not dip_id or not pin:
            errori.append({"id": dip_id, "errore": "id o pin mancante"})
            continue
        if not pin.isdigit() or len(pin) != 4:
            errori.append({"id": dip_id, "errore": "PIN non valido (servono 4 cifre)"})
            continue

        dipendente = await db[Collections.DIPENDENTI].find_one({"id": dip_id})
        if not dipendente:
            errori.append({"id": dip_id, "errore": "dipendente non trovato"})
            continue

        pin_hash = _hash_pin(pin)
        await db[Collections.DIPENDENTI].update_one(
            {"id": dip_id},
            {"$set": {
                "pin":            pin_hash,
                "pin_updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        nome = dipendente.get("nome_completo") or dip_id
        ok.append(nome)

    return {
        "successi": len(ok),
        "errori":   len(errori),
        "ok":       ok,
        "errori_dettaglio": errori,
    }
