"""
Router Registry — Ceraldi ERP
==============================
Registrazione centralizzata di tutti i router FastAPI.
Organizzato per modulo funzionale.
"""
import logging
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_all_routers(app: FastAPI) -> None:
    """Registra tutti i router nell'applicazione FastAPI."""
    
    _register_auth(app)
    _register_f24(app)
    _register_accounting(app)
    _register_bank(app)
    _register_warehouse(app)
    _register_invoices(app)
    _register_employees(app)
    _register_reports(app)
    _register_core(app)
    _register_email(app)
    _register_noleggio(app)
    _register_ai(app)
    _register_tracciabilita(app)
    
    logger.info("✅ Tutti i router registrati")


# ─── Auth & Public ──────────────────────────────────────────────────────────
def _register_auth(app: FastAPI):
    from app.routers import auth, public_api, google_auth, openclaw
    from app.routers.agenti import router as r_agenti
    from app.routers.erp_bridge import router as erp_bridge_router
    
    app.include_router(public_api.router, prefix="/api", tags=["Public API"])
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(google_auth.router, prefix="/api", tags=["Google OAuth"])
    app.include_router(openclaw.router, prefix="/api", tags=["OpenClaw AI Assistant"])
    app.include_router(r_agenti, prefix="/api", tags=["Agenti AI"])
    app.include_router(erp_bridge_router)


# ─── F24 Module ─────────────────────────────────────────────────────────────
def _register_f24(app: FastAPI):
    from app.routers.f24 import f24_main, f24_riconciliazione, f24_public, quietanze, f24_gestione_avanzata, f24_notifiche
    from app.routers import f24_email_settings, codici_tributari
    from app.routers.bank import riconciliazione_f24_banca
    
    app.include_router(f24_main.router, prefix="/api/f24", tags=["F24"])
    app.include_router(f24_riconciliazione.router, prefix="/api/f24-riconciliazione", tags=["F24 Riconciliazione"])
    app.include_router(f24_public.router, prefix="/api/f24-public", tags=["F24 Public"])
    app.include_router(quietanze.router, prefix="/api/quietanze-f24", tags=["Quietanze F24"])
    app.include_router(f24_notifiche.router, prefix="/api/f24-notifiche", tags=["F24 Notifiche"])
    app.include_router(f24_gestione_avanzata.router, prefix="/api/f24-avanzato", tags=["F24 Avanzato"])
    app.include_router(f24_email_settings.router, prefix="/api/f24-email-settings", tags=["F24 Email"])
    app.include_router(codici_tributari.router, prefix="/api/codici-tributari", tags=["Codici Tributari"])
    app.include_router(riconciliazione_f24_banca.router, prefix="/api/f24-riconciliazione", tags=["Riconciliazione F24 Banca"])


# ─── Accounting Module ──────────────────────────────────────────────────────
def _register_accounting(app: FastAPI):
    from app.routers.accounting import (
        accounting_main, accounting_extended, accounting_engine_api,
        prima_nota_automation, prima_nota_salari,
        piano_conti, bilancio, centri_costo, contabilita_avanzata,
        regole_categorizzazione, iva_calcolo, liquidazione_iva,
        riconciliazione_automatica, contabilita_gestionale
    )
    from app.routers.prima_nota_module import router as prima_nota_router
    from app.routers import accounting_engine, contabilita_italiana, fiscalita_italiana
    from app.routers import riconciliazione_intelligente_api, batch_operations
    
    app.include_router(accounting_main.router, prefix="/api/accounting", tags=["Accounting"])
    app.include_router(accounting_extended.router, prefix="/api/accounting", tags=["Accounting Extended"])
    app.include_router(accounting_engine_api.router, prefix="/api/accounting-engine", tags=["Accounting Engine"])
    app.include_router(prima_nota_router, prefix="/api/prima-nota", tags=["Prima Nota"])
    app.include_router(prima_nota_automation.router, prefix="/api/prima-nota-auto", tags=["Prima Nota Auto"])
    app.include_router(prima_nota_salari.router, prefix="/api/prima-nota-salari", tags=["Prima Nota Salari"])
    app.include_router(piano_conti.router, prefix="/api/piano-conti", tags=["Piano dei Conti"])
    app.include_router(bilancio.router, prefix="/api/bilancio", tags=["Bilancio"])
    app.include_router(contabilita_gestionale.router, tags=["Contabilità Gestionale"])
    app.include_router(centri_costo.router, prefix="/api/centri-costo", tags=["Centri di Costo"])
    app.include_router(contabilita_avanzata.router, prefix="/api/contabilita", tags=["Contabilita Avanzata"])
    app.include_router(regole_categorizzazione.router, prefix="/api/regole", tags=["Regole"])
    app.include_router(iva_calcolo.router, prefix="/api/iva", tags=["IVA"])
    app.include_router(liquidazione_iva.router, prefix="/api", tags=["Liquidazione IVA"])
    app.include_router(riconciliazione_automatica.router, prefix="/api/riconciliazione-auto", tags=["Riconciliazione Auto"])
    app.include_router(riconciliazione_intelligente_api.router, prefix="/api/riconciliazione-intelligente", tags=["Riconciliazione Intelligente"])
    app.include_router(batch_operations.router, prefix="/api/batch", tags=["Batch Operations"])
    app.include_router(accounting_engine.router, prefix="/api/accounting", tags=["Accounting Engine"])
    app.include_router(contabilita_italiana.router, prefix="/api/contabilita", tags=["Contabilità Italiana"])
    app.include_router(fiscalita_italiana.router, prefix="/api/fiscalita", tags=["Fiscalità Italiana"])


