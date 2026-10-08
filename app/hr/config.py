"""Configurazione AppDipendenti — punto unico (oggetto `settings` + costanti)."""
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


def _env(*nomi: str, default: str = "") -> str:
    """Prima variabile d'ambiente impostata tra quelle elencate, altrimenti `default`.

    Dentro GestionaleCloud le variabili dell'app originale sono prefissate `HR_`
    (per non collidere con quelle omonime dell'app ospite); i nomi originali
    compatibili restano come fallback, escluso il PIN admin.
    """
    for nome in nomi:
        val = os.environ.get(nome)
        if val:
            return val
    return default


def _shared_auth_secret() -> str:
    """Segreto JWT UNIFICATO per tutte le app Ceraldi.

    La fonte e' esclusivamente il secret store del runtime. Nessun import di
    configurazione apre connessioni a database e nessun segreto viene scritto
    in una collezione applicativa.
    """
    import secrets as _s
    configurato = _env("HR_JWT_SECRET", "JWT_SECRET")
    if not configurato:
        logger.warning(
            "⚠️ HR_JWT_SECRET/JWT_SECRET non configurata: uso un secret JWT "
            "casuale effimero di processo (invalida i token a ogni riavvio). "
            "Configurare HR_JWT_SECRET nel secret store di Render."
        )
    return configurato or _s.token_urlsafe(64)


class Settings:
    """Config centrale. I valori sensibili arrivano dalle env di Render."""
    # JWT — segreto condiviso tra le app Ceraldi (vedi _shared_auth_secret)
    SECRET_KEY: str = _shared_auth_secret()
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 giorni

    # Utente admin a cui il PIN concede accesso (deve esistere in `users`).
    PIN_ADMIN_USERNAME: str = _env("HR_PIN_ADMIN_USERNAME", "PIN_ADMIN_USERNAME", default="ceraldi")


settings = Settings()

# Retro-compatibilità con chi importa le costanti a modulo.
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Feature flag (usati da require_feature). Vuoto = nessuna feature gated attiva.
FEATURES: dict = {}

# Origini consentite (CORS). NIENTE wildcard "*": con endpoint pubblici + credenziali
# permetterebbe a qualunque sito di leggere i dati dal browser di un visitatore.
# Il frontend dell'app è servito dallo stesso dominio (same-origin, non serve CORS).
CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://ceraldicontabilita.github.io",
]
