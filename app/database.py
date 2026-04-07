"""MongoDB connection manager with Motor."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)


class Database:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_db(cls) -> None:
        logger.info("Connecting to MongoDB Atlas...")
        cls.client = AsyncIOMotorClient(
            settings.MONGODB_ATLAS_URI,
            maxPoolSize=50,
            minPoolSize=10,
            serverSelectionTimeoutMS=5000
        )
        cls.db = cls.client[settings.DB_NAME]
        await cls.client.admin.command('ping')
        logger.info(f"Connected to MongoDB: {settings.DB_NAME}")
        await cls._create_indexes()

    @classmethod
    async def _create_indexes(cls) -> None:
        try:
            db = cls.db
            await db["dipendenti"].create_index("codice_fiscale", unique=True, sparse=True)
            await db["dipendenti"].create_index("stato")
            await db["fornitori"].create_index("partita_iva", unique=True, sparse=True)
            await db["fatture_passive"].create_index("dedup_key", unique=True, sparse=True)
            await db["fatture_passive"].create_index([("fornitore_piva", 1), ("data", -1)])
            await db["cedolini"].create_index([("codice_fiscale", 1), ("anno", -1), ("mese", -1)])
            await db["estratto_conto_movimenti"].create_index("chiave", unique=True, sparse=True)
            await db["corrispettivi"].create_index("chiave", unique=True, sparse=True)
            await db["f24"].create_index("chiave", unique=True, sparse=True)
            await db["cartelle_esattoriali"].create_index("numero_cartella", unique=True, sparse=True)
            logger.info("Database indexes created")
        except Exception as e:
            logger.warning(f"Index creation: {e}")

    @classmethod
    async def close_db(cls) -> None:
        if cls.client:
            cls.client.close()

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        if cls.db is None:
            raise RuntimeError("Database not connected")
        return cls.db


async def get_database() -> AsyncIOMotorDatabase:
    return Database.get_db()
