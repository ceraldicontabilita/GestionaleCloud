"""Accesso al database per il modulo HR.

Non esiste piu' una connessione separata: il modulo usa il runtime
documentale unico del gestionale (``app.database.Database``) attraverso
l'adattatore ``HRDatabase`` (prefisso ``hr_`` + scarico dei PDF nel
``BlobStore``). ``Database.get_db()`` e ``get_database()`` restano i due
accessori storici usati da tutti i router HR.
"""
import logging
from typing import Optional

from app.database import Database as _GestionaleDatabase
from app.services.blob_store import BlobStore, blob_store_per_runtime
from app.hr.db_adapter import HRDatabase

logger = logging.getLogger(__name__)


class Collections:
    """Nomi canonici delle collection HR (un solo punto di verita')."""
    USERS = "users"
    EMPLOYEES = "dipendenti"
    PAYSLIPS = "cedolini"
    AUDIT_LOG = "audit_log"


class Database:
    _db: Optional[HRDatabase] = None
    _runtime_id: Optional[int] = None

    @classmethod
    def get_db(cls) -> HRDatabase:
        runtime = _GestionaleDatabase.db
        if runtime is None:
            raise RuntimeError("Registro dati del gestionale non connesso")
        # Il runtime puo' essere sostituito (riconnessione, test): l'adattatore
        # segue sempre l'istanza corrente.
        if cls._db is None or cls._runtime_id != id(runtime):
            cls._db = HRDatabase(runtime, blob_store_per_runtime(runtime))
            cls._runtime_id = id(runtime)
        return cls._db

    @classmethod
    def blob_store(cls) -> BlobStore:
        return cls.get_db().blobs

    @classmethod
    def reset(cls) -> None:
        cls._db = None
        cls._runtime_id = None


def get_database() -> HRDatabase:
    """Accessor funzionale usato dalle dependency FastAPI (Depends)."""
    return Database.get_db()
