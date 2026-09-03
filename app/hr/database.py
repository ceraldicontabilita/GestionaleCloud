"""Database connection per AppDipendenti.

Due backend possibili, scelti dalle env:
  - HR_SUPABASE_DB_URL (fallback APPDIPENDENTI_DB_URL, poi SUPABASE_DB_URL)
    impostata -> Postgres/Supabase via l'adattatore db_supabase
  - altrimenti HR_MONGO_URL (fallback MONGO_URL) -> MongoDB (motor), il backend storico

Dentro GestionaleCloud i nomi sono prefissati `HR_` per non collidere con le
variabili omonime dell'app ospite; i nomi originali restano come fallback.

L'oggetto restituito da `get_db()` espone la stessa API nei due casi, per cui i
269 punti che chiamano `Database.get_db()` non cambiano.

Se nessuna DSN e' configurata (o manca `motor` per il ramo Mongo) l'app parte
lo stesso: il primo accesso al database solleva un RuntimeError esplicito,
invece di un errore all'import.
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


MONGO_URL = _env("HR_MONGO_URL", "MONGO_URL")
DB_NAME = _env("HR_DB_NAME", "DB_NAME", default="Gestionale")
SUPABASE_DB_URL = _env("HR_SUPABASE_DB_URL", "APPDIPENDENTI_DB_URL", "SUPABASE_DB_URL")


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
        "(DSN Postgres/Supabase asyncpg; fallback APPDIPENDENTI_DB_URL, SUPABASE_DB_URL) "
        "oppure HR_MONGO_URL (fallback MONGO_URL, richiede `motor`)."
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
            cls.db = await crea_database(SUPABASE_DB_URL)
            cls.client = cls.db._pool
            cls.backend = "supabase"
            logger.info("Database: Supabase/Postgres")
            return

        if not MONGO_URL:
            cls.db = DatabaseNonConfigurato()
            cls.client = None
            cls.backend = "non_configurato"
            logger.warning("Modulo HR senza database: %s", DatabaseNonConfigurato.MESSAGGIO)
            return

        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as e:
            cls.db = DatabaseNonConfigurato(f"`motor` non installato ({e})")
            cls.client = None
            cls.backend = "non_configurato"
            logger.warning("Modulo HR: HR_MONGO_URL impostata ma `motor` non e' installato")
            return
        cls.client = AsyncIOMotorClient(MONGO_URL)
        cls.db = cls.client[DB_NAME]
        cls.backend = "mongo"
        logger.info(f"MongoDB connesso: {DB_NAME}")

    @classmethod
    async def close(cls):
        if cls.client is None:
            return
        if cls.backend == "supabase":
            await cls.client.close()
        else:
            cls.client.close()
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