# ─── Bank Module ────────────────────────────────────────────────────────────
def _register_bank(app: FastAPI):
    from app.routers.bank import (
        bank_main, bank_reconciliation, bank_statement_import,
        bank_statement_parser, estratto_conto, assegni, pos_accredito,
        bank_statement_bulk_import, assegni_learning
    )
    from app.routers.bonifici_module import router as archivio_bonifici_router
    from app.routers.bonifici_module import associazioni as bonifici_associazioni
    from app.routers import paypal_statements, distinte_bpm
    
    app.include_router(bank_main.router, prefix="/api/bank", tags=["Bank"])
    app.include_router(bank_reconciliation.router, prefix="/api/bank-reconciliation", tags=["Bank Reconciliation"])
    app.include_router(bank_statement_import.router, prefix="/api/bank-statement", tags=["Bank Statement"])
    app.include_router(bank_statement_parser.router, prefix="/api/estratto-conto", tags=["Estratto Conto Parser"])
    app.include_router(bank_statement_bulk_import.router, prefix="/api/bank-statement-bulk", tags=["Bank Bulk"])
    app.include_router(estratto_conto.router, prefix="/api/estratto-conto-movimenti", tags=["Estratto Conto"])
    app.include_router(archivio_bonifici_router, prefix="/api/archivio-bonifici", tags=["Archivio Bonifici"])
    app.include_router(assegni.router, prefix="/api/assegni", tags=["Assegni"])
    app.include_router(assegni_learning.router, prefix="/api/assegni/learning", tags=["Assegni Learning"])
    app.include_router(pos_accredito.router, prefix="/api/pos-accredito", tags=["POS Accredito"])
    app.include_router(paypal_statements.router, prefix="/api/paypal-statements", tags=["PayPal"])
    app.include_router(bonifici_associazioni.router, prefix="/api", tags=["Bonifici Associazioni"])
    app.include_router(distinte_bpm.router, prefix="/api/paghe", tags=["Distinte BPM"])


# ─── Warehouse Module ──────────────────────────────────────────────────────
def _register_warehouse(app: FastAPI):
    from app.routers.warehouse import warehouse_main, magazzino, magazzino_products, products, products_catalog, dizionario_articoli
    from app.routers import magazzino_avanzato, dizionario_prodotti, inventario
    
    app.include_router(warehouse_main.router, prefix="/api/warehouse", tags=["Warehouse"])
    app.include_router(magazzino.router, prefix="/api/magazzino", tags=["Magazzino"])
    app.include_router(magazzino_products.router, prefix="/api/magazzino", tags=["Magazzino Products"])
    app.include_router(products.router, prefix="/api/products", tags=["Products"])
    app.include_router(products_catalog.router, prefix="/api/products", tags=["Products Catalog"])
    app.include_router(dizionario_articoli.router, prefix="/api/dizionario-articoli", tags=["Dizionario Articoli"])
    app.include_router(magazzino_avanzato.router, prefix="/api", tags=["Magazzino Avanzato"])
    app.include_router(dizionario_prodotti.router, prefix="/api/dizionario-prodotti", tags=["Dizionario Prodotti"])
    app.include_router(inventario.router, prefix="/api", tags=["Inventario"])


