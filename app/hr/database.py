"""Connessione Supabase/Postgres del modulo HR.

L'API esposta ai chiamanti resta simile a quella documentale storica, ma il
solo archivio persistente ammesso e' l'adattatore :mod:`db_supabase`. In
assenza della DSN l'app fallisce chiusa al primo accesso ai dati: non apre un
database alternativo e non crea un archivio locale silenzioso.
"""
import os
import logging

logger = logging.getLogger(__name__)


def _env(*nomi: str, default: str = "") -> str:
    for nome in nomi:
        val = os.environ.get(nome)
        if val:
            return val
    return default


HR_USE_MAIN_DATABASE = _env("HR_USE_MAIN_DATABASE").lower() in {"1", "true", "yes", "on"}
SUPABASE_DB_URL = (
    _env("SUPABASE_DB_URL")
    if HR_USE_MAIN_DATABASE
    else _env("HR_SUPABASE_DB_URL", "APPDIPENDENTI_DB_URL", "SUPABASE_DB_URL")
)
SUPABASE_DB_SCHEMA = _env("HR_DB_SCHEMA", default="public")


class Collections:
    """Nomi canonici delle collection (un solo punto di verità)."""
    USERS = "users"
    EMPLOYEES = "dipendenti"
    PAYSLIPS = "cedolini"
    AUDIT_LOG = "audit_log"


class DatabaseNonConfigurato:
    """Segnaposto restituito da `get_db()` quando nessuna DSN e' configurata.

    Qualunque uso (db["coll"], db.coll, await db.command(...)) solleva un
    RuntimeError con il nome delle variabili da impostare: l'app ospite
    parte comunque e l'errore compare solo alla prima richiesta HR.
    """

    MESSAGGIO = (
        "Database del modulo HR non configurato: impostare HR_SUPABASE_DB_URL "
        "(DSN Postgres/Supabase asyncpg; fallback APPDIPENDENTI_DB_URL, SUPABASE_DB_URL)."
    )

    def __init__(self, motivo: str = ""):
        self._motivo = motivo

    def _errore(self) -> RuntimeError:
        msg = self.MESSAGGIO if not self._motivo else f"{self.MESSAGGIO} Dettaglio: {self._motivo}"
        return RuntimeError(msg)

    def __getitem__(self, nome):
        raise self._errore()

    def __getattr__(self, nome):
        if nome.startswith("_"):
            raise AttributeError(nome)
        raise self._errore()

    def __bool__(self) -> bool:
        return False


class Database:
    client = None
    db = None
    backend: str = ""

    @classmethod
    async def connect(cls):
        if SUPABASE_DB_URL:
            from .db_supabase import crea_database
            cls.db = await crea_database(SUPABASE_DB_URL, schema=SUPABASE_DB_SCHEMA)
            cls.client = cls.db._pool
            cls.backend = "supabase"
            logger.info("Database: Supabase/Postgres")
            return

        cls.db = DatabaseNonConfigurato()
        cls.client = None
        cls.backend = "non_configurato"
        logger.warning("Modulo HR senza database: %s", DatabaseNonConfigurato.MESSAGGIO)

    @classmethod
    async def close(cls):
        if cls.client is None:
            return
        await cls.client.close()
        cls.client = None

    @classmethod
    def get_db(cls):
        if cls.db is None:
            # Nessun connect() ancora eseguito (es. avvio della sotto-app non
            # riuscito): errore chiaro invece di AttributeError su None.
            return DatabaseNonConfigurato("Database.connect() non ancora eseguito")
        return cls.db


def get_database():
    """Accessor funzionale usato dalle dependency FastAPI (Depends)."""
    return Database.get_db()
