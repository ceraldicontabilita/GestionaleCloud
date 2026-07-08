"""Cifratura simmetrica per credenziali salvate (App Password Gmail, ecc.).

Prima venivano salvate in chiaro su MongoDB (es. gmail_app_password in
'settings', app_password in 'email_accounts'): chiunque avesse accesso in
lettura al database poteva leggerle direttamente.

Usa Fernet (AES128-CBC + HMAC, libreria 'cryptography', già una dipendenza
del progetto). La chiave viene letta da CREDENTIALS_ENCRYPTION_KEY
nell'ambiente; se assente, viene generata una volta e persistita nella
collection 'sistema_stato' (stesso pattern già usato per SECRET_KEY in
app/config.py), così resta stabile tra i riavvii senza richiedere una
variabile d'ambiente obbligatoria in ogni deploy.
"""
import os
import logging
from functools import lru_cache

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

ENV_VAR = "CREDENTIALS_ENCRYPTION_KEY"


def _get_or_create_persisted_key() -> str:
    import pymongo
    from app.config import settings

    uri = settings.MONGO_URL or settings.MONGODB_ATLAS_URI or os.environ.get("MONGO_URL")
    if not uri:
        logger.critical(
            "CRITICAL: %s non configurata e nessuna connessione Mongo disponibile "
            "per persistere una chiave generata: uso una chiave temporanea di "
            "processo (le credenziali cifrate non saranno leggibili dopo il riavvio).",
            ENV_VAR,
        )
        return Fernet.generate_key().decode()

    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=4000)
    try:
        coll = client[settings.DB_NAME]["sistema_stato"]
        doc = coll.find_one({"chiave": "credentials_encryption_key"})
        if doc and doc.get("valore"):
            return doc["valore"]

        nuova_chiave = Fernet.generate_key().decode()
        coll.update_one(
            {"chiave": "credentials_encryption_key"},
            {"$set": {"chiave": "credentials_encryption_key", "valore": nuova_chiave}},
            upsert=True,
        )
        logger.critical(
            "CRITICAL: %s non configurata. Generata e salvata una chiave di "
            "cifratura in sistema_stato. Per maggiore sicurezza, impostare "
            "%s nell'ambiente di produzione (Render) con questo valore.",
            ENV_VAR, ENV_VAR,
        )
        return nuova_chiave
    finally:
        client.close()


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get(ENV_VAR) or _get_or_create_persisted_key()
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
