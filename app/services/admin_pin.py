"""Unica verifica del PIN amministratore per ERP e sotto-applicazioni.

Il riferimento è PIN_HASH_ADMIN di Render. Nessun fallback a PIN di reparto,
hash degli operatori o credenziali storiche: assenza/configurazione invalida
disabilita l'accesso amministratore senza cambiare i dati degli utenti.
"""
import hashlib
import hmac
import os
import re
from typing import Optional


def configured() -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", os.getenv("PIN_HASH_ADMIN", "").strip().lower()))


def verify_admin_pin(pin: str) -> Optional[bool]:
    expected = os.getenv("PIN_HASH_ADMIN", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return None
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{4,12}", pin):
        return False
    return hmac.compare_digest(hashlib.sha256(pin.encode("utf-8")).hexdigest(), expected)
