"""
Azienda in Cloud ERP - Main Application Entry Point
FastAPI application with MongoDB Atlas - Refactored Modular Architecture
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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
    
    # DISABILITATO: Monitor email automatico ogni 10 minuti
    # Causa: tentativo IMAP con credenziali non valide blocca l'event loop FastAPI per ~30s
    # (IMAP timeout default). Riabilitare solo dopo aver configurato credenziali valide.
    # try:
    #     from app.services.email_monitor_service import start_monitor
    #     db = Database.get_db()
    #     if db is not None:
    #         start_monitor(db, interval_seconds=600)
    # except Exception as e:
    #     logger.warning(f"Monitor email non avviato: {e}")

    # DISABILITATO: Scheduler HACCP/Verbali/Gmail ogni 10 minuti
    # Stesso problema: IMAP blocca l'async event loop causando "reload" percepito dall'utente
    # try:
    #     from app.scheduler import start_scheduler
    #     start_scheduler()
    # except Exception as e:
    #     logger.warning(f"Scheduler non avviato: {e}")
    
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
# app.add_middleware(AuthenticationMiddleware)  # DISABILITATO - Login rimandato al deploy

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
    warehouse_main, magazzino, magazzino_products,
    products, products_catalog, dizionario_articoli
)

# --- Invoices Module ---
from app.routers.invoices import (
    invoices_main, invoices_emesse, invoices_export, fatture_upload, corrispettivi
)
# Fatture Ricevute modularizzato
from app.routers.fatture_module import router as fatture_ricevute_router
from app.routers.fatture_module.api_tracciabilita import router as r_api_tracciabilita

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
    cash_register, settings as settings_base,
    config, search, ocr_assegni, portal,
    finanziaria, public_api,
    comparatore, gestione_riservata, commercialista, scadenze,
    riconciliazione_fornitori, payroll,
    pianificazione, admin, verifica_coerenza, documenti,
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
# auto_repair rimosso (Blocco J1)
# odoo_integration rimosso (Blocco J1)
from app.routers import accounting_engine  # Motore Contabile Odoo-style
from app.routers import contabilita_italiana  # Contabilità Italiana Completa
from app.routers import fiscalita_italiana  # Fiscalità e Calendario Scadenze
# REMOVED: claude_api - replaced by OpenClaw
from app.routers import batch_operations  # Operazioni Batch - Riconcilia/Paga N documenti
from app.routers import google_auth  # Google OAuth - Login con Google
from app.routers import openclaw  # OpenClaw/MoltBot AI Assistant
from app.routers.agenti import router as r_agenti  # Agenti AI
from app.routers import settings_router  # Impostazioni Gestionale
from app.routers.erp_bridge import router as erp_bridge_router  # Ponte Tracciabilità → Gestionale


# =============================================================================
# ROUTER REGISTRATION
# =============================================================================

# --- Public API (no auth) ---
app.include_router(public_api.router, prefix="/api", tags=["Public API"])

# --- Authentication ---
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(google_auth.router, prefix="/api", tags=["Google OAuth"])
app.include_router(openclaw.router, prefix="/api", tags=["OpenClaw AI Assistant"])
app.include_router(r_agenti, prefix="/api", tags=["Agenti AI"])
app.include_router(settings_router.router, prefix="/api", tags=["Impostazioni"])
app.include_router(erp_bridge_router)  # Ponte Tracciabilità → Gestionale (/api/erp/ponte)

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
# magazzino_doppia_verita rimosso (Blocco J1)
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(products_catalog.router, prefix="/api/products", tags=["Products Catalog"])
# lotti rimosso (Blocco J1)
# tracciabilita rimosso (Blocco J1)
app.include_router(dizionario_articoli.router, prefix="/api/dizionario-articoli", tags=["Dizionario Articoli"])

# --- Invoices Module ---
app.include_router(invoices_emesse.router, prefix="/api/invoices/emesse", tags=["Invoices Emesse"])
app.include_router(invoices_main.router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(invoices_export.router, prefix="/api/invoices", tags=["Invoices Export"])
app.include_router(fatture_upload.router, prefix="/api/fatture", tags=["Fatture Upload"])
app.include_router(fatture_ricevute_router, prefix="/api/fatture-ricevute", tags=["Fatture Ricevute"])
app.include_router(r_api_tracciabilita, prefix="/api", tags=["API Tracciabilita"])

# --- Tracciabilita HACCP ---
try:
    from app.routers.tracciabilita import (
        lotti, lotti_fornitori, lotti_produzione, produzioni,
        temperature_negative, temperature_positive, sanificazione,
        disinfestazione, haccp_auto, haccp_report, report_haccp,
        anomalie, chiusure, attrezzature, costi_giornalieri,
        acquaviva, colazione, ricezione_merce, sconti_merce,
        vendita_banco, fornitori as tr_fornitori
    )
    from app.routers.tracciabilita import ricette as tr_ricette
    from app.routers.tracciabilita import prodotti_vendita as tr_prodotti
    app.include_router(lotti.router,                prefix="/api/tr", tags=["TR Lotti"])
    app.include_router(lotti_fornitori.router,      prefix="/api/tr", tags=["TR Lotti Fornitori"])
    app.include_router(lotti_produzione.router,     prefix="/api/tr", tags=["TR Lotti Produzione"])
    app.include_router(produzioni.router,           prefix="/api/tr", tags=["TR Produzioni"])
    app.include_router(temperature_positive.router, prefix="/api/tr", tags=["TR Temperature +"])
    app.include_router(temperature_negative.router, prefix="/api/tr", tags=["TR Temperature -"])
    app.include_router(sanificazione.router,        prefix="/api/tr", tags=["TR Sanificazione"])
    app.include_router(disinfestazione.router,      prefix="/api/tr", tags=["TR Disinfestazione"])
    app.include_router(haccp_auto.router,           prefix="/api/tr", tags=["TR HACCP Auto"])
    app.include_router(haccp_report.router,         prefix="/api/tr", tags=["TR HACCP Report"])
    app.include_router(report_haccp.router,         prefix="/api/tr", tags=["TR Report HACCP"])
    app.include_router(anomalie.router,             prefix="/api/tr", tags=["TR Anomalie"])
    app.include_router(chiusure.router,             prefix="/api/tr", tags=["TR Chiusure"])
    app.include_router(attrezzature.router,         prefix="/api/tr", tags=["TR Attrezzature"])
    app.include_router(costi_giornalieri.router,    prefix="/api/tr", tags=["TR Costi Giornalieri"])
    app.include_router(acquaviva.router,            prefix="/api/tr", tags=["TR Acquaviva"])
    app.include_router(colazione.router,            prefix="/api/tr", tags=["TR Colazione"])
    app.include_router(ricezione_merce.router,      prefix="/api/tr", tags=["TR Ricezione Merce"])
    app.include_router(sconti_merce.router,         prefix="/api/tr", tags=["TR Sconti Merce"])
    app.include_router(vendita_banco.router,        prefix="/api/tr", tags=["TR Vendita Banco"])
    app.include_router(tr_fornitori.router,         prefix="/api/tr", tags=["TR Fornitori"])
    app.include_router(tr_ricette.router,           prefix="/api/tr", tags=["TR Ricette"])
    app.include_router(tr_prodotti.router,          prefix="/api/tr", tags=["TR Prodotti Vendita"])
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Tracciabilita non caricata: {e}")
# tracciabilita rimosso (Blocco J1)
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
app.include_router(suppliers_router, prefix="/api/fornitori", tags=["Fornitori"])  # alias canonico
app.include_router(cash.router, prefix="/api/cash", tags=["Cash Register"])
app.include_router(chart_of_accounts.router, prefix="/api/chart-of-accounts", tags=["Chart of Accounts"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(cash_register.router, prefix="/api/cash-register", tags=["Cash Register Operations"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(settings_base.router, prefix="/api/settings", tags=["Settings Base"])
app.include_router(config.router, prefix="/api/config", tags=["Config"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(ocr_assegni.router, prefix="/api/ocr-assegni", tags=["OCR Assegni"])
app.include_router(portal.router, prefix="/api/portal", tags=["Portal"])
app.include_router(finanziaria.router, prefix="/api/finanziaria", tags=["Finanziaria"])
app.include_router(comparatore.router, prefix="/api/comparatore", tags=["Comparatore Prezzi"])
app.include_router(gestione_riservata.router, prefix="/api/gestione-riservata", tags=["Gestione Riservata"])
app.include_router(commercialista.router, prefix="/api/commercialista", tags=["Commercialista"])
app.include_router(scadenze.router, prefix="/api/scadenze", tags=["Scadenze e Notifiche"])
app.include_router(riconciliazione_fornitori.router, prefix="/api/riconciliazione-fornitori", tags=["Riconciliazione Fornitori"])
app.include_router(pianificazione.router, prefix="/api/pianificazione", tags=["Pianificazione"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(verifica_coerenza.router, prefix="/api/verifica-coerenza", tags=["Verifica Coerenza Dati"])
app.include_router(documenti.router, prefix="/api/documenti", tags=["Gestione Documenti Email"])
app.include_router(operazioni_router, prefix="/api/operazioni-da-confermare", tags=["Operazioni da Confermare"])
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
from app.routers import chat_router
app.include_router(chat_router.router, prefix="/api", tags=["Chat Intelligente"])

# --- Schede Tecniche Prodotti ---
app.include_router(schede_tecniche.router, prefix="/api", tags=["Schede Tecniche Prodotti"])

# --- Auto-Riparazione rimossa (Blocco J1) ---
from app.routers import auto_repair
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

# --- Learning Machine Universale ---
from app.routers import learning_universal
app.include_router(learning_universal.router, prefix="/api/learning-universal", tags=["Learning Machine Universale"])

app.include_router(magazzino_avanzato.router, prefix="/api", tags=["Magazzino Avanzato"])
# odoo_integration rimosso (Blocco J1)
# app.include_router(odoo_integration.router, prefix="/api/odoo", tags=["Odoo Integration"])
app.include_router(accounting_engine.router, prefix="/api/accounting", tags=["Accounting Engine"])
app.include_router(contabilita_italiana.router, prefix="/api/contabilita", tags=["Contabilità Italiana"])

# --- Claude AI API (Assistente Contabile Intelligente) ---
# REMOVED: Claude AI - replaced by OpenClaw
# app.include_router(claude_api.router, prefix="/api/claude", tags=["Claude AI"])

# --- PayPal Statements (MSR/CSR) ---
from app.routers import paypal_statements
app.include_router(paypal_statements.router, prefix="/api/paypal-statements", tags=["PayPal Statements"])

# missing_endpoints, sync_router rimossi (Blocco J1)
# from app.routers import missing_endpoints
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

# force_sync rimosso (Blocco J1)
# from app.routers import force_sync
# app.include_router(force_sync.router, prefix="/api/force-sync", tags=["Force Sync"])

# missing_endpoints_fix rimosso (Blocco J1)
# from app.routers import missing_endpoints_fix
# app.include_router(missing_endpoints_fix.router, prefix="/api", tags=["Missing Endpoints Fix"])

# --- Dati Provvisori (NUOVA LOGICA WORKFLOW) ---
from app.routers import dati_provvisori
app.include_router(dati_provvisori.router, prefix="/api", tags=["Dati Provvisori"])

# batch_reprocessing
from app.routers import batch_reprocessing
app.include_router(batch_reprocessing.router, prefix="/api", tags=["Batch Reprocessing"])


# --- POS Corrispettivi Check (Verifica coerenza POS/Corrispettivi XML) ---
from app.routers import pos_corrispettivi_check
app.include_router(pos_corrispettivi_check.router, prefix="/api", tags=["POS Corrispettivi Check"])


# --- Distinte BPM (Import distinte stipendi da banca BPM) ---
from app.routers import distinte_bpm
app.include_router(distinte_bpm.router, prefix="/api/paghe", tags=["Distinte BPM"])

# --- Veicoli Noleggio ---
from app.routers import veicoli
app.include_router(veicoli.router, tags=["Veicoli Noleggio"])

# --- Cucina: Ricette, Food Cost, Prodotti Vendita, Ordini Fornitori ---
from app.routers.cucina import ricette as r_cu_ricette_mod
from app.routers.cucina import food_cost as r_cu_foodcost_mod
from app.routers.cucina import prodotti_vendita as r_cu_prodotti_mod
from app.routers.cucina import ordini_fornitori as r_cu_ord_mod
app.include_router(r_cu_ricette_mod.router,    prefix="/api", tags=["Cucina Ricette"])
app.include_router(r_cu_foodcost_mod.router,   prefix="/api", tags=["Cucina Food Cost"])
app.include_router(r_cu_prodotti_mod.router,   prefix="/api", tags=["Cucina Prodotti Vendita"])
app.include_router(r_cu_ord_mod.router,        prefix="/api", tags=["Cucina Ordini Fornitori"])


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/")
async def root(request: Request):
    """Serve il frontend React o health check JSON in base al client."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        # Richiesta browser: serve index.html del frontend
        _idx = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "index.html")
        if os.path.isfile(_idx):
            return FileResponse(_idx)
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


