"""
Azienda in Cloud ERP - Main Application Entry Point
FastAPI application with MongoDB Atlas - Refactored Modular Architecture
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.database import Database
from app.utils.logger import setup_logging, get_logger
from app.middleware.error_handler import add_exception_handlers

# Setup logging first
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    
    # Connect to database (with error handling)
    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        # Continue anyway - health check will show database disconnected
    
    # Validate critical configuration
    settings.validate_startup()
    secrets_status = settings.validate_required_secrets()
    if not secrets_status.get('auth'):
        logger.critical("⚠️ SECRET_KEY non configurata nel .env! Usando chiave temporanea.")
    if not secrets_status.get('database'):
        logger.critical("⚠️ MONGODB_ATLAS_URI non configurata! Il database non funzionerà.")
    
    # Avvia monitor email automatico (ogni 10 minuti)
    try:
        from app.services.email_monitor_service import start_monitor
        db = Database.get_db()
        if db is not None:
            start_monitor(db, interval_seconds=600)  # 10 minuti
            logger.info("📬 Monitor email avviato (ogni 10 minuti)")
    except Exception as e:
        logger.warning(f"Monitor email non avviato: {e}")
    
    # Avvia scheduler per task automatici (HACCP, Verbali, Gmail/Aruba)
    try:
        from app.scheduler import start_scheduler
        start_scheduler()
        logger.info("⏰ Scheduler avviato (HACCP, Verbali, Email)")
    except Exception as e:
        logger.warning(f"Scheduler non avviato: {e}")
    
    logger.info("✅ Application startup complete")
    
    # Migrazione one-shot: pulisci movimenti bancari da prima_nota_cassa (skip if no db)
    try:
        db = Database.get_db()
        if db is not None:
            from app.routers.prima_nota_module.manutenzione import migrazione_pulisci_bancari_da_cassa
            result = await migrazione_pulisci_bancari_da_cassa()
            if result.get("movimenti_eliminati", 0) > 0:
                logger.info(f"🧹 Migrazione cassa: {result['message']}")
            else:
                logger.info("🧹 Migrazione cassa: nessun movimento bancario da pulire")
    except Exception as e:
        logger.warning(f"Migrazione cassa non eseguita: {e}")
    
    yield
    
    # Shutdown
    logger.info("🔄 Shutting down application...")
    
    # Ferma monitor email
    try:
        from app.services.email_monitor_service import stop_monitor
        stop_monitor()
        logger.info("📬 Monitor email fermato")
    except Exception:
        pass
    
    # Ferma scheduler
    try:
        from app.scheduler import stop_scheduler
        stop_scheduler()
        logger.info("⏰ Scheduler fermato")
    except Exception:
        pass
    
    await Database.close_db()
    logger.info("✅ Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Add Rate Limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("🛡️ Rate limiting attivo: 200 req/min default")
except ImportError:
    logger.warning("⚠️ slowapi non installato, rate limiting disabilitato")
    limiter = None

# Add global authentication middleware (safety net for all /api/ endpoints)
# Richiede token JWT valido per tutti gli endpoint /api/ eccetto /api/auth/* e /api/public/*
from app.middleware.authentication import AuthenticationMiddleware
app.add_middleware(AuthenticationMiddleware)

# Add exception handlers
add_exception_handlers(app)


# =============================================================================
# MODULAR ROUTER IMPORTS
# =============================================================================

# --- F24 Module ---
from app.routers.f24 import (
    f24_main, f24_riconciliazione, f24_public, quietanze
)

# --- Accounting Module ---
from app.routers.accounting import (
    accounting_main, accounting_extended, accounting_engine_api,
    prima_nota_automation, prima_nota_salari,
    piano_conti, bilancio, centri_costo, contabilita_avanzata,
    regole_categorizzazione, iva_calcolo, liquidazione_iva,
    riconciliazione_automatica, contabilita_gestionale
)
# Prima Nota modularizzato
from app.routers.prima_nota_module import router as prima_nota_router

# --- To-Do Module ---
from app.routers import todo

# --- Bank Module ---
from app.routers.bank import (
    bank_main, bank_reconciliation, bank_statement_import,
    bank_statement_parser, estratto_conto, assegni, pos_accredito,
    bank_statement_bulk_import, assegni_learning
)
# Archivio Bonifici modularizzato
from app.routers.bonifici_module import router as archivio_bonifici_router
from app.routers.bank import riconciliazione_f24_banca

# --- Warehouse Module ---
from app.routers.warehouse import (
    warehouse_main, magazzino, magazzino_products, magazzino_doppia_verita,
    products, products_catalog, lotti, tracciabilita, dizionario_articoli
)

# --- Invoices Module ---
from app.routers.invoices import (
    invoices_main, invoices_emesse, invoices_export, fatture_upload, corrispettivi
)
# Fatture Ricevute modularizzato
from app.routers.fatture_module import router as fatture_ricevute_router

# --- Sync Relazionale ---
from app.routers import sync_relazionale

# --- Ciclo Passivo Integrato ---
from app.routers import ciclo_passivo_integrato

# --- Employees Module ---
from app.routers.employees import (
    dipendenti, employees_payroll, employee_contracts, buste_paga, shifts, staff, giustificativi
)

# --- Noleggio Module ---
from app.routers import noleggio

# --- Reports Module ---
from app.routers.reports import (
    report_pdf, exports, simple_exports, analytics, dashboard
)

# --- OpenAPI Imprese Integration ---
from app.routers import openapi_imprese

# --- Core Routers (non modulari) ---
from app.routers import (
    auth, cash, chart_of_accounts, notifications,
    cash_register, failed_invoices, settings as settings_router,
    config, search, incasso_reale, ocr_assegni, cart, portal, orders,
    portal_extended, cash_register_extended, finanziaria, public_api,
    comparatore, gestione_riservata, commercialista, scadenze,
    riconciliazione_fornitori, ordini_fornitori, payroll, documents,
    pianificazione, admin, verifica_coerenza, documenti,
    previsioni_acquisti,
    cedolini, tfr, cespiti, scadenzario_fornitori,
    controllo_gestione, indici_bilancio, chiusura_esercizio,
    gestione_iva_speciale, configurazioni, alerts, import_templates,
    dizionario_prodotti, inventario, manutenzione, verbali_noleggio_api,
    openapi_it
)
# Operazioni da Confermare modularizzato
from app.routers.operazioni_module import router as operazioni_router
from app.routers.suppliers_module import router as suppliers_router
from app.routers import cedolini_riconciliazione
from app.routers import pagopa  # PagoPA - Associazione ricevute
from app.routers import invoicetronic  # InvoiceTronic - Fatturazione Elettronica SDI
from app.routers import verbali_noleggio  # Verbali Noleggio da Email
from app.routers import verbali_riconciliazione  # Riconciliazione Verbali (Fattura + Pagamento + Driver)
from app.routers import bonifici_stipendi  # Bonifici Stipendi da Email
from app.routers import inps_documenti  # INPS - Delibere FONSI, Dilazioni
from app.routers import adr  # ADR - Definizione Agevolata
from app.routers import dimissioni  # Dimissioni dipendenti
from app.routers import documenti_intelligenti  # Sistema classificazione email intelligente
from app.routers import document_ai  # Document AI - Estrazione dati con OCR + LLM
from app.routers import email_reconciliation  # Riconciliazione Email ↔ Gestionale
from app.routers import email_scanner  # Scanner Email Completo - Tutta la posta
from app.routers import email_download  # Download Completo Email con Salvataggio DB
from app.routers import codici_tributari  # Gestione Codici Tributari F24 - Riconciliazione 3 vie
from app.routers import learning_machine  # Learning Machine - Classificazione documenti intelligente
from app.routers import learning_machine_cdc  # Learning Machine CDC - Classificazione per Centro di Costo
from app.routers import magazzino_avanzato  # Magazzino Avanzato - Categorie merceologiche e lotti
from app.routers import riconciliazione_intelligente_api  # Riconciliazione Intelligente - Conferma Pagamenti
from app.routers import attendance  # Gestione Presenze Dipendenti (legacy)
from app.routers.attendance_module import presenze as attendance_presenze  # Presenze calendario
from app.routers import inserimento_rapido  # Inserimento Rapido - Mobile
from app.routers import email_mongodb  # Email to MongoDB - Download email su Atlas
from app.routers import documenti_non_associati  # Gestione documenti non associati
from app.routers import fornitori_learning  # Fornitori Learning - Associazione keywords
from app.routers import ai_parser  # AI Parser - Estrazione intelligente documenti
from app.routers import upload_ai  # Upload AI - Parsing automatico su upload diretto
# REMOVED: chat_router - replaced by OpenClaw
from app.routers import schede_tecniche  # Schede Tecniche Prodotti
from app.routers import auto_repair  # Auto-Riparazione Globale delle relazioni
from app.routers import odoo_integration  # Integrazione Odoo External API
from app.routers import accounting_engine  # Motore Contabile Odoo-style
from app.routers import contabilita_italiana  # Contabilità Italiana Completa
from app.routers import fiscalita_italiana  # Fiscalità e Calendario Scadenze
# REMOVED: claude_api - replaced by OpenClaw
from app.routers import batch_operations  # Operazioni Batch - Riconcilia/Paga N documenti
from app.routers import google_auth  # Google OAuth - Login con Google
from app.routers import openclaw  # OpenClaw/MoltBot AI Assistant


# =============================================================================
# ROUTER REGISTRATION
# =============================================================================

# --- Public API (no auth) ---
app.include_router(public_api.router, prefix="/api", tags=["Public API"])

# --- Authentication ---
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(google_auth.router, prefix="/api", tags=["Google OAuth"])
app.include_router(openclaw.router, prefix="/api", tags=["OpenClaw AI Assistant"])

# --- F24 Module ---
app.include_router(f24_main.router, prefix="/api/f24", tags=["F24"])
app.include_router(f24_riconciliazione.router, prefix="/api/f24-riconciliazione", tags=["F24 Riconciliazione"])
# DISABILITATO: f24_tributi - endpoint duplicati con f24_main
# app.include_router(f24_tributi.router, prefix="/api/f24", tags=["F24 Tributi"])
app.include_router(f24_public.router, prefix="/api/f24-public", tags=["F24 Public"])
app.include_router(quietanze.router, prefix="/api/quietanze-f24", tags=["Quietanze F24"])

# F24 Notifiche Push (scadenze con alert Telegram + Email)
from app.routers.f24 import f24_notifiche
app.include_router(f24_notifiche.router, prefix="/api/f24-notifiche", tags=["F24 Notifiche Push"])

# F24 Email Settings - Impostazioni per download automatico F24 da email
from app.routers import f24_email_settings
app.include_router(f24_email_settings.router, prefix="/api/f24-email-settings", tags=["F24 Email Settings"])
# DISABILITATO: f24_gestione_avanzata - non usato dal frontend
# app.include_router(f24_gestione_avanzata.router, prefix="/api/f24-avanzato", tags=["F24 Gestione Avanzata"])
app.include_router(codici_tributari.router, prefix="/api/codici-tributari", tags=["Codici Tributari"])

# --- Accounting Module ---
app.include_router(accounting_main.router, prefix="/api/accounting", tags=["Accounting"])
app.include_router(accounting_extended.router, prefix="/api/accounting", tags=["Accounting Extended"])
# DISABILITATO: accounting_f24 - non usato, duplicato con f24_main
# app.include_router(accounting_f24.router, prefix="/api/f24", tags=["F24 Accounting"])
app.include_router(accounting_engine_api.router, prefix="/api/accounting-engine", tags=["Accounting Engine - Partita Doppia"])
# Prima Nota - Modulo refactorizzato (cassa, banca, salari unificati)
app.include_router(prima_nota_router, prefix="/api/prima-nota", tags=["Prima Nota"])
app.include_router(prima_nota_automation.router, prefix="/api/prima-nota-auto", tags=["Prima Nota Automation"])
# Prima Nota Salari - Modulo legacy per compatibilità frontend
app.include_router(prima_nota_salari.router, prefix="/api/prima-nota-salari", tags=["Prima Nota Salari"])
app.include_router(piano_conti.router, prefix="/api/piano-conti", tags=["Piano dei Conti"])
app.include_router(bilancio.router, prefix="/api/bilancio", tags=["Bilancio"])
app.include_router(contabilita_gestionale.router, tags=["Contabilità Gestionale"])
app.include_router(centri_costo.router, prefix="/api/centri-costo", tags=["Centri di Costo"])
app.include_router(contabilita_avanzata.router, prefix="/api/contabilita", tags=["Contabilita Avanzata"])
app.include_router(regole_categorizzazione.router, prefix="/api/regole", tags=["Regole Categorizzazione"])
app.include_router(iva_calcolo.router, prefix="/api/iva", tags=["IVA Calcolo"])
app.include_router(liquidazione_iva.router, prefix="/api", tags=["Liquidazione IVA"])
app.include_router(riconciliazione_automatica.router, prefix="/api/riconciliazione-auto", tags=["Riconciliazione Automatica"])
app.include_router(riconciliazione_intelligente_api.router, prefix="/api/riconciliazione-intelligente", tags=["Riconciliazione Intelligente"])

# --- Batch Operations ---
app.include_router(batch_operations.router, prefix="/api/batch", tags=["Batch Operations"])

# --- Attendance Module ---
app.include_router(attendance.router, prefix="/api/attendance", tags=["Attendance"])
app.include_router(attendance_presenze.router, prefix="/api/attendance", tags=["Attendance Presenze"])

# --- To-Do Module ---
app.include_router(todo.router, prefix="/api/todo", tags=["To-Do"])

# --- Bank Module ---
app.include_router(bank_main.router, prefix="/api/bank", tags=["Bank"])
app.include_router(bank_reconciliation.router, prefix="/api/bank-reconciliation", tags=["Bank Reconciliation"])
app.include_router(bank_statement_import.router, prefix="/api/bank-statement", tags=["Bank Statement Import"])
app.include_router(bank_statement_parser.router, prefix="/api/estratto-conto", tags=["Estratto Conto Parser"])
app.include_router(bank_statement_bulk_import.router, prefix="/api/bank-statement-bulk", tags=["Bank Statement Bulk Import"])
app.include_router(estratto_conto.router, prefix="/api/estratto-conto-movimenti", tags=["Estratto Conto Movimenti"])
app.include_router(archivio_bonifici_router, prefix="/api/archivio-bonifici", tags=["Archivio Bonifici"])
app.include_router(assegni.router, prefix="/api/assegni", tags=["Assegni"])
app.include_router(assegni_learning.router, prefix="/api/assegni/learning", tags=["Assegni Learning Machine"])
app.include_router(pos_accredito.router, prefix="/api/pos-accredito", tags=["POS Accredito"])
app.include_router(riconciliazione_f24_banca.router, prefix="/api/f24-riconciliazione", tags=["Riconciliazione F24 Banca"])

# --- Warehouse Module ---
app.include_router(warehouse_main.router, prefix="/api/warehouse", tags=["Warehouse"])
app.include_router(magazzino.router, prefix="/api/magazzino", tags=["Magazzino"])
app.include_router(magazzino_products.router, prefix="/api/magazzino", tags=["Magazzino Products"])
app.include_router(magazzino_doppia_verita.router, prefix="/api/magazzino-dv", tags=["Magazzino Doppia Verità"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(products_catalog.router, prefix="/api/products", tags=["Products Catalog"])
app.include_router(lotti.router, prefix="/api/lotti", tags=["Lotti"])
app.include_router(tracciabilita.router, prefix="/api/tracciabilita", tags=["Tracciabilita"])
app.include_router(dizionario_articoli.router, prefix="/api/dizionario-articoli", tags=["Dizionario Articoli"])

# --- Invoices Module ---
app.include_router(invoices_emesse.router, prefix="/api/invoices/emesse", tags=["Invoices Emesse"])
app.include_router(invoices_main.router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(invoices_export.router, prefix="/api/invoices", tags=["Invoices Export"])
app.include_router(fatture_upload.router, prefix="/api/fatture", tags=["Fatture Upload"])
app.include_router(fatture_ricevute_router, prefix="/api/fatture-ricevute", tags=["Fatture Ricevute"])
app.include_router(corrispettivi.router, prefix="/api/corrispettivi", tags=["Corrispettivi"])

# --- Ciclo Passivo Integrato (XML → Magazzino → Prima Nota → Scadenziario → Riconciliazione) ---
app.include_router(ciclo_passivo_integrato.router, prefix="/api/ciclo-passivo", tags=["Ciclo Passivo Integrato"])

# --- Employees Module ---
app.include_router(dipendenti.router, prefix="/api/dipendenti", tags=["Dipendenti"])
app.include_router(employees_payroll.router, prefix="/api/employees", tags=["Employees Payroll"])
app.include_router(employee_contracts.router, prefix="/api/contracts", tags=["Employee Contracts"])
app.include_router(buste_paga.router, prefix="/api", tags=["Buste Paga"])
app.include_router(shifts.router, prefix="/api/shifts", tags=["Shifts"])
app.include_router(staff.router, prefix="/api/staff", tags=["Staff"])
app.include_router(giustificativi.router, prefix="/api/giustificativi", tags=["Giustificativi Dipendenti"])
app.include_router(payroll.router, prefix="/api/payroll", tags=["Payroll"])
app.include_router(noleggio.router, prefix="/api/noleggio", tags=["Noleggio Auto"])

# --- Reports Module ---
app.include_router(report_pdf.router, prefix="/api/report-pdf", tags=["Report PDF"])
app.include_router(exports.router, prefix="/api/exports", tags=["Exports"])
app.include_router(simple_exports.router, prefix="/api/exports", tags=["Simple Exports"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

# --- Core Routers ---
app.include_router(suppliers_router, prefix="/api/suppliers", tags=["Suppliers"])
# Alias italiano per compatibilità frontend
app.include_router(suppliers_router, prefix="/api/fornitori", tags=["Fornitori"])
app.include_router(cash.router, prefix="/api/cash", tags=["Cash Register"])
app.include_router(chart_of_accounts.router, prefix="/api/chart-of-accounts", tags=["Chart of Accounts"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(cash_register.router, prefix="/api/cash-register", tags=["Cash Register Operations"])
app.include_router(cash_register_extended.router, prefix="/api/cash-register", tags=["Cash Register Extended"])
app.include_router(failed_invoices.router, prefix="/api/failed-invoices", tags=["Failed Invoices"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(config.router, prefix="/api/config", tags=["Config"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(incasso_reale.router, prefix="/api/incasso-reale", tags=["Incasso Reale"])
app.include_router(ocr_assegni.router, prefix="/api/ocr-assegni", tags=["OCR Assegni"])
app.include_router(cart.router, prefix="/api/cart", tags=["Cart"])
app.include_router(portal.router, prefix="/api/portal", tags=["Portal"])
app.include_router(portal_extended.router, prefix="/api/portal", tags=["Portal Extended"])
app.include_router(orders.router, prefix="/api", tags=["Orders"])
app.include_router(finanziaria.router, prefix="/api/finanziaria", tags=["Finanziaria"])
app.include_router(comparatore.router, prefix="/api/comparatore", tags=["Comparatore Prezzi"])
app.include_router(gestione_riservata.router, prefix="/api/gestione-riservata", tags=["Gestione Riservata"])
app.include_router(commercialista.router, prefix="/api/commercialista", tags=["Commercialista"])
app.include_router(scadenze.router, prefix="/api/scadenze", tags=["Scadenze e Notifiche"])
app.include_router(riconciliazione_fornitori.router, prefix="/api/riconciliazione-fornitori", tags=["Riconciliazione Fornitori"])
app.include_router(ordini_fornitori.router, prefix="/api/ordini-fornitori", tags=["Ordini Fornitori"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(pianificazione.router, prefix="/api/pianificazione", tags=["Pianificazione"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(verifica_coerenza.router, prefix="/api/verifica-coerenza", tags=["Verifica Coerenza Dati"])
app.include_router(documenti.router, prefix="/api/documenti", tags=["Gestione Documenti Email"])
app.include_router(operazioni_router, prefix="/api/operazioni-da-confermare", tags=["Operazioni da Confermare"])
app.include_router(previsioni_acquisti.router, prefix="/api/previsioni-acquisti", tags=["Previsioni Acquisti"])
app.include_router(cedolini.router, prefix="/api/cedolini", tags=["Cedolini Paga"])
app.include_router(cedolini_riconciliazione.router, prefix="/api/cedolini", tags=["Cedolini Riconciliazione"])

# Salari Unificati V2 (saldi completi, acconti, ferie/ROL, riconciliazione banca)
from app.routers import salari_unificati_v2
app.include_router(salari_unificati_v2.router, prefix="/api/salari-v2", tags=["Salari Unificati V2"])
app.include_router(tfr.router, prefix="/api/tfr", tags=["TFR"])
app.include_router(cespiti.router, prefix="/api/cespiti", tags=["Cespiti e Ammortamenti"])
app.include_router(fiscalita_italiana.router, prefix="/api/fiscalita", tags=["Fiscalità Italiana"])
app.include_router(scadenzario_fornitori.router, prefix="/api/scadenzario-fornitori", tags=["Scadenzario Fornitori"])

# --- Mutui Module ---
from app.routers import mutui
from app.routers import mutui_parser
from app.routers import libro_unico_parser
from app.routers import f24_parser
app.include_router(mutui.router, prefix="/api/mutui", tags=["Mutui"])
app.include_router(mutui_parser.router, prefix="/api/mutui", tags=["Mutui Parser PDF"])
app.include_router(libro_unico_parser.router, prefix="/api/paghe", tags=["Libro Unico Parser"])
app.include_router(f24_parser.router, prefix="/api/paghe", tags=["F24 Parser"])

# calcolo_iva rimosso - usa liquidazione_iva invece (più completo e corretto)
app.include_router(controllo_gestione.router, prefix="/api/controllo-gestione", tags=["Controllo Gestione"])
app.include_router(indici_bilancio.router, prefix="/api/indici-bilancio", tags=["Indici di Bilancio"])
app.include_router(chiusura_esercizio.router, prefix="/api/chiusura-esercizio", tags=["Chiusura Esercizio"])
app.include_router(gestione_iva_speciale.router, prefix="/api/iva-speciale", tags=["IVA Speciale"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alert Sistema"])
app.include_router(import_templates.router, prefix="/api/import-templates", tags=["Import Templates"])

# --- Import Manuale (POS, Versamenti, Finanziamento Soci) ---
from app.routers import import_manuale
app.include_router(import_manuale.router, prefix="/api/import-manuale", tags=["Import Manuale"])

# --- Dizionario Prodotti (Food Cost & Tracciabilità) ---
app.include_router(dizionario_prodotti.router, prefix="/api/dizionario-prodotti", tags=["Dizionario Prodotti"])

# --- Inventario ---
app.include_router(inventario.router, prefix="/api", tags=["Inventario"])

# --- PagoPA - Associazione Ricevute ---
app.include_router(pagopa.router, tags=["PagoPA"])

# --- InvoiceTronic - Fatturazione Elettronica SDI ---
app.include_router(invoicetronic.router, tags=["InvoiceTronic SDI"])

# --- Verbali Noleggio da Email ---
app.include_router(verbali_noleggio.router, tags=["Verbali Noleggio"])
app.include_router(verbali_noleggio_api.router, prefix="/api/verbali-noleggio", tags=["Verbali Noleggio API"])
app.include_router(verbali_riconciliazione.router, prefix="/api/verbali-riconciliazione", tags=["Verbali Riconciliazione"])

# --- Email Scanner Completo - Tutta la posta ---
app.include_router(email_scanner.router, tags=["Email Scanner"])

# --- Download Completo Email con Salvataggio DB ---
app.include_router(email_download.router, prefix="/api", tags=["Email Download"])

# --- Manutenzione Dati ---
app.include_router(manutenzione.router, prefix="/api/manutenzione", tags=["Manutenzione Dati"])

# --- OpenAPI.it Integration (SDI, AISP) ---
app.include_router(openapi_it.router, prefix="/api/openapi", tags=["OpenAPI.it SDI/AISP"])

# --- OpenAPI Imprese (Anagrafica Fornitori) ---
app.include_router(openapi_imprese.router, prefix="/api", tags=["OpenAPI Imprese"])

# --- OpenAPI Automotive (Visure Veicoli) ---
from app.routers import openapi_automotive
app.include_router(openapi_automotive.router, prefix="/api", tags=["OpenAPI Automotive"])

# --- Inserimento Rapido Mobile ---
app.include_router(inserimento_rapido.router, prefix="/api", tags=["Inserimento Rapido"])

# --- Email to MongoDB (tutto su Atlas, niente filesystem) ---
app.include_router(email_mongodb.router, prefix="/api", tags=["Email MongoDB"])

# --- Documenti Non Associati (gestione manuale) ---
app.include_router(documenti_non_associati.router, prefix="/api", tags=["Documenti Non Associati"])

# --- Bonifici Stipendi da Email ---
app.include_router(bonifici_stipendi.router, tags=["Bonifici Stipendi"])

# --- INPS Documenti (Delibere FONSI, Dilazioni) ---
app.include_router(inps_documenti.router, prefix="/api/inps", tags=["INPS Documenti"])

# --- ADR Definizione Agevolata ---
app.include_router(adr.router, prefix="/api/adr", tags=["ADR Definizione Agevolata"])

# --- Dimissioni Dipendenti ---
app.include_router(dimissioni.router, prefix="/api/dimissioni", tags=["Dimissioni"])

# --- Documenti Intelligenti (Classificazione Email) ---
app.include_router(documenti_intelligenti.router, prefix="/api/documenti-smart", tags=["Documenti Intelligenti"])

# --- Document AI (OCR + LLM Extraction) ---
app.include_router(document_ai.router, prefix="/api/document-ai", tags=["Document AI"])

# --- AI Parser (Lettura intelligente documenti con Gemini) ---
app.include_router(ai_parser.router, prefix="/api/ai-parser", tags=["AI Parser"])

# --- Upload AI (Parsing automatico su upload diretto) ---
app.include_router(upload_ai.router, prefix="/api/upload-ai", tags=["Upload AI"])

# REMOVED: Chat Intelligente - replaced by OpenClaw
# app.include_router(chat_router.router, prefix="/api/chat", tags=["Chat Intelligente"])

# --- Schede Tecniche Prodotti ---
app.include_router(schede_tecniche.router, prefix="/api", tags=["Schede Tecniche Prodotti"])

# --- Auto-Riparazione Globale ---
app.include_router(auto_repair.router, prefix="/api", tags=["Auto Riparazione"])

# --- Riconciliazione Email ↔ Gestionale ---
app.include_router(email_reconciliation.router, tags=["Riconciliazione Email"])

# --- Sincronizzazione Relazionale ---
app.include_router(sync_relazionale.router, prefix="/api", tags=["Sincronizzazione Relazionale"])

# --- Configurazioni Sistema ---
app.include_router(configurazioni.router, prefix="/api/config", tags=["Configurazioni"])

# --- WebSocket Real-time ---
from app.routers import websocket_realtime
app.include_router(websocket_realtime.router, prefix="/api", tags=["WebSocket Real-time"])
app.include_router(learning_machine.router, prefix="/api/learning-machine", tags=["Learning Machine"])
app.include_router(learning_machine_cdc.router, prefix="/api", tags=["Learning Machine CDC"])
app.include_router(fornitori_learning.router, prefix="/api", tags=["Fornitori Learning"])
app.include_router(magazzino_avanzato.router, prefix="/api", tags=["Magazzino Avanzato"])
app.include_router(odoo_integration.router, prefix="/api/odoo", tags=["Odoo Integration"])
app.include_router(accounting_engine.router, prefix="/api/accounting", tags=["Accounting Engine"])
app.include_router(contabilita_italiana.router, prefix="/api/contabilita", tags=["Contabilità Italiana"])

# --- Claude AI API (Assistente Contabile Intelligente) ---
# REMOVED: Claude AI - replaced by OpenClaw
# app.include_router(claude_api.router, prefix="/api/claude", tags=["Claude AI"])

# --- PayPal Statements (MSR/CSR) ---
from app.routers import paypal_statements
app.include_router(paypal_statements.router, prefix="/api/paypal-statements", tags=["PayPal Statements"])

# --- Fix Endpoint Mancanti (frontend → backend) ---
from app.routers import missing_endpoints
#from app.routers import fix_endpoints_mancanti  # Fix endpoint 404
#from app.routers import sync_router  # Sync email configuration
#from app.routers import fix_sync_diagnostica  # Diagnostica e sync
#from app.routers import fix_riconciliazione_endpoints  # Fix riconciliazione 404
#from app.routers import fix_estratto_conto_batch  # Ricategorizzazione estratto conto
#app.include_router(missing_endpoints.router, prefix="/api", tags=["Fix Endpoint Mancanti"])
#app.include_router(fix_endpoints_mancanti.router, prefix="/api", tags=["Fix Endpoint 404"])
#app.include_router(sync_router.router, prefix="/api", tags=["Sync Email"])
#app.include_router(fix_sync_diagnostica.router, prefix="/api/sync", tags=["Sync Diagnostica"])
#app.include_router(fix_riconciliazione_endpoints.router, prefix="/api/riconciliazione-auto", tags=["Fix Riconciliazione"])
#app.include_router(fix_estratto_conto_batch.router, prefix="/api/estratto-conto-movimenti", tags=["Estratto Conto Fix"])

# --- Archivio Bonifici Associazioni ---
from app.routers.bonifici_module import associazioni as bonifici_associazioni
app.include_router(bonifici_associazioni.router, prefix="/api", tags=["Archivio Bonifici Associazioni"])

# --- Enhanced Document Parser (F24 + Cedolini migliorati) ---
from app.routers import enhanced_parser
app.include_router(enhanced_parser.router, prefix="/api", tags=["Enhanced Parser"])

# --- Force Sync (Email Aruba + F24 Riconciliazione) ---
from app.routers import force_sync
app.include_router(force_sync.router, prefix="/api/force-sync", tags=["Force Sync"])

# --- Missing Endpoints Fix (health, ordini-fornitori) ---
from app.routers import missing_endpoints_fix
app.include_router(missing_endpoints_fix.router, prefix="/api", tags=["Missing Endpoints Fix"])

# --- Dati Provvisori (NUOVA LOGICA WORKFLOW) ---
from app.routers import dati_provvisori
app.include_router(dati_provvisori.router, prefix="/api", tags=["Dati Provvisori"])

# --- Batch Reprocessing (Riprocessamento massivo documenti) ---
from app.routers import batch_reprocessing
app.include_router(batch_reprocessing.router, prefix="/api", tags=["Batch Reprocessing"])


# --- POS Corrispettivi Check (Verifica coerenza POS/Corrispettivi XML) ---
from app.routers import pos_corrispettivi_check
app.include_router(pos_corrispettivi_check.router, prefix="/api", tags=["POS Corrispettivi Check"])


# --- Distinte BPM (Import distinte stipendi da banca BPM) ---
from app.routers import distinte_bpm
app.include_router(distinte_bpm.router, prefix="/api/paghe", tags=["Distinte BPM"])

# --- DIPENDENTI IN CLOUD (Nuovo modulo HR completo) ---
from app.routers.dipendenti_cloud import router as dipendenti_cloud_router
app.include_router(dipendenti_cloud_router, prefix="/api", tags=["Dipendenti Cloud"])


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "environment": settings.ENVIRONMENT
    }


@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Detailed health check endpoint."""
    from datetime import datetime, timezone
    db_status = "connected" if Database.db is not None else "disconnected"
    
    return {
        "status": "healthy",
        "database": db_status,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/ping")
async def ping():
    """
    Lightweight keep-alive endpoint.
    Use this for periodic health checks to prevent server standby.
    """
    return {"pong": True}


@app.get("/api/system/lock-status")
async def system_lock_status():
    """
    Stato dei lock per operazioni email/DB.
    Utile per verificare se ci sono operazioni in corso prima di avviarne altre.
    """
    from app.routers.documenti import is_email_operation_running, get_current_operation
    
    return {
        "email_locked": is_email_operation_running(),
        "operation": get_current_operation(),
        "can_start_email_operation": not is_email_operation_running()
    }


# Mount static files for downloads
docs_path = "./docs"
if os.path.exists(docs_path):
    app.mount("/api/download", StaticFiles(directory=docs_path), name="download")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD
    )
