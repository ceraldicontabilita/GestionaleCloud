"""Configurazione AppDipendenti — punto unico (oggetto `settings` + costanti)."""
import os
from typing import List


def _env(*nomi: str, default: str = "") -> str:
    """Prima variabile d'ambiente impostata tra quelle elencate, altrimenti `default`.

    Dentro GestionaleCloud le variabili dell'app originale sono prefissate `HR_`
    (per non collidere con quelle omonime dell'app ospite: SECRET_KEY, MONGO_URL,
    DB_NAME, PIN_CODE...); i nomi originali restano come fallback.
    """
    for nome in nomi:
        val = os.environ.get(nome)
        if val:
            return val
    return default


def _shared_auth_secret() -> str:
    """Segreto JWT UNIFICATO per tutte le app Ceraldi.

    Fonte unica: collezione `sistema_stato` (chiave `auth_secret`) sul DB condiviso
    `Gestionale` — lo stesso meccanismo usato da Lotti. Così le tre app firmano e
    validano i token con la STESSA chiave, senza sincronizzare variabili a mano, e
    quando verranno fuse l'autenticazione è già coerente.
    Fallback: env JWT_SECRET, poi una chiave di processo.
    """
    try:
        from pymongo import MongoClient
        uri = _env("HR_MONGO_URL", "MONGO_URL")
        if uri:
            cli = MongoClient(uri, serverSelectionTimeoutMS=4000)
            coll = cli[_env("HR_DB_NAME", "DB_NAME", default="Gestionale")]["sistema_stato"]
            doc = coll.find_one({"chiave": "auth_secret"})
            if doc and doc.get("valore"):
                cli.close()
                return doc["valore"]
            import secrets as _s
            val = _env("HR_JWT_SECRET", "JWT_SECRET") or _s.token_hex(32)
            coll.update_one({"chiave": "auth_secret"}, {"$set": {"valore": val}}, upsert=True)
            cli.close()
            return val
    except Exception:
        pass
    # Ultima spiaggia: env JWT_SECRET, altrimenti un segreto casuale di processo
    # (mai un literal prevedibile come "changeme": permetterebbe di forgiare token).
    import secrets as _s
    return _env("HR_JWT_SECRET", "JWT_SECRET") or _s.token_hex(32)


class Settings:
    """Config centrale. I valori sensibili arrivano dalle env di Render."""
    # JWT — segreto condiviso tra le app Ceraldi (vedi _shared_auth_secret)
    SECRET_KEY: str = _shared_auth_secret()
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 giorni

    # PIN unico (fisso) per il login mobile. Valore SOLO nelle env
    # (HR_PIN_CODE dentro GestionaleCloud, PIN_CODE come fallback).
    PIN_CODE: str = _env("HR_PIN_CODE", "PIN_CODE")

    # Utente admin a cui il PIN concede accesso (deve esistere in `users`).
    PIN_ADMIN_USERNAME: str = _env("HR_PIN_ADMIN_USERNAME", "PIN_ADMIN_USERNAME", default="ceraldi")


settings = Settings()

# Retro-compatibilità con chi importa le costanti a modulo.
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
PIN_CODE = settings.PIN_CODE

# Feature flag (usati da require_feature). Vuoto = nessuna feature gated attiva.
FEATURES: dict = {}

# Origini consentite (CORS). NIENTE wildcard "*": con endpoint pubblici + credenziali
# permetterebbe a qualunque sito di leggere i dati dal browser di un visitatore.
# Il frontend dell'app è servito dallo stesso dominio (same-origin, non serve CORS).
CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://ceraldicontabilita.github.io",
    "https://gestionale-ceraldi.onrender.com",
    "https://appdipendenti.onrender.com",
]