# ─── Tracciabilità Module (mini-sito interno) ─────────────────────────────────
try:
    from app.routers.tracciabilita.lotti import router as r_tr_lotti
    from app.routers.tracciabilita.lotti_fornitori import router as r_tr_lotti_forn
    from app.routers.tracciabilita.lotti_produzione import router as r_tr_lotti_prod
    from app.routers.tracciabilita.produzioni import router as r_tr_produzioni
    from app.routers.tracciabilita.temperature_negative import router as r_tr_temp_neg
    from app.routers.tracciabilita.temperature_positive import router as r_tr_temp_pos
    from app.routers.tracciabilita.sanificazione import router as r_tr_san
    from app.routers.tracciabilita.disinfestazione import router as r_tr_dis
    from app.routers.tracciabilita.haccp_auto import router as r_tr_haccp_auto
    from app.routers.tracciabilita.haccp_report import router as r_tr_haccp_rep
    from app.routers.tracciabilita.report_haccp import router as r_tr_report
    from app.routers.tracciabilita.anomalie import router as r_tr_anomalie
    from app.routers.tracciabilita.chiusure import router as r_tr_chiusure
    from app.routers.tracciabilita.attrezzature import router as r_tr_attr
    from app.routers.tracciabilita.costi_giornalieri import router as r_tr_costi
    from app.routers.tracciabilita.acquaviva import router as r_tr_acquaviva
    from app.routers.tracciabilita.colazione import router as r_tr_colazione
    from app.routers.tracciabilita.vendita_banco import router as r_tr_vendita
    from app.routers.tracciabilita.fornitori import router as r_tr_fornitori_tr
    from app.routers.tracciabilita.sconti_merce import router as r_tr_sconti
    from app.routers.tracciabilita.ricezione_merce import router as r_tr_ricezione
    from app.routers.tracciabilita.stampa import router as r_tr_stampa
    from app.routers.tracciabilita.manuale_haccp import router as r_tr_manuale
    from app.routers.tracciabilita.haccp_manuale_auto import router as r_tr_haccp_man
    # Router aggiuntivi (19 router copiati dal repo originale)
    from app.routers.tracciabilita.ricette import router as r_tr_ricette
    from app.routers.tracciabilita.backup import router as r_tr_backup
    from app.routers.tracciabilita.controllo_olio import router as r_tr_olio
    from app.routers.tracciabilita.prodotti_vendita import router as r_tr_prodotti_v
    from app.routers.tracciabilita.food_cost import router as r_tr_fc
    from app.routers.tracciabilita.normalizzazione import router as r_tr_norm
    from app.routers.tracciabilita.materie_prime import router as r_tr_materie
    from app.routers.tracciabilita.ordini_fornitori import router as r_tr_ord_forn
    from app.routers.tracciabilita.temperature_cottura import router as r_tr_temp_cott
    from app.routers.tracciabilita.fatture import router as r_tr_fatture
    from app.routers.tracciabilita.supervisor_operativo import router as r_tr_supervisor
    from app.routers.tracciabilita.utils import router as r_tr_utils
    from app.routers.tracciabilita.codici_cun import router as r_tr_codici_cun
    from app.routers.tracciabilita.pec_import import router as r_tr_pec
    from app.routers.tracciabilita.mepa import router as r_tr_mepa
    from app.routers.tracciabilita.saima import router as r_tr_saima
    from app.routers.tracciabilita.saima_ricettari import router as r_tr_saima_ric
    from app.routers.tracciabilita.pipeline import router as r_tr_pipeline
    _TR_ROUTERS = [
        r_tr_lotti, r_tr_lotti_forn, r_tr_lotti_prod, r_tr_produzioni,
        r_tr_temp_neg, r_tr_temp_pos, r_tr_san, r_tr_dis,
        r_tr_haccp_auto, r_tr_haccp_rep, r_tr_report, r_tr_anomalie,
        r_tr_chiusure, r_tr_attr, r_tr_costi, r_tr_acquaviva, r_tr_colazione,
        r_tr_vendita, r_tr_fornitori_tr, r_tr_sconti, r_tr_ricezione,
        r_tr_stampa, r_tr_manuale, r_tr_haccp_man,
        r_tr_ricette, r_tr_backup, r_tr_olio, r_tr_prodotti_v,
        r_tr_fc, r_tr_norm, r_tr_materie, r_tr_ord_forn, r_tr_temp_cott,
        r_tr_fatture, r_tr_supervisor, r_tr_utils, r_tr_codici_cun,
        r_tr_pec, r_tr_mepa, r_tr_saima, r_tr_saima_ric, r_tr_pipeline,
    ]
    for _r in _TR_ROUTERS:
        app.include_router(_r, prefix="/api/tr")
    logger.info("✅ Modulo Tracciabilità caricato (%d router)", len(_TR_ROUTERS))
