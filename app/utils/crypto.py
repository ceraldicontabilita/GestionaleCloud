"""Cifratura simmetrica per credenziali salvate (App Password Gmail, ecc.).

Usa Fernet (AES128-CBC + HMAC, libreria 'cryptography', già una dipendenza
del progetto). La chiave viene letta da CREDENTIALS_ENCRYPTION_KEY
nell'ambiente. In produzione e' obbligatoria: i registri Sheets non devono
mai contenere una chiave capace di decifrare le credenziali archiviate.
"""
import os
import logging
from functools import lru_cache

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

ENV_VAR = "CREDENTIALS_ENCRYPTION_KEY"


def _temporary_development_key() -> str:
    logger.critical(
        "%s non configurata: uso una chiave temporanea soltanto fuori dalla "
        "produzione. Configurare il secret su Render prima del deploy.",
        ENV_VAR,
    )
    return Fernet.generate_key().decode()


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get(ENV_VAR) or _temporary_development_key()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credential(plaintext: str) -> str:
    """Cifra una credenziale (es. App Password). Ritorna un token Fernet (stringa)."""
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(value: str) -> str:
    """Decifra una credenziale salvata con encrypt_credential().

    Se il valore non è un token Fernet valido (credenziali salvate in chiaro
    prima di questa modifica), lo restituisce così com'è: permette una
    migrazione trasparente, senza uno script a parte — al primo salvataggio
    successivo dalla UI il valore verrà cifrato."""
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except Exception:
        return value
