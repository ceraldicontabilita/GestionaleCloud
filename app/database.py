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
        db = cls.db
        created = 0
        skipped = 0
        
        async def _safe_index(collection_name, keys, **kwargs):
            nonlocal created, skipped
            try:
                await db[collection_name].create_index(keys, **kwargs)
                created += 1
            except Exception:
                skipped += 1
        
        # --- Invoices ---
        await _safe_index(Collections.INVOICES, "invoice_key", unique=True, sparse=True, name="idx_invoice_key_unique")
        await _safe_index(Collections.INVOICES, [("fornitore_piva", 1), ("invoice_date", -1)], name="idx_invoices_fornitore_data")
        await _safe_index(Collections.INVOICES, "stato", name="idx_invoices_stato")
        
        # --- Employees ---
        await _safe_index(Collections.EMPLOYEES, "codice_fiscale", unique=True, sparse=True, name="idx_employees_cf_unique")
        await _safe_index(Collections.EMPLOYEES, "attivo", name="idx_employees_attivo")
        
        # --- Prima Nota ---
        await _safe_index(Collections.CASH_MOVEMENTS, [("data", -1)], name="idx_pn_cassa_data")
        await _safe_index(Collections.CASH_MOVEMENTS, [("anno", 1), ("tipo", 1)], name="idx_pn_cassa_anno_tipo")
        await _safe_index("prima_nota_banca", [("data", -1)], name="idx_pn_banca_data")
        await _safe_index("prima_nota_banca", [("anno", 1), ("tipo", 1)], name="idx_pn_banca_anno_tipo")
        
        # --- Estratto Conto ---
        await _safe_index(Collections.BANK_STATEMENTS, [("data", -1)], name="idx_ec_data")
        await _safe_index(Collections.BANK_STATEMENTS, [("importo", 1)], name="idx_ec_importo")
        
        # --- F24 ---
        await _safe_index(Collections.F24_MODELS, [("periodo", 1), ("stato", 1)], name="idx_f24_periodo_stato")
        
        # --- Cedolini ---
        await _safe_index(Collections.PAYSLIPS, [("employee_id", 1), ("anno", 1), ("mese", 1)], name="idx_cedolini_emp_anno_mese")
        
        # --- Fornitori ---
        await _safe_index(Collections.SUPPLIERS, "partita_iva", unique=True, sparse=True, name="idx_fornitori_piva_unique")
        
        # --- Anno indexes ---
        await _safe_index(Collections.INVOICES, "anno", name="idx_invoices_anno")
        await _safe_index(Collections.CASH_MOVEMENTS, "anno", name="idx_pn_cassa_anno")
        await _safe_index("prima_nota_banca", "anno", name="idx_pn_banca_anno")
        
        # --- Timestamps ---
        await _safe_index(Collections.INVOICES, [("created_at", -1)], name="idx_invoices_created_at")
        await _safe_index(Collections.BANK_STATEMENTS, [("created_at", -1)], name="idx_ec_created_at")
        
        # --- Riconciliazione ---
        await _safe_index(Collections.BANK_STATEMENTS, [("stato_riconciliazione", 1), ("data", -1)], name="idx_ec_riconciliazione_data")
        
        # --- Corrispettivi ---
        await _safe_index(Collections.CORRISPETTIVI, [("data", -1)], name="idx_corrispettivi_data")
        await _safe_index(Collections.F24_MODELS, "anno", name="idx_f24_anno")
        
        # --- Warehouse ---
        await _safe_index(Collections.WAREHOUSE_PRODUCTS, [("nome", 1)], name="idx_warehouse_nome")
        
        logger.info(f"✅ Database indexes: {created} creati, {skipped} già esistenti")

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
    
    # Suppliers - usa "fornitori" come collection canonica (deduplicata)
    SUPPLIERS = "fornitori"
    
    # Warehouse
    WAREHOUSE_PRODUCTS = "warehouse_inventory"
    WAREHOUSE_MOVEMENTS = "warehouse_movements"
    RIMANENZE = "rimanenze"
    
    # Corrispettivi
    CORRISPETTIVI = "corrispettivi"
    
    # Employees
    EMPLOYEES = "dipendenti"
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