except Exception as _e:
    logger.warning("⚠️ Tracciabilità: alcuni router non caricati — %s", str(_e)[:120])

# Mount static files for downloads
docs_path = "./docs"
os.makedirs(docs_path, exist_ok=True)
app.mount("/api/download", StaticFiles(directory=docs_path), name="download")

# Mount mini-sito Tracciabilità (build React statica) sotto /api/tracciabilita
_tracciabilita_static = os.path.join(os.path.dirname(__file__), "static", "tracciabilita")
if os.path.isdir(_tracciabilita_static):
    app.mount("/api/tracciabilita", StaticFiles(directory=_tracciabilita_static, html=True), name="tracciabilita")
    logger.info("✅ Mini-sito Tracciabilità montato su /api/tracciabilita")

# =============================================================================
# SPA FRONTEND SERVING
# Serve il frontend React per tutti i path non-API.
# Necessario per il routing lato client (React Router) in produzione:
# ogni refresh/navigazione diretta a /dipendenti, /fatture, ecc.
# riceve index.html e React Router gestisce il routing client-side.
# =============================================================================
_FRONTEND_DIST = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.isdir(_FRONTEND_DIST):
    # Serve file statici (JS, CSS, assets) direttamente
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str) -> FileResponse:
        """
        Catch-all handler: serve index.html per qualsiasi route non-API.
        Permette a React Router di gestire la navigazione client-side.
        """
        # Le route /api/ non esistenti restituiscono 404 JSON (non index.html)
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        # Prova a servire un file statico esistente (favicon, logo, ecc.)
        # Protezione path traversal: normalizza il path
        safe_path = os.path.normpath(full_path).lstrip("/\\")
        static_file = os.path.join(_FRONTEND_DIST, safe_path)
        if full_path and os.path.isfile(static_file) and static_file.startswith(_FRONTEND_DIST):
            return FileResponse(static_file)
        # Per tutte le altre route, serve index.html (SPA fallback)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

    logger.info("✅ Frontend React montato da %s (SPA routing attivo)", _FRONTEND_DIST)
else:
    logger.warning("⚠️ Frontend dist non trovato in %s — SPA routing non attivo", _FRONTEND_DIST)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD
    )
