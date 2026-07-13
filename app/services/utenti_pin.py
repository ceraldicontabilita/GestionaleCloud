"""
Utenti con accesso via PIN personale (scelta utente 13/07/2026).

Ogni utente ha un PIN a 6 cifre e un ruolo (operatore | sola_lettura | admin).
L'amministratore "storico" continua a entrare col PIN da variabile d'ambiente
(ADMIN_PIN/PIN_HASH_ADMIN); questi sono utenti AGGIUNTIVI creati dall'admin
dalla pagina Utenti.

Sicurezza PIN: il PIN non è mai salvato in chiaro. Si conserva un salt casuale
per utente e `sha256(salt + pin)`. La verifica al login itera sugli utenti
attivi (pochi) e confronta in tempo costante. La difesa dal brute force è il
lockout condiviso (5 tentativi / 5 min, app/utils/login_lockout.py).

Collection: `utenti_pin`.
"""
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.utils.ruoli import RUOLI_VALIDI, normalizza_ruolo

COLLECTION = "utenti_pin"


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pin_valido(pin: str) -> bool:
    return bool(pin) and pin.isdigit() and 4 <= len(pin) <= 12


async def lista_utenti(db) -> List[Dict[str, Any]]:
    """Elenco utenti PIN SENZA campi segreti (no salt/hash)."""
    utenti = await db[COLLECTION].find(
        {}, {"_id": 0, "pin_salt": 0, "pin_hash": 0}
    ).sort("nome", 1).to_list(500)
    return utenti


async def crea_utente(db, nome: str, ruolo: str, pin: str) -> Dict[str, Any]:
    """Crea un utente PIN. Ritorna il record pubblico. Solleva ValueError su input errati."""
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Il nome è obbligatorio")
    ruolo = (ruolo or "").strip().lower()
    if ruolo not in RUOLI_VALIDI:
        raise ValueError(f"Ruolo non valido: {ruolo}")
    if not pin_valido(pin):
        raise ValueError("PIN non valido: solo cifre, da 4 a 12")

    # Il PIN deve essere univoco tra tutti gli utenti attivi (altrimenti il
    # login sarebbe ambiguo) e non deve coincidere con l'ADMIN_PIN a env.
    admin_pin = os.getenv("ADMIN_PIN", "").strip()
    if admin_pin and hmac.compare_digest(pin, admin_pin):
        raise ValueError("Questo PIN è riservato all'amministratore")
    if await _pin_gia_usato(db, pin):
        raise ValueError("PIN già assegnato a un altro utente: scegline un altro")

    salt = uuid.uuid4().hex
    doc = {
        "id": uuid.uuid4().hex,
        "nome": nome,
        "ruolo": ruolo,  # già validato contro RUOLI_VALIDI
        "pin_salt": salt,
        "pin_hash": _hash_pin(pin, salt),
        "attivo": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[COLLECTION].insert_one(doc)
    return {k: v for k, v in doc.items() if k not in ("_id", "pin_salt", "pin_hash")}


async def _pin_gia_usato(db, pin: str, escludi_id: Optional[str] = None) -> bool:
    async for u in db[COLLECTION].find({"attivo": True}, {"_id": 0, "id": 1, "pin_salt": 1, "pin_hash": 1}):
        if escludi_id and u.get("id") == escludi_id:
            continue
        if hmac.compare_digest(_hash_pin(pin, u.get("pin_salt", "")), u.get("pin_hash", "")):
            return True
    return False


async def aggiorna_utente(db, utente_id: str, nome=None, ruolo=None, attivo=None, pin=None) -> bool:
    """Aggiorna i campi indicati. Ritorna True se un documento è stato toccato."""
    update: Dict[str, Any] = {}
    if nome is not None:
        nome = nome.strip()
        if not nome:
            raise ValueError("Il nome non può essere vuoto")
        update["nome"] = nome
    if ruolo is not None:
        ruolo = ruolo.strip().lower()
        if ruolo not in RUOLI_VALIDI:
            raise ValueError(f"Ruolo non valido: {ruolo}")
        update["ruolo"] = ruolo
    if attivo is not None:
        update["attivo"] = bool(attivo)
    if pin is not None:
        if not pin_valido(pin):
            raise ValueError("PIN non valido: solo cifre, da 4 a 12")
        admin_pin = os.getenv("ADMIN_PIN", "").strip()
        if admin_pin and hmac.compare_digest(pin, admin_pin):
            raise ValueError("Questo PIN è riservato all'amministratore")
        if await _pin_gia_usato(db, pin, escludi_id=utente_id):
            raise ValueError("PIN già assegnato a un altro utente")
        salt = uuid.uuid4().hex
        update["pin_salt"] = salt
        update["pin_hash"] = _hash_pin(pin, salt)
    if not update:
        return False
    update["updated_at"] = _now()
    res = await db[COLLECTION].update_one({"id": utente_id}, {"$set": update})
    return res.matched_count > 0


async def elimina_utente(db, utente_id: str) -> bool:
    res = await db[COLLECTION].delete_one({"id": utente_id})
    return res.deleted_count > 0


async def verifica_pin(db, pin: str) -> Optional[Dict[str, Any]]:
    """Se il PIN corrisponde a un utente attivo, ritorna il suo record pubblico
    (id, nome, ruolo). Altrimenti None."""
    if not pin_valido(pin):
        return None
    async for u in db[COLLECTION].find({"attivo": True}):
        if hmac.compare_digest(_hash_pin(pin, u.get("pin_salt", "")), u.get("pin_hash", "")):
            return {"id": u.get("id"), "nome": u.get("nome"), "ruolo": u.get("ruolo", "operatore")}
    return None
