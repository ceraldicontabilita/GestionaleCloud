"""
Database configuration and connection management.
Provides singleton Motor AsyncIOMotorClient for MongoDB Atlas.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)


class Database:
    """MongoDB connection manager with singleton pattern."""
    
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_db(cls) -> None:
        """
        Create database connection.
        Called on application startup.
        """
        try:
            logger.info("Connecting to MongoDB Atlas...")
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_ATLAS_URI,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS
            )
            cls.db = cls.client[settings.DB_NAME]
            
            # Test connection
            await cls.client.admin.command('ping')
            logger.info(f"✅ Connected to MongoDB database: {settings.DB_NAME}")
            
            # Create indexes for unique constraints
            await cls._create_indexes()
            
        except Exception as e:
            logger.error(f"❌ Error connecting to MongoDB: {e}")
            raise

    @classmethod
    async def _create_indexes(cls) -> None:
        """Create database indexes for unique constraints and performance."""
        try:
            db = cls.db
            
            # --- Invoices ---
            await db[Collections.INVOICES].create_index(
                "invoice_key", unique=True, sparse=True,
                name="idx_invoice_key_unique"
            )
            await db[Collections.INVOICES].create_index(
                [("fornitore_piva", 1), ("invoice_date", -1)],
                name="idx_invoices_fornitore_data"
            )
            await db[Collections.INVOICES].create_index(
                "stato", name="idx_invoices_stato"
            )
            
            # --- Employees ---
            await db[Collections.EMPLOYEES].create_index(
                "codice_fiscale", unique=True, sparse=True,
                name="idx_employees_cf_unique"
            )
            await db[Collections.EMPLOYEES].create_index(
                "attivo", name="idx_employees_attivo"
            )
            
            # --- Prima Nota Cassa ---
            await db[Collections.CASH_MOVEMENTS].create_index(
                [("data", -1)], name="idx_pn_cassa_data"
            )
            await db[Collections.CASH_MOVEMENTS].create_index(
                [("anno", 1), ("tipo", 1)], name="idx_pn_cassa_anno_tipo"
            )
            
            # --- Prima Nota Banca ---
            await db["prima_nota_banca"].create_index(
                [("data", -1)], name="idx_pn_banca_data"
            )
            await db["prima_nota_banca"].create_index(
                [("anno", 1), ("tipo", 1)], name="idx_pn_banca_anno_tipo"
            )
            
            # --- Estratto Conto ---
            await db[Collections.BANK_STATEMENTS].create_index(
                [("data", -1)], name="idx_ec_data"
            )
            await db[Collections.BANK_STATEMENTS].create_index(
                [("importo", 1)], name="idx_ec_importo"
            )
            
            # --- F24 ---
            await db[Collections.F24_MODELS].create_index(
                [("periodo", 1), ("stato", 1)], name="idx_f24_periodo_stato"
            )
            
            # --- Cedolini ---
            await db[Collections.PAYSLIPS].create_index(
                [("employee_id", 1), ("anno", 1), ("mese", 1)],
                name="idx_cedolini_emp_anno_mese"
            )
            
            # --- Fornitori ---
            await db[Collections.SUPPLIERS].create_index(
                "partita_iva", unique=True, sparse=True,
                name="idx_fornitori_piva_unique"
            )
            
            # --- Indici aggiuntivi per performance ---
            
            # Anno (usato in TUTTE le query filtrate per anno fiscale)
            await db[Collections.INVOICES].create_index("anno", name="idx_invoices_anno")
            await db[Collections.CASH_MOVEMENTS].create_index("anno", name="idx_pn_cassa_anno")
            await db["prima_nota_banca"].create_index("anno", name="idx_pn_banca_anno")
            
            # created_at / updated_at (ordinamento temporale)
            await db[Collections.INVOICES].create_index(
                [("created_at", -1)], name="idx_invoices_created_at"
            )
            await db[Collections.BANK_STATEMENTS].create_index(
                [("created_at", -1)], name="idx_ec_created_at"
            )
            
            # Riconciliazione: stato + data
            await db[Collections.BANK_STATEMENTS].create_index(
                [("stato_riconciliazione", 1), ("data", -1)],
                name="idx_ec_riconciliazione_data"
            )
            
            # Documenti email: data + tipo
            await db["documenti_classificati"].create_index(
                [("tipo_documento", 1), ("data_documento", -1)],
                name="idx_docs_tipo_data"
            )
            
            # Warehouse: product search
            await db[Collections.WAREHOUSE_PRODUCTS].create_index(
                [("nome", 1)], name="idx_warehouse_nome"
            )
            
            # Scadenzario fornitori
            await db["scadenziario_fornitori"].create_index(
                [("data_scadenza", 1), ("stato", 1)],
                name="idx_scadenzario_data_stato"
            )
            
            # Corrispettivi
            await db[Collections.CORRISPETTIVI].create_index(
                [("data", -1)], name="idx_corrispettivi_data"
            )
            
            # F24 per anno
            await db[Collections.F24_MODELS].create_index(
                "anno", name="idx_f24_anno"
            )
            
            # Users - sparse index allows multiple documents with null email
            # Email is optional but must be unique when present
            await db[Collections.USERS].create_index(
                "email", unique=True, sparse=True, name="idx_users_email_unique"
            )
            
            # Text index for search on invoices
            await db[Collections.INVOICES].create_index(
                [("fornitore_denominazione", "text"), ("numero_documento", "text")],
                name="idx_invoices_text_search"
            )
            
            logger.info("✅ Database indexes created (invoices, employees, prima_nota, f24, cedolini, fornitori, performance indexes)")
        except Exception as e:
            logger.warning(f"Index creation warning (may already exist): {e}")

    @classmethod
    async def close_db(cls) -> None:
        """
        Close database connection.
        Called on application shutdown.
        """
        if cls.client:
            logger.info("Closing MongoDB connection...")
            cls.client.close()
            logger.info("✅ MongoDB connection closed")

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """
        Get database instance.
        
        Returns:
            AsyncIOMotorDatabase: MongoDB database instance
            
        Raises:
            RuntimeError: If database is not connected
        """
        if cls.db is None:
            raise RuntimeError("Database not initialized. Call connect_db() first.")
        return cls.db

    @classmethod
    def get_collection(cls, collection_name: str):
        """
        Get a collection from the database.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            AsyncIOMotorCollection: MongoDB collection instance
        """
        db = cls.get_db()
        return db[collection_name]


# Convenience function for dependency injection
async def get_database() -> AsyncIOMotorDatabase:
    """
    FastAPI dependency to get database instance.
    
    Usage:
        @router.get("/endpoint")
        async def endpoint(db: AsyncIOMotorDatabase = Depends(get_database)):
            ...
    """
    return Database.get_db()


# Collection name constants - IMPORTARE DA db_collections.py per nuovi sviluppi
# Questa classe è mantenuta per retrocompatibilità
class Collections:
    """MongoDB collection names - LEGACY. Usare db_collections.py per nuovi sviluppi."""
    # Core
    USERS = "users"
    
    # Invoices
    INVOICES = "invoices"
    INVOICE_METADATA_TEMPLATES = "invoice_metadata_templates"
    
    # Suppliers - usa "fornitori" che è la collezione con i dati
    SUPPLIERS = "fornitori"
    
    # Warehouse
    WAREHOUSE_PRODUCTS = "warehouse_inventory"
    WAREHOUSE_MOVEMENTS = "warehouse_movements"
    RIMANENZE = "rimanenze"
    
    # Corrispettivi
    CORRISPETTIVI = "corrispettivi"
    
    # Employees
    EMPLOYEES = "employees"
    PAYSLIPS = "cedolini"  # Cambiato a collezione principale
    
    LIBRETTI_SANITARI = "libretti_sanitari"
    
    # Cash & Bank
    CASH_MOVEMENTS = "prima_nota_cassa"
    BANK_STATEMENTS = "estratto_conto_movimenti"  # Collezione principale
    
    # Accounting
    CHART_OF_ACCOUNTS = "piano_conti"  # Collezione italiana
    ACCOUNTING_ENTRIES = "accounting_entries"
    VAT_LIQUIDATIONS = "vat_liquidations"
    VAT_REGISTRY = "vat_registry"
    F24_MODELS = "f24_unificato"  # Collezione unificata
    BALANCE_SHEETS = "balance_sheets"
    YEAR_END_CLOSURES = "chiusure_esercizio"
    
    # Settings
    WAREHOUSE_SETTINGS = "warehouse_settings"
    SYSTEM_SETTINGS = "system_settings"
    
    # HACCP
    HACCP_TEMPERATURES = "haccp_temperatures"
