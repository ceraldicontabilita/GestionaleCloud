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
    # La password per le app Google si legge a gruppi («abcd efgh ijkl mnop»):
    # incollata cosi' su Render gli spazi la fanno rifiutare. Non ne contiene.
    if password:
        password = "".join(str(password).split())
    if user:
        user = str(user).strip()
    return GmailEnvironmentCredentials(user=user, password=password, host=host)


_VARIABILI_UTENTE = (
    "IMAP_USER", "EMAIL_USER", "EMAIL_ADDRESS", "GMAIL_EMAIL",
    "GMAIL_ACCOUNT_AMMINISTRATIVO", "ADMIN_EMAIL",
)
# Prima le password per le app: e' l'unico tipo che Gmail accetta via IMAP.
_VARIABILI_PASSWORD = (
    "GMAIL_APP_PASSWORD", "EMAIL_APP_PASSWORD", "GMAIL_APP_PASSWORD_AMMINISTRATIVO",
    "IMAP_PASSWORD", "EMAIL_PASSWORD",
)
_coppia_riuscita: Optional[tuple] = None


def candidate_gmail_credentials(massimo: int = 8) -> list:
    """Tutte le coppie (indirizzo, password) configurate, senza doppioni.

    Una password per le app nuova messa in ``GMAIL_APP_PASSWORD`` restava
    inutile finche' ``IMAP_PASSWORD`` conteneva quella vecchia: la prima
    variabile vinceva sempre. Il login ora le prova tutte; quella che Gmail
    accetta passa in testa. Ogni voce e' (utente, password, var_utente,
    var_password): i nomi servono ai log, i valori non si scrivono mai.
    """
    utenti, visti = [], set()
    for nome in _VARIABILI_UTENTE:
        valore = str(getattr(settings, nome, None) or "").strip()
        if valore and valore.lower() not in visti:
            visti.add(valore.lower())
            utenti.append((valore, nome))
    password, viste = [], set()
    for nome in _VARIABILI_PASSWORD:
        valore = "".join(str(getattr(settings, nome, None) or "").split())
        if valore and valore not in viste:
            viste.add(valore)
            password.append((valore, nome))
    coppie = [(u, p, nu, np) for p, np in password for u, nu in utenti]
    if _coppia_riuscita:
        coppie.sort(key=lambda c: (c[2], c[3]) != _coppia_riuscita)
    return coppie[:massimo]


def ricorda_coppia_riuscita(var_utente: str, var_password: str) -> None:
    global _coppia_riuscita
    _coppia_riuscita = (var_utente, var_password)