# ─── Invoices Module ───────────────────────────────────────────────────────
def _register_invoices(app: FastAPI):
    from app.routers.invoices import invoices_main, invoices_emesse, invoices_export, fatture_upload, corrispettivi
    from app.routers.fatture_module import router as fatture_ricevute_router
    from app.routers.fatture_module.api_tracciabilita import router as r_api_tracciabilita
    from app.routers import invoicetronic
    
    app.include_router(invoices_emesse.router, prefix="/api/invoices/emesse", tags=["Invoices Emesse"])
    app.include_router(invoices_main.router, prefix="/api/invoices", tags=["Invoices"])
    app.include_router(invoices_export.router, prefix="/api/invoices", tags=["Invoices Export"])
    app.include_router(fatture_upload.router, prefix="/api/fatture", tags=["Fatture Upload"])
    app.include_router(fatture_ricevute_router, prefix="/api/fatture-ricevute", tags=["Fatture Ricevute"])
    app.include_router(r_api_tracciabilita, prefix="/api", tags=["API Tracciabilita"])
    app.include_router(corrispettivi.router, prefix="/api/corrispettivi", tags=["Corrispettivi"])
    app.include_router(invoicetronic.router, tags=["InvoiceTronic SDI"])


# ─── Employees Module ──────────────────────────────────────────────────────
def _register_employees(app: FastAPI):
    from app.routers.employees import dipendenti, employees_payroll, employee_contracts, buste_paga, shifts, staff, giustificativi
    from app.routers import payroll, cedolini, cedolini_riconciliazione, tfr, attendance, dimissioni
    from app.routers import salari_unificati_v2, bonifici_stipendi, libro_unico_parser, f24_parser
    from app.routers.attendance_module import presenze as attendance_presenze
    
    app.include_router(dipendenti.router, prefix="/api/dipendenti", tags=["Dipendenti"])
    app.include_router(employees_payroll.router, prefix="/api/employees", tags=["Employees Payroll"])
    app.include_router(employee_contracts.router, prefix="/api/contracts", tags=["Contracts"])
    app.include_router(buste_paga.router, prefix="/api", tags=["Buste Paga"])
    app.include_router(shifts.router, prefix="/api/shifts", tags=["Shifts"])
    app.include_router(staff.router, prefix="/api/staff", tags=["Staff"])
    app.include_router(giustificativi.router, prefix="/api/giustificativi", tags=["Giustificativi"])
    app.include_router(payroll.router, prefix="/api/payroll", tags=["Payroll"])
    app.include_router(cedolini.router, prefix="/api/cedolini", tags=["Cedolini"])
    app.include_router(cedolini_riconciliazione.router, prefix="/api/cedolini", tags=["Cedolini Riconciliazione"])
    app.include_router(tfr.router, prefix="/api/tfr", tags=["TFR"])
    app.include_router(attendance.router, prefix="/api/attendance", tags=["Attendance"])
    app.include_router(attendance_presenze.router, prefix="/api/attendance", tags=["Presenze"])
    app.include_router(salari_unificati_v2.router, prefix="/api/salari-v2", tags=["Salari V2"])
    app.include_router(bonifici_stipendi.router, tags=["Bonifici Stipendi"])
    app.include_router(dimissioni.router, prefix="/api/dimissioni", tags=["Dimissioni"])
    app.include_router(libro_unico_parser.router, prefix="/api/paghe", tags=["Libro Unico Parser"])
    app.include_router(f24_parser.router, prefix="/api/paghe", tags=["F24 Parser"])


# ─── Reports Module ────────────────────────────────────────────────────────
def _register_reports(app: FastAPI):
    from app.routers.reports import report_pdf, exports, simple_exports, analytics, dashboard
    
    app.include_router(report_pdf.router, prefix="/api/report-pdf", tags=["Report PDF"])
    app.include_router(exports.router, prefix="/api/exports", tags=["Exports"])
    app.include_router(simple_exports.router, prefix="/api/exports", tags=["Simple Exports"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])


