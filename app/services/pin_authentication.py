"""Autenticazione PIN canonica del GestionaleCloud.

Questo servizio decide identita' e ruolo a partire da un PIN. I router HTTP
non devono conoscere sorgenti credenziali, collezioni utenti o fallback legacy.

Ordine canonico:
1. PIN amministratore centrale da app.services.admin_pin;
2. PIN utenti gestiti dal Gestionale (operatore/sola_lettura/admin aggiuntivi).

Nessun fallback ad ADMIN_PIN in chiaro o PIN locali di HR/Lotti/Menu.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from app.database import Collections
from app.repositories import UserRepository
from app.services.admin_pin import verify_admin_pin
from app.services import utenti_pin

logger = logging.getLogger(__name__)

PIN_ADMIN_USERNAME = "ceraldi"
PIN_ADMIN_EMAIL_DEFAULT = os.getenv("ADMIN_EMAIL", "ceraldigroupsrl@gmail.com")


@dataclass(frozen=True)
class PinIdentity:
    id: str
    email: str
    name: str | None
    role: str
    source: str
    user_repo: UserRepository | None = None

    def as_user(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
        }


async def _admin_identity(db) -> PinIdentity:
    user_repo: UserRepository | None = None
    user = None
    try:
        user_repo = UserRepository(db[Collections.USERS])
        try:
            user = await user_repo.find_by_username(PIN_ADMIN_USERNAME)
        except Exception:
            user = None
        if not user:
            user = await db[Collections.USERS].find_one({"role": "admin"})
    except Exception:
        logger.exception("PIN auth: lookup identita admin fallito, uso identita sintetica")
        user_repo = None

    if not user:
        return PinIdentity(
            id="admin",
            email=PIN_ADMIN_EMAIL_DEFAULT,
            name="Amministratore",
            role="admin",
            source="admin_pin",
            user_repo=None,
        )

    return PinIdentity(
        id=str(user.get("id") or user.get("_id")),
        email=user.get("email", ""),
        name=user.get("name"),
        role="admin",
        source="admin_pin",
        user_repo=user_repo,
    )


async def authenticate_pin(db, pin: str) -> PinIdentity | None:
    """Ritorna identita canonica associata al PIN, oppure None."""
    admin_match = verify_admin_pin(pin)
    if admin_match is True:
        return await _admin_identity(db)

    match = await utenti_pin.verifica_pin(db, pin)
    if not match:
        return None

    return PinIdentity(
        id=str(match["id"]),
        email="",
        name=match.get("nome"),
        role=match.get("ruolo", "operatore"),
        source="utente_pin",
        user_repo=None,
    )


async def has_any_pin_identity(db) -> bool:
    """True se esiste almeno una sorgente PIN utilizzabile."""
    from app.services.admin_pin import configured

    if configured():
        return True
    try:
        return await db[utenti_pin.COLLECTION].count_documents({"attivo": True}) > 0
    except Exception:
        return False
