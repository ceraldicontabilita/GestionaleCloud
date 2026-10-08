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


def admin_pin_is_configured() -> bool:
    from app.services.admin_pin import configured
    return configured()


def admin_pin_matches(pin: str) -> bool:
    """Unica verifica booleana del PIN amministratore centrale."""
    pin = (pin or "").strip()
    return verify_admin_pin(pin) is True


@dataclass(frozen=True)
class PinIdentity:
    id: str
    email: str
    name: str | None
    role: str
    source: str
    user_repo: Any | None = None

    def as_user(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
        }


async def authenticate_admin_pin(
    db,
    pin: str,
    *,
    users_collection: str = Collections.USERS,
    username: str = PIN_ADMIN_USERNAME,
    repository_factory=UserRepository,
    require_existing: bool = False,
    require_active: bool = False,
    allow_synthetic: bool = True,
    synthetic_email: str = PIN_ADMIN_EMAIL_DEFAULT,
) -> PinIdentity | None:
    """Valida il PIN centrale e risolve l'identita' admin del dominio.

    La credenziale e' unica; il dominio decide soltanto dove vive la propria
    identita' amministrativa e se una identita' persistita e' obbligatoria.
    """
    if not admin_pin_matches(pin):
        return None
    return await risolvi_identita_admin(
        db,
        users_collection=users_collection,
        username=username,
        repository_factory=repository_factory,
        require_existing=require_existing,
        require_active=require_active,
        allow_synthetic=allow_synthetic,
        synthetic_email=synthetic_email,
    )


async def risolvi_identita_admin(
    db,
    *,
    users_collection: str = Collections.USERS,
    username: str = PIN_ADMIN_USERNAME,
    repository_factory=UserRepository,
    require_existing: bool = False,
    require_active: bool = False,
    allow_synthetic: bool = True,
    synthetic_email: str = PIN_ADMIN_EMAIL_DEFAULT,
) -> PinIdentity | None:
    """L'identita' amministrativa del dominio, senza verificare credenziali:
    chi chiama ha gia' una prova (il PIN, oppure la sessione del Gestionale)."""
    user_repo = None
    user = None
    try:
        if repository_factory is not None:
            user_repo = repository_factory(db[users_collection])
            try:
                candidate = await user_repo.find_by_username(username)
            except Exception:
                candidate = None
            if candidate and candidate.get("role") == "admin":
                user = candidate

        if not user:
            user = await db[users_collection].find_one({"role": "admin"})
    except Exception:
        logger.exception("PIN auth: lookup identita admin fallito")
        user_repo = None
        user = None

    if user and require_active and user.get("is_active") is False:
        user = None

    if user:
        return PinIdentity(
            id=str(user.get("id") or user.get("_id")),
            email=user.get("email", ""),
            name=user.get("name"),
            role="admin",
            source="admin_pin",
            user_repo=user_repo,
        )

    if require_existing or not allow_synthetic:
        return None

    return PinIdentity(
        id="admin",
        email=synthetic_email,
        name="Amministratore",
        role="admin",
        source="admin_pin",
        user_repo=None,
    )


async def authenticate_pin(db, pin: str) -> PinIdentity | None:
    """Ritorna identita canonica associata al PIN, oppure None."""
    admin_match = admin_pin_matches(pin)
    if admin_match:
        return await authenticate_admin_pin(db, pin)

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
    if admin_pin_is_configured():
        return True
    try:
        return await db[utenti_pin.COLLECTION].count_documents({"attivo": True}) > 0
    except Exception:
        return False
