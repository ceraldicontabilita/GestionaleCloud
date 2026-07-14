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
        
        # --- PayPal ---
        await _safe_index("paypal_transactions", "transaction_id", unique=True, name="idx_paypal_txn_id")
        await _safe_index("paypal_transactions", "paypal_account_id", name="idx_paypal_account")
        await _safe_index("paypal_transactions", "is_pagopa", name="idx_paypal_pagopa")
        await _safe_index("paypal_transactions", [("initiation_date", -1)], name="idx_paypal_date")

        # --- Partite Aperte (Chat 8) ---
        await _safe_index("partite_aperte", "id", unique=True, name="idx_pa_id")

        # --- Dipendenti (query per CF, attivo, data_assunzione) ---
        await _safe_index("dipendenti", "codice_fiscale", unique=True, sparse=True, name="idx_dipendenti_cf")
        await _safe_index("dipendenti", "attivo", name="idx_dipendenti_attivo")
        await _safe_index("dipendenti", [("cognome", 1), ("nome", 1)], name="idx_dipendenti_nome")

        # --- Assegni (query per stato, fornitore, data) ---
        await _safe_index("assegni", "stato", name="idx_assegni_stato")
        await _safe_index("assegni", "pagato", name="idx_assegni_pagato")
        await _safe_index("assegni", [("fornitore_piva", 1), ("data_emissione", -1)], name="idx_assegni_fornitore_data")
        await _safe_index("assegni", "fattura_id", sparse=True, name="idx_assegni_fattura")

        # --- Alerts (query per stato, tipo, data) ---
        await _safe_index("alerts", [("stato", 1), ("created_at", -1)], name="idx_alerts_stato_data")
        await _safe_index("alerts", "tipo", name="idx_alerts_tipo")
        await _safe_index("alerts", "entity_id", sparse=True, name="idx_alerts_entity")

        # --- Pagamenti (query per fattura, stato, data) ---
        await _safe_index("pagamenti", "fattura_id", sparse=True, name="idx_pagamenti_fattura")
        await _safe_index("pagamenti", [("data", -1)], name="idx_pagamenti_data")
        await _safe_index("pagamenti", "stato", name="idx_pagamenti_stato")
        # Idempotenza pagamenti (P0.9): stesso submit -> stesso documento, no doppioni
        await _safe_index("pagamenti", "idempotency_key", unique=True, sparse=True,
                          name="idx_pagamenti_idempotency")

        # --- F24 (consolidamento P1 §5.1): chiave di deduplica naturale ---
        await _safe_index("f24_unificato", "f24_dedup_key", sparse=True,
                          name="idx_f24_dedup_key")

        # --- Verbali Noleggio ---
        await _safe_index("verbali_noleggio", [("data_verbale", -1)], name="idx_verbali_data")
        await _safe_index("verbali_noleggio", "veicolo_targa", sparse=True, name="idx_verbali_targa")
        await _safe_index("verbali_noleggio", "dipendente_id", sparse=True, name="idx_verbali_dipendente")

        # --- Presenze / Attendance ---
        await _safe_index("presenze", [("employee_id", 1), ("data", -1)], name="idx_presenze_emp_data")
        await _safe_index("presenze_giornaliere", [("employee_id", 1), ("anno", 1), ("mese", 1)], name="idx_presenze_g_emp")
        await _safe_index("attendance_assenze", [("dipendente_id", 1), ("data_inizio", -1)], name="idx_assenze_dip_data")
        await _safe_index("attendance_timbrature", [("dipendente_id", 1), ("timestamp", -1)], name="idx_timbrature_dip")

        # --- Acconti / TFR ---
        await _safe_index("acconti_dipendenti", "dipendente_id", name="idx_acconti_dip")
        # Compound index per query "tutti gli acconti di tizio per il mese X"
        await _safe_index(
            "acconti_dipendenti",
            [("dipendente_id", 1), ("scalato_su_anno_mese", 1)],
            name="idx_acconti_dip_scalato",
        )
        # Indice per filtrare/aggregare per stato lifecycle
        await _safe_index("acconti_dipendenti", "stato", name="idx_acconti_stato")
        # Indice per riconciliazione: "trovami acconti collegati a questo movimento"
        await _safe_index(
            "acconti_dipendenti",
            "movimento_bancario_id",
            name="idx_acconti_movimento",
            sparse=True,
        )
        await _safe_index("tfr_accantonamenti", [("dipendente_id", 1), ("anno", 1)], name="idx_tfr_dip_anno")
        await _safe_index("trattenute_dipendenti", "dipendente_id", name="idx_trattenute_dip")
        # Indici per workflow disciplinari (Task 4)
        await _safe_index(
            "trattenute_dipendenti",
            [("dipendente_id", 1), ("anno", 1), ("mese", 1)],
            name="idx_trattenute_dip_periodo",
        )
        await _safe_index("trattenute_dipendenti", "stato", name="idx_trattenute_stato")
        await _safe_index(
            "trattenute_dipendenti",
            "cedolino_id",
            name="idx_trattenute_cedolino",
            sparse=True,
        )

        # --- Notifications ---
        await _safe_index("notifications", [("created_at", -1)], name="idx_notif_data")
        await _safe_index("notifications", "letta", name="idx_notif_letta")

        # --- Documents inbox ---
        await _safe_index("documents_inbox", [("received_at", -1)], name="idx_docs_inbox_data")
        await _safe_index("documents_inbox", "stato", name="idx_docs_inbox_stato")

        # --- Prima nota salari ---
        await _safe_index("prima_nota_salari", [("anno", 1), ("mese", 1)], name="idx_pn_salari_anno_mese")
        await _safe_index("prima_nota_salari", "dipendente_id", sparse=True, name="idx_pn_salari_dip")

        # --- Movimenti contabili ---
        await _safe_index("movimenti_contabili", [("data", -1)], name="idx_mov_cont_data")
        await _safe_index("movimenti_contabili", [("anno", 1), ("conto", 1)], name="idx_mov_cont_anno_conto")
        # Protocollo per anno (§6.1/A7, scelta utente 2026-07-14): ricerca veloce
        # del "prossimo numero" e verifica di unicità del protocollo nell'anno.
        await _safe_index("movimenti_contabili", [("anno", 1), ("numero_registrazione", 1)],
                          name="idx_mov_cont_anno_protocollo")

        # --- Cash ---
        await _safe_index("cash", [("data", -1)], name="idx_cash_data")
        await _safe_index("cash", [("anno", 1), ("tipo", 1)], name="idx_cash_anno_tipo")

        # --- Fatture emesse ---
        await _safe_index("fatture_emesse", [("data_emissione", -1)], name="idx_fe_data")
        await _safe_index("fatture_emesse", "stato", name="idx_fe_stato")

        # --- Acquisti prodotti ---
        await _safe_index("acquisti_prodotti", [("data", -1)], name="idx_acquisti_data")
        await _safe_index("acquisti_prodotti", "fornitore_id", sparse=True, name="idx_acquisti_fornitore")

        # --- Veicoli noleggio ---
        await _safe_index("veicoli_noleggio", "targa", unique=True, sparse=True, name="idx_veicoli_targa")
        await _safe_index("veicoli_noleggio", "disponibile", name="idx_veicoli_disponibile")

        # --- Riepilogo cedolini ---
        await _safe_index("riepilogo_cedolini", [("anno", 1), ("mese", 1)], name="idx_riep_ced_anno_mese")

        # --- Agenti segnalazioni ---
        await _safe_index("agenti_segnalazioni", [("created_at", -1)], name="idx_agenti_segn_data")
        await _safe_index("agenti_segnalazioni", "stato", name="idx_agenti_segn_stato")

        # --- Operazioni da confermare ---
        await _safe_index("operazioni_da_confermare", [("created_at", -1)], name="idx_op_conf_data")
        await _safe_index("operazioni_da_confermare", "stato", name="idx_op_conf_stato")
        await _safe_index("partite_aperte", [("stato", 1), ("tipo", 1)], name="idx_pa_stato_tipo")
        await _safe_index("partite_aperte", [("controparte_id", 1), ("stato", 1)], name="idx_pa_controparte")
        await _safe_index("partite_aperte", [("documento_id", 1), ("tipo", 1)], name="idx_pa_doc_tipo")
        await _safe_index("partite_aperte", "data_scadenza", name="idx_pa_scadenza")

        # --- Riconciliazioni Match (Chat 8) ---
        await _safe_index("riconciliazioni_match", "id", unique=True, name="idx_rm_id")
        await _safe_index("riconciliazioni_match", [("movimento_id", 1)], name="idx_rm_movimento")
        await _safe_index("riconciliazioni_match", [("partita_id", 1)], name="idx_rm_partita")
        await _safe_index("riconciliazioni_match", [("stato", 1)], name="idx_rm_stato")

        # --- Audit Log (Chat 8) ---
        await _safe_index("audit_log", "id", unique=True, name="idx_audit_id")
        await _safe_index("audit_log", [("entita_id", 1), ("timestamp", -1)], name="idx_audit_entita")
        await _safe_index("audit_log", [("modulo", 1), ("timestamp", -1)], name="idx_audit_modulo")

        # --- Alert Definitions (Chat 8) ---
        await _safe_index("alert_definitions", "codice", unique=True, name="idx_alertdef_codice")

        # --- Alerts (Chat 8) ---
        await _safe_index("alerts", "id", unique=True, sparse=True, name="idx_alerts_id")
        await _safe_index("alerts", [("codice", 1), ("entita_id", 1), ("stato", 1)], name="idx_alerts_codice_entita")
        await _safe_index("alerts", [("modulo", 1), ("stato", 1)], name="idx_alerts_modulo_stato")

        # --- Liquidazioni IVA (SPECIFICA_IVA.md §22, Fase 3) ---
        await _safe_index("liquidazioni_iva", "id", unique=True, name="idx_liq_iva_id")
        await _safe_index("liquidazioni_iva", [("periodo", 1), ("versione", -1)], name="idx_liq_iva_periodo_ver")
        await _safe_index("liquidazioni_iva", [("periodo", 1), ("stato", 1)], name="idx_liq_iva_periodo_stato")
        await _safe_index("movimenti_iva_fattura", "id", unique=True, name="idx_mov_iva_id")
        await _safe_index("movimenti_iva_fattura", [("fattura_id", 1), ("created_at", -1)], name="idx_mov_iva_fattura")
        await _safe_index("movimenti_iva_fattura", [("periodo", 1), ("tipo_movimento", 1)], name="idx_mov_iva_periodo_tipo")
        await _safe_index("iva_ricalcolo_log", [("eseguito_il", -1)], name="idx_iva_ricalcolo_data")
        # Indici IVA su fatture (attribuzione/utilizzo per competenza)
        await _safe_index(Collections.INVOICES, "periodo_iva_attribuito", name="idx_invoices_periodo_iva")
        await _safe_index(Collections.INVOICES, "liquidazione_id", sparse=True, name="idx_invoices_liq_id")

        # --- Indici mancanti (AUDIT §7) ---
        # Scadenzario fornitori: query per fornitore/scadenza e per stato.
        await _safe_index("scadenziario_fornitori", [("fornitore_piva", 1), ("data_scadenza", 1)],
                          name="idx_scad_forn_piva_scad")
        await _safe_index("scadenziario_fornitori", [("stato", 1), ("data_scadenza", 1)],
                          name="idx_scad_forn_stato_scad")
        # Cespiti: query per anno e per categoria.
        await _safe_index("cespiti", [("anno", 1)], name="idx_cespiti_anno")
        await _safe_index("cespiti", "categoria", sparse=True, name="idx_cespiti_categoria")
        # Quietanze F24: chiave di collegamento quietanza↔F24 (SPECIFICA §22).
        await _safe_index("quietanze_f24",
                          [("codice_fiscale", 1), ("periodo", 1), ("saldo_delega", 1), ("data_versamento", 1)],
                          name="idx_quietanze_chiave")
        await _safe_index("quietanze_f24", "f24_id", sparse=True, name="idx_quietanze_f24_id")
        # Contratti dipendenti: query per dipendente e per validità.
        await _safe_index("contratti_dipendenti", "dipendente_id", name="idx_contratti_dip")
        await _safe_index("contratti_dipendenti", [("dipendente_id", 1), ("data_inizio", -1)],
                          name="idx_contratti_dip_inizio")
        # Documenti non associati: dedup per impronta + coda per data.
        await _safe_index("documenti_non_associati", "pdf_hash", sparse=True, name="idx_docnonass_hash")
        await _safe_index("documenti_non_associati", [("created_at", -1)], name="idx_docnonass_data")

        # --- Collezioni introdotte in questa sessione ---
        # Fascicolo F24 (§21): chiave univoca soggetto+periodo.
        await _safe_index("fascicoli_f24", "chiave", unique=True, sparse=True, name="idx_fascicoli_chiave")
        # Storia fattura: chiave stabile invoice_key (registro che sopravvive all'azzeramento).
        await _safe_index("storia_fatture", "invoice_key", unique=True, sparse=True, name="idx_storia_invoice_key")
        # Mittenti attendibili unificati: accessor per tipo/canale/attivo.
        await _safe_index("mittenti_email", [("tipo_documento", 1), ("canale", 1), ("attivo", 1)],
                          name="idx_mittenti_tipo_canale")
        # Dedup cross-canale documents_inbox per impronta md5.
        await _safe_index("documents_inbox", "file_hash", sparse=True, name="idx_docs_inbox_hash")

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