# ─── Core Routers ──────────────────────────────────────────────────────────
def _register_core(app: FastAPI):
    from app.routers import (
        cash, chart_of_accounts, notifications, cash_register,
        settings as settings_base, config, search, ocr_assegni, portal,
        finanziaria, comparatore, gestione_riservata, commercialista, scadenze,
        riconciliazione_fornitori, pianificazione, admin, verifica_coerenza,
        documenti, cespiti, scadenzario_fornitori, controllo_gestione,
        indici_bilancio, chiusura_esercizio, gestione_iva_speciale,
        configurazioni, alerts, import_templates, manutenzione,
        todo, mutui, mutui_parser, import_manuale, auto_repair,
        inserimento_rapido, settings_router, dati_provvisori, 
        batch_reprocessing, pos_corrispettivi_check, enhanced_parser,
        chat_router, learning_universal, schede_tecniche
    )
    from app.routers.suppliers_module import router as suppliers_router
    from app.routers.operazioni_module import router as operazioni_router
    from app.routers import openapi_imprese, openapi_it, openapi_automotive
    from app.routers import websocket_realtime, learning_machine, learning_machine_cdc, fornitori_learning
    from app.routers import sync_relazionale, pagopa, inps_documenti, adr
    
    app.include_router(suppliers_router, prefix="/api/suppliers", tags=["Suppliers"])
    app.include_router(suppliers_router, prefix="/api/fornitori", tags=["Fornitori"])
    app.include_router(cash.router, prefix="/api/cash", tags=["Cash"])
    app.include_router(chart_of_accounts.router, prefix="/api/chart-of-accounts", tags=["Chart of Accounts"])
    app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
    app.include_router(cash_register.router, prefix="/api/cash-register", tags=["Cash Register"])
    app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(settings_base.router, prefix="/api/settings", tags=["Settings Base"])
    app.include_router(config.router, prefix="/api/config", tags=["Config"])
    app.include_router(configurazioni.router, prefix="/api/config", tags=["Configurazioni"])
    app.include_router(search.router, prefix="/api/search", tags=["Search"])
    app.include_router(ocr_assegni.router, prefix="/api/ocr-assegni", tags=["OCR Assegni"])
    app.include_router(portal.router, prefix="/api/portal", tags=["Portal"])
    app.include_router(finanziaria.router, prefix="/api/finanziaria", tags=["Finanziaria"])
    app.include_router(comparatore.router, prefix="/api/comparatore", tags=["Comparatore"])
    app.include_router(gestione_riservata.router, prefix="/api/gestione-riservata", tags=["Gestione Riservata"])
    app.include_router(commercialista.router, prefix="/api/commercialista", tags=["Commercialista"])
    app.include_router(scadenze.router, prefix="/api/scadenze", tags=["Scadenze"])
    app.include_router(riconciliazione_fornitori.router, prefix="/api/riconciliazione-fornitori", tags=["Riconciliazione Fornitori"])
    app.include_router(pianificazione.router, prefix="/api/pianificazione", tags=["Pianificazione"])
    app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
    app.include_router(verifica_coerenza.router, prefix="/api/verifica-coerenza", tags=["Verifica Coerenza"])
    app.include_router(documenti.router, prefix="/api/documenti", tags=["Documenti"])
    app.include_router(operazioni_router, prefix="/api/operazioni-da-confermare", tags=["Operazioni"])
    app.include_router(cespiti.router, prefix="/api/cespiti", tags=["Cespiti"])
    app.include_router(scadenzario_fornitori.router, prefix="/api/scadenzario-fornitori", tags=["Scadenzario"])
    app.include_router(controllo_gestione.router, prefix="/api/controllo-gestione", tags=["Controllo Gestione"])
    app.include_router(indici_bilancio.router, prefix="/api/indici-bilancio", tags=["Indici Bilancio"])
    app.include_router(chiusura_esercizio.router, prefix="/api/chiusura-esercizio", tags=["Chiusura Esercizio"])
    app.include_router(gestione_iva_speciale.router, prefix="/api/iva-speciale", tags=["IVA Speciale"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["Alert"])
    app.include_router(import_templates.router, prefix="/api/import-templates", tags=["Import Templates"])
    app.include_router(manutenzione.router, prefix="/api/manutenzione", tags=["Manutenzione"])
    app.include_router(todo.router, prefix="/api/todo", tags=["To-Do"])
    app.include_router(mutui.router, prefix="/api/mutui", tags=["Mutui"])
    app.include_router(mutui_parser.router, prefix="/api/mutui", tags=["Mutui Parser"])
    app.include_router(import_manuale.router, prefix="/api/import-manuale", tags=["Import Manuale"])
    app.include_router(auto_repair.router, prefix="/api", tags=["Auto Riparazione"])
    app.include_router(inserimento_rapido.router, prefix="/api", tags=["Inserimento Rapido"])
    app.include_router(dati_provvisori.router, prefix="/api", tags=["Dati Provvisori"])
    app.include_router(batch_reprocessing.router, prefix="/api", tags=["Batch Reprocessing"])
    app.include_router(pos_corrispettivi_check.router, prefix="/api", tags=["POS Check"])
    app.include_router(enhanced_parser.router, prefix="/api", tags=["Enhanced Parser"])
    app.include_router(chat_router.router, prefix="/api", tags=["Chat"])
    app.include_router(schede_tecniche.router, prefix="/api", tags=["Schede Tecniche"])
    app.include_router(learning_universal.router, prefix="/api/learning-universal", tags=["Learning Universal"])
    app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(websocket_realtime.router, prefix="/api", tags=["WebSocket"])
    app.include_router(learning_machine.router, prefix="/api/learning-machine", tags=["Learning Machine"])
    app.include_router(learning_machine_cdc.router, prefix="/api", tags=["Learning CDC"])
    app.include_router(fornitori_learning.router, prefix="/api", tags=["Fornitori Learning"])
    app.include_router(openapi_imprese.router, prefix="/api", tags=["OpenAPI Imprese"])
    app.include_router(openapi_it.router, prefix="/api/openapi", tags=["OpenAPI.it"])
    app.include_router(openapi_automotive.router, prefix="/api", tags=["OpenAPI Automotive"])
    app.include_router(sync_relazionale.router, prefix="/api", tags=["Sync Relazionale"])
    app.include_router(pagopa.router, tags=["PagoPA"])
    app.include_router(inps_documenti.router, prefix="/api/inps", tags=["INPS"])
    app.include_router(adr.router, prefix="/api/adr", tags=["ADR"])
    
    # Multi-Pagamento Fatture
    from app.routers import multi_pagamento
    app.include_router(multi_pagamento.router, prefix="/api/pagamenti", tags=["Multi-Pagamento"])


# ─── Email Module ──────────────────────────────────────────────────────────
def _register_email(app: FastAPI):
    from app.routers import (
        email_scanner, email_download, email_reconciliation, email_mongodb,
        documenti_non_associati, documenti_intelligenti, document_ai, ai_parser, upload_ai
    )
    
    app.include_router(email_scanner.router, tags=["Email Scanner"])
    app.include_router(email_download.router, prefix="/api", tags=["Email Download"])
    app.include_router(email_reconciliation.router, tags=["Email Riconciliazione"])
    app.include_router(email_mongodb.router, prefix="/api", tags=["Email MongoDB"])
    app.include_router(documenti_non_associati.router, prefix="/api", tags=["Documenti Non Associati"])
    app.include_router(documenti_intelligenti.router, prefix="/api/documenti-smart", tags=["Documenti Intelligenti"])
    app.include_router(document_ai.router, prefix="/api/document-ai", tags=["Document AI"])
    app.include_router(ai_parser.router, prefix="/api/ai-parser", tags=["AI Parser"])
    app.include_router(upload_ai.router, prefix="/api/upload-ai", tags=["Upload AI"])


# ─── Noleggio & Verbali Module ─────────────────────────────────────────────
def _register_noleggio(app: FastAPI):
    from app.routers import noleggio, verbali_noleggio, verbali_noleggio_api, verbali_riconciliazione, veicoli
    
    app.include_router(noleggio.router, prefix="/api/noleggio", tags=["Noleggio Auto"])
    app.include_router(verbali_noleggio.router, tags=["Verbali Noleggio"])
    app.include_router(verbali_noleggio_api.router, prefix="/api/verbali-noleggio", tags=["Verbali API"])
    app.include_router(verbali_riconciliazione.router, prefix="/api/verbali-riconciliazione", tags=["Verbali Riconciliazione"])
    app.include_router(veicoli.router, tags=["Veicoli"])


# ─── AI Module ─────────────────────────────────────────────────────────────
def _register_ai(app: FastAPI):
    """Registra router AI/ML (opzionale - non blocca se fallisce)."""
    pass  # AI routers already registered in _register_email


# ─── Tracciabilità Module ──────────────────────────────────────────────────
def _register_tracciabilita(app: FastAPI):
    """Registra i 40+ router del modulo tracciabilità HACCP."""
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
        
        _all = [
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
        for r in _all:
            app.include_router(r, prefix="/api/tr")
        logger.info("✅ Tracciabilità: %d router caricati", len(_all))
    except Exception as e:
        logger.warning("⚠️ Tracciabilità: %s", str(e)[:120])
