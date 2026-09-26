"""Risoluzione canonica delle credenziali Gmail definite nell'ambiente.

Il progetto ha accumulato nel tempo piu nomi equivalenti per utente e App
Password. Tutti i flussi Gmail devono usare la stessa precedenza, senza
duplicare o rinominare segreti su Render.
"""
from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass(frozen=True)
class GmailEnvironmentCredentials:
    user: Optional[str]
    password: Optional[str]
    host: str


def get_gmail_environment_credentials() -> GmailEnvironmentCredentials:
    """Restituisce le credenziali Gmail disponibili senza esporle nei log."""
    user = (
        settings.IMAP_USER
        or settings.EMAIL_USER
        or settings.EMAIL_ADDRESS
        or settings.GMAIL_EMAIL
        or settings.GMAIL_ACCOUNT_AMMINISTRATIVO
        or settings.ADMIN_EMAIL
    )
    password = (
        settings.IMAP_PASSWORD
        or settings.EMAIL_APP_PASSWORD
        or settings.EMAIL_PASSWORD
        or settings.GMAIL_APP_PASSWORD
        or settings.GMAIL_APP_PASSWORD_AMMINISTRATIVO
    )
    host = settings.IMAP_HOST or settings.IMAP_SERVER or "imap.gmail.com"
    return GmailEnvironmentCredentials(user=user, password=password, host=host)
