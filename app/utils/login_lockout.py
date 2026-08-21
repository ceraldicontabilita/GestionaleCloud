"""
Anti brute-force condiviso per il login (email/password e PIN).

Blocco per IP dopo N tentativi falliti entro una finestra temporale.
Sostituisce il lockout duplicato che viveva solo in pin_login.py, così
email-login e pin-login condividono la stessa politica (scelta utente
13/07/2026: 5 tentativi, poi 5 minuti di attesa).

In-memory per processo: adeguato al deployment mono/pochi-worker attuale.
Se in futuro si passa a molti worker, spostare lo stato su Drive/Sheets
mantenendo questa stessa interfaccia.
"""
import time
import logging
from typing import Dict, Any

from fastapi import Request

logger = logging.getLogger(__name__)

# Politica (scelta utente): 5 tentativi, poi lock di 5 minuti.
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300
# I fallimenti "invecchiano": un tentativo più vecchio della finestra non conta.
WINDOW_SECONDS = 300

_FAILED: Dict[str, Dict[str, Any]] = {}


def client_ip(request: Request) -> str:
    """IP del client, con supporto X-Forwarded-For dietro reverse proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def seconds_locked(ip: str) -> int:
    """Secondi residui di blocco per l'IP, 0 se non bloccato."""
    rec = _FAILED.get(ip)
    if not rec:
        return 0
    locked_until = rec.get("locked_until", 0)
    if locked_until > time.time():
        return int(locked_until - time.time())
    return 0


def register_failure(ip: str) -> None:
    """Registra un tentativo fallito; blocca l'IP al raggiungimento della soglia."""
    now = time.time()
    rec = _FAILED.get(ip)
    # Reset del contatore se l'ultimo tentativo è fuori finestra.
    if not rec or (now - rec.get("last", 0)) > WINDOW_SECONDS:
        rec = {"count": 0, "locked_until": 0}
    rec["count"] += 1
    rec["last"] = now
    if rec["count"] >= MAX_ATTEMPTS:
        rec["locked_until"] = now + LOCK_SECONDS
        rec["count"] = 0
        logger.warning(f"Login: IP {ip} bloccato per {LOCK_SECONDS}s (troppi tentativi)")
    _FAILED[ip] = rec


def clear_failures(ip: str) -> None:
    """Azzera i fallimenti per l'IP (dopo un login riuscito)."""
    _FAILED.pop(ip, None)
