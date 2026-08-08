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

    # Sistema relazionale (Chat 9e)
    try:
        from app.routers.partite_aperte_api import router as partite_router
        from app.routers.riconciliazione_stats_api import router as ric_stats_router
        app.include_router(partite_router, prefix="/api", tags=["Partite Aperte"])
        app.include_router(ric_stats_router, prefix="/api", tags=["Riconciliazione Stats"])
    except Exception as e:
        logger.warning(f"Router relazionali non registrati: {e}")

    logger.info("✅ Tutti i router registrati")


# ─── Auth & Public ───────────────────────────────────────────────────────────
def _register_auth(app: FastAPI):
    from app.routers import auth, mfa, public_api, pin_login
    from app.routers.erp_bridge import router as erp_bridge_router
    from app.routers.legal_pages import router as legal_router

    app.include_router(public_api.router, prefix="/api", tags=["Public API"])
    # auth.router already carries an internal prefix="/api" and its routes are
    # "/auth/...", so it must be included WITHOUT an extra prefix — otherwise the
    # paths double up to "/api/auth/api/auth/verify" and the frontend's
    # "/api/auth/verify" / "/api/auth/login" calls 404 (logging users out on
    # refresh). pin_login.router has no internal prefix, so it keeps "/api/auth".
    app.include_router(auth.router, tags=["Authentication"])
    app.include_router(pin_login.router, prefix="/api/auth", tags=["PIN Login"])
    app.include_router(mfa.router, prefix="/api/auth", tags=["MFA"])
    # ERP Bridge: ponte inbound dall'app esterna collegata allo stesso DB
    # (ceraldiapp.it) che invia al gestionale le fatture importate dalla PEC.
    # NON rimuovere: endpoint chiamato dall'altra app.
    # Il router ha già prefix interno "/api/erp/ponte", quindi NO prefix qui.
    app.include_router(erp_bridge_router)
    app.include_router(legal_router, tags=["Legal"])

    from app.routers.whatsapp_webhook import router as whatsapp_router
    app.include_router(whatsapp_router, prefix="/api/whatsapp", tags=["WhatsApp"])


# ─── F24 Module ──────────────────────────────────────────────────────────────
# Rimossi (audit lug 2026, zero chiamanti verificati due volte): quietanze,
# f24_gestione_avanzata, f24_notifiche, codici_tributari.
def _register_f24(app: FastAPI):
    from app.routers.f24 import f24_main, f24_riconciliazione, f24_public
    from app.routers import f24_email_settings, f24_analisi
    from app.routers.bank import riconciliazione_f24_banca

    app.include_router(f24_main.router, prefix="/api/f24", tags=["F24"])
    app.include_router(f24_analisi.router, prefix="/api/f24-analisi", tags=["F24 Analisi"])
    app.include_router(f24_riconciliazione.router, prefix="/api/f24-riconciliazione", tags=["F24 Riconciliazione"])
    app.include_router(f24_public.router, prefix="/api/f24-public", tags=["F24 Public"])
    app.include_router(f24_email_settings.router, prefix="/api/f24-email-settings", tags=["F24 Email"])
    app.include_router(riconciliazione_f24_banca.router, prefix="/api/f24-riconciliazione", tags=["Riconciliazione F24 Banca"])

    # Email F24 (scarica/processa allegati F24 da email)
    try:
        from app.routers.f24.email_f24 import router as email_f24_router
        app.include_router(email_f24_router, prefix="/api/f24-email", tags=["F24 Email Download"])
    except Exception as e:
        logger.warning(f"Router email_f24 non registrato: {e}")


# ─── Accounting Module ───────────────────────────────────────────────────────
# Rimossi (audit lug 2026, zero chiamanti verificati due volte):
# accounting_main, accounting_extended, accounting_engine (router),
# accounting_engine_api, prima_nota_automation, prima_nota_salari_v2,
# iva_calcolo, liquidazione_iva (router; il service omonimo resta vivo).
def _register_accounting(app: FastAPI):
    from app.routers.accounting import (
        prima_nota_salari,
        piano_conti, bilancio, centri_costo, contabilita_avanzata,
        regole_categorizzazione, contabilita_gestionale
    )
    from app.routers.prima_nota_module import router as prima_nota_router
    from app.routers import contabilita_italiana, fiscalita_italiana, finanziamenti_soci

    app.include_router(prima_nota_router, prefix="/api/prima-nota", tags=["Prima Nota"])
    app.include_router(prima_nota_salari.router, prefix="/api/prima-nota-salari", tags=["Prima Nota Salari"])
    from app.routers import pagamenti_buoni
    app.include_router(pagamenti_buoni.router, prefix="/api/pagamenti-buoni", tags=["Pagamenti buoni"])
    app.include_router(finanziamenti_soci.router, prefix="/api/finanziamenti-soci", tags=["Finanziamento Soci"])
    app.include_router(piano_conti.router, prefix="/api/piano-conti", tags=["Piano dei Conti"])
    app.include_router(bilancio.router, prefix="/api/bilancio", tags=["Bilancio"])
    app.include_router(contabilita_gestionale.router, prefix="/api/contabilita-gestionale", tags=["Contabilità Gestionale"])
    app.include_router(centri_costo.router, prefix="/api/centri-costo", tags=["Centri di Costo"])
    app.include_router(contabilita_avanzata.router, prefix="/api/contabilita", tags=["Contabilita Avanzata"])
    app.include_router(regole_categorizzazione.router, prefix="/api/regole", tags=["Regole"])
    # batch_operations: smontato (audit 14/07/2026, piano residuo op.2) — zero
    # chiamanti verificati (frontend/scheduler/interno/test). File conservato in
    # git: tests/test_p0_02_auto_riconcilia.py importa ancora l'helper puro
    # filtro_uscite_da_riconciliare direttamente dal modulo.
    app.include_router(contabilita_italiana.router, prefix="/api/contabilita", tags=["Contabilità Italiana"])
    app.include_router(fiscalita_italiana.router, prefix="/api/fiscalita", tags=["Fiscalità Italiana"])


# ─── Bank Module ─────────────────────────────────────────────────────────────
def _register_bank(app: FastAPI):
    # Rimossi (audit lug 2026, zero chiamanti verificati due volte):
    # bank_reconciliation, bank_statement_parser, bank_statement_bulk_import.
    # Rimosso bank_main (audit lug 2026, item #27 memoria/endpoints/README.md):
    # router legacy MAI usato dal frontend (getBankStatements in api.js senza
    # chiamanti), con /reconcile e /assegni che erano stub letterali (return
    # {"message": "..."} senza toccare il DB) e uno schema dati (user_id,
    # amount, date) incompatibile con quello reale di estratto_conto_movimenti
    # (tipo/importo sempre positivo/data) — se mai invocato avrebbe scritto
    # documenti corrotti nella collezione condivisa con la riconciliazione vera.
    from app.routers.bank import (
        bank_statement_import,
        estratto_conto, assegni,
        assegni_learning
    )
    from app.routers.bonifici_module import router as archivio_bonifici_router
    from app.routers.bonifici_module import associazioni as bonifici_associazioni
    from app.routers import paypal_statements, nexi_carta, sumup

    app.include_router(bank_statement_import.router, prefix="/api/bank-statement", tags=["Bank Statement"])
    app.include_router(estratto_conto.router, prefix="/api/estratto-conto-movimenti", tags=["Estratto Conto"])
    app.include_router(archivio_bonifici_router, prefix="/api/archivio-bonifici", tags=["Archivio Bonifici"])
    app.include_router(assegni.router, prefix="/api/assegni", tags=["Assegni"])
    app.include_router(assegni_learning.router, prefix="/api/assegni/learning", tags=["Assegni Learning"])
    app.include_router(nexi_carta.router, prefix="/api/nexi", tags=["Carta Nexi"])
    app.include_router(sumup.router, prefix="/api/sumup", tags=["SumUp"])
    # pos_accredito (router HTTP): smontato (audit 14/07/2026, piano residuo
    # op.6) — sostituito funzionalmente da pos_corrispettivi_check, zero
    # chiamanti verificati. app/utils/pos_accredito.py (le funzioni di calcolo,
    # NON questo router) resta vivo: importato direttamente da
    # pos_corrispettivi_check.py, corrispettivi_service.py e corrispettivi.py.
    app.include_router(paypal_statements.router, prefix="/api/paypal-statements", tags=["PayPal"])

    # (paypal_api è registrato in _register_core con prefix="/api/paypal-api")
    app.include_router(bonifici_associazioni.router, prefix="/api", tags=["Bonifici Associazioni"])
    # distinte_bpm (router HTTP): smontato (audit 14/07/2026, piano residuo
    # op.5) — la route stessa non ha chiamanti, ma la funzione
    # import_distinte_bpm resta viva: importata e chiamata direttamente da
    # app/routers/documenti.py (pipeline di ingest documentale).

    # bonifici_import_unificato: wrapper per ImportUnificato UI.
    # Il router ha prefix interno "/archivio-bonifici/jobs", quindi prefix="/api" qui.
    from app.routers.bank.bonifici_import_unificato import router as bonifici_import_unif_router
    app.include_router(bonifici_import_unif_router, prefix="/api", tags=["Bonifici Import Unificato"])


# ─── Warehouse Module ────────────────────────────────────────────────────────
def _register_warehouse(app: FastAPI):
    # Giacenze/prodotti/inventario sono competenza dell'app HACCP (ceraldiapp.it):
    # qui resta SOLO il Dizionario Articoli, strumento contabile usato dalle
    # fatture. Le collection condivise non vengono toccate.
    from app.routers.warehouse import dizionario_articoli

    app.include_router(dizionario_articoli.router, prefix="/api/dizionario-articoli", tags=["Dizionario Articoli"])


# ─── Invoices Module ─────────────────────────────────────────────────────────
def _register_invoices(app: FastAPI):
    from app.routers.invoices import (
        invoices_main,
        invoices_emesse,
        fatture_upload,
        fatture_drive,
        corrispettivi,
    )
    from app.routers.fatture_module import router as fatture_ricevute_router
    from app.routers import fatture_estera_verifica

    app.include_router(invoices_emesse.router, prefix="/api/invoices/emesse", tags=["Invoices Emesse"])
    app.include_router(invoices_main.router, prefix="/api/invoices", tags=["Invoices"])
    app.include_router(fatture_upload.router, prefix="/api/fatture", tags=["Fatture Upload"])
    app.include_router(fatture_drive.router, prefix="/api/fatture", tags=["Fatture Drive"])
    app.include_router(fatture_ricevute_router, prefix="/api/fatture-ricevute", tags=["Fatture Ricevute"])
    app.include_router(corrispettivi.router, prefix="/api/corrispettivi", tags=["Corrispettivi"])
    app.include_router(fatture_estera_verifica.router, prefix="/api/fatture-estere", tags=["Fatture Estere Verifica"])



# ─── Employees Module (ridotto) ──────────────────────────────────────────────
# La gestione HR è stata spostata nell'app esterna AppDipendenti (stesso DB).
# Restano solo i router usati da flussi NON-HR di questo gestionale:
#   - dipendenti: anagrafica in lettura (verbali noleggio, inserimento rapido, portale)
#   - tfr: riepilogo fondo TFR mostrato in Gestione Cespiti (contabilità)
# libro_unico_parser / f24_parser (router HTTP): smontati (audit 14/07/2026,
# piano residuo op.5) — le route stesse non hanno chiamanti, ma le funzioni
# import_libro_unico/import_f24 restano vive: importate e chiamate
# direttamente da app/routers/documenti.py (pipeline di ingest documentale).
def _register_employees(app: FastAPI):
    from app.routers.employees import dipendenti
    from app.routers import tfr, drive_cedolini, drive_corrispettivi, drive_quietanze

    app.include_router(dipendenti.router, prefix="/api/dipendenti", tags=["Dipendenti"])
    app.include_router(tfr.router, prefix="/api/tfr", tags=["TFR"])
    app.include_router(drive_cedolini.router, prefix="/api/cedolini", tags=["Cedolini Drive"])
    app.include_router(drive_corrispettivi.router, prefix="/api/corrispettivi", tags=["Corrispettivi Drive"])
    app.include_router(drive_quietanze.router, prefix="/api/f24/quietanze", tags=["Quietanze Drive"])

    # Documenti fiscali caricati a mano (dichiarazione IVA, cartelle
    # esattoriali, avvisi bonari): upload → id → recupero/download.
    from app.routers import documenti_fiscali
    app.include_router(documenti_fiscali.router, prefix="/api/documenti-fiscali", tags=["Documenti fiscali"])

    # Gestione IVA (SPECIFICA_IVA.md): attribuzione periodo per competenza,
    # IVA disponibile non utilizzata.
    from app.routers import iva as iva_router
    app.include_router(iva_router.router, prefix="/api/iva", tags=["IVA"])


# ─── Reports Module ──────────────────────────────────────────────────────────
# report_pdf, simple_exports: smontati (audit 14/07/2026, piano residuo
# op.9/op.4) — zero chiamanti verificati (frontend/scheduler/interno/test).
# File conservati in git, non montati in produzione.
def _register_reports(app: FastAPI):
    from app.routers.reports import dashboard

    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])


# ─── Core Routers ────────────────────────────────────────────────────────────
def _register_core(app: FastAPI):
    # Rimossi dai router "core" (audit lug 2026, zero chiamanti verificati
    # due volte): chart_of_accounts, cash_register, ocr_assegni,
    # indici_bilancio, notifications (la campanella usa /api/alerts),
    # config.py (/api/config/email mai chiamato; /api/config/* vivo è
    # configurazioni.py), import_templates, import_manuale, enhanced_parser,
    # learning_machine_cdc (router; il service omonimo resta vivo),
    # inps_documenti, adr, e l'alias doppio /api/fornitori (il frontend usa
    # /api/suppliers). controllo_gestione resta: il chatbot ne importa
    # get_trend_mensile.
    from app.routers import (
        cash,
        settings as settings_base,
        finanziaria, gestione_riservata, commercialista, scadenze,
        pianificazione, admin, admin_rollback, verifica_coerenza,
        documenti, cespiti, scadenzario_fornitori, controllo_gestione,
        chiusura_esercizio,
        configurazioni, alerts,
        mutui, mutui_parser, auto_repair,
        rapido, settings_router, dati_provvisori,
        batch_reprocessing, pos_corrispettivi_check,
        chat_router, learning_universal, voci_bilancio
    )
    from app.routers.suppliers_module import router as suppliers_router
    from app.routers.operazioni_module import router as operazioni_router
    from app.routers import openapi_imprese, openapi_it, openapi_automotive
    from app.routers import websocket_realtime, learning_machine, fornitori_learning
    from app.routers import sync_relazionale, pagopa
    from app.routers import anagrafica_fornitori_xml
    from app.routers import config_import
    from app.routers import ritenute
    from app.routers import collaudo
    from app.routers import utenti

    app.include_router(suppliers_router, prefix="/api/suppliers", tags=["Suppliers"])
    app.include_router(cash.router, prefix="/api/cash", tags=["Cash"])
    app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(settings_base.router, prefix="/api/settings", tags=["Settings Base"])
    app.include_router(configurazioni.router, prefix="/api/config", tags=["Configurazioni"])
    app.include_router(finanziaria.router, prefix="/api/finanziaria", tags=["Finanziaria"])
    app.include_router(gestione_riservata.router, prefix="/api/gestione-riservata", tags=["Gestione Riservata"])
    app.include_router(commercialista.router, prefix="/api/commercialista", tags=["Commercialista"])
    app.include_router(scadenze.router, prefix="/api/scadenze", tags=["Scadenze"])
    app.include_router(pianificazione.router, prefix="/api/pianificazione", tags=["Pianificazione"])
    app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
    app.include_router(admin_rollback.router, tags=["Admin Rollback"])
    app.include_router(verifica_coerenza.router, prefix="/api/verifica-coerenza", tags=["Verifica Coerenza"])
    app.include_router(documenti.router, prefix="/api/documenti", tags=["Documenti"])
    app.include_router(operazioni_router, prefix="/api/operazioni-da-confermare", tags=["Operazioni"])
    app.include_router(cespiti.router, prefix="/api/cespiti", tags=["Cespiti"])
    app.include_router(voci_bilancio.router, prefix="/api/voci-bilancio", tags=["Voci Bilancio Manuali"])
    app.include_router(scadenzario_fornitori.router, prefix="/api/scadenzario-fornitori", tags=["Scadenzario"])
    app.include_router(controllo_gestione.router, prefix="/api/controllo-gestione", tags=["Controllo Gestione"])
    app.include_router(chiusura_esercizio.router, prefix="/api/chiusura-esercizio", tags=["Chiusura Esercizio"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["Alert"])
    app.include_router(mutui.router, prefix="/api/mutui", tags=["Mutui"])
    app.include_router(mutui_parser.router, prefix="/api/mutui", tags=["Mutui Parser"])
    app.include_router(auto_repair.router, prefix="/api/auto-repair", tags=["Auto Riparazione"])
    app.include_router(rapido.router, prefix="/api/rapido", tags=["Inserimento Rapido"])
    app.include_router(dati_provvisori.router, prefix="/api", tags=["Dati Provvisori"])
    app.include_router(batch_reprocessing.router, prefix="/api/batch-reprocess", tags=["Batch Reprocessing"])
    app.include_router(pos_corrispettivi_check.router, prefix="/api", tags=["POS Check"])
    app.include_router(chat_router.router, prefix="/api", tags=["Chat"])
    app.include_router(learning_universal.router, prefix="/api/learning-universal", tags=["Learning Universal"])
    app.include_router(anagrafica_fornitori_xml.router, prefix="/api/anagrafica-fornitori", tags=["Anagrafica Fornitori"])
    app.include_router(config_import.router, prefix="/api/config-import", tags=["Config Import"])
    app.include_router(ritenute.router, prefix="/api/ritenute", tags=["Ritenute"])
    app.include_router(collaudo.router, prefix="/api/collaudo", tags=["Collaudo"])
    app.include_router(utenti.router, prefix="/api", tags=["Utenti"])
    app.include_router(websocket_realtime.router, prefix="/api", tags=["WebSocket"])
    app.include_router(learning_machine.router, prefix="/api/learning-machine", tags=["Learning Machine"])
    app.include_router(fornitori_learning.router, prefix="/api/fornitori-learning", tags=["Fornitori Learning"])
    app.include_router(openapi_imprese.router, prefix="/api/openapi-imprese", tags=["OpenAPI Imprese"])
    app.include_router(openapi_it.router, prefix="/api/openapi", tags=["OpenAPI.it"])
    app.include_router(openapi_automotive.router, prefix="/api/openapi-automotive", tags=["OpenAPI Automotive"])
    app.include_router(sync_relazionale.router, prefix="/api", tags=["Sync Relazionale"])
    app.include_router(pagopa.router, prefix="/api/pagopa", tags=["PagoPA"])

    # Agenti AI, PayPal, Previsioni Acquisti
    from app.routers import agenti, paypal_api, previsioni_acquisti, dati_isa
    app.include_router(agenti.router, prefix="/api/agenti", tags=["Agenti AI"])
    app.include_router(paypal_api.router, prefix="/api/paypal-api", tags=["PayPal API"])
    app.include_router(previsioni_acquisti.router, prefix="/api/previsioni-acquisti", tags=["Previsioni Acquisti"])
    app.include_router(dati_isa.router, prefix="/api/dati-isa", tags=["Dati ISA"])

    # Multi-Pagamento Fatture
    from app.routers import multi_pagamento
    app.include_router(multi_pagamento.router, prefix="/api/pagamenti", tags=["Multi-Pagamento"])


# ─── Email Module ────────────────────────────────────────────────────────────
def _register_email(app: FastAPI):
    from app.routers import (
        email_scanner, email_download,
        documenti_non_associati, document_ai, ai_parser
    )

    app.include_router(email_scanner.router, prefix="/api/email-scanner", tags=["Email Scanner"])
    app.include_router(email_download.router, prefix="/api/email-download", tags=["Email Download"])

    # Auto-classify documents_inbox (Gmail/PEC)
    from app.routers import documents_inbox_classify
    app.include_router(documents_inbox_classify.router, prefix="/api/documenti-inbox", tags=["Documents Inbox"])
    app.include_router(documenti_non_associati.router, prefix="/api/documenti-non-associati", tags=["Documenti Non Associati"])
    app.include_router(document_ai.router, prefix="/api/document-ai", tags=["Document AI"])
    app.include_router(ai_parser.router, prefix="/api/ai-parser", tags=["AI Parser"])


# ─── Noleggio & Verbali Module ───────────────────────────────────────────────
def _register_noleggio(app: FastAPI):
    # veicoli.py (prefisso legacy /api/noleggio-auto) rimosso: scriveva sulla
    # stessa collezione veicoli_noleggio con uno schema incompatibile
    # (stato/anno/data_scadenza_noleggio) e zero chiamanti frontend — vedi
    # memoria/endpoints/07-hr-noleggio-verbali.md. noleggio.py (prefisso
    # /api/noleggio) resta l'unico scrittore canonico della collezione.
    from app.routers import noleggio, verbali_noleggio, verbali_noleggio_api, verbali_riconciliazione

    app.include_router(noleggio.router, prefix="/api/noleggio", tags=["Noleggio Auto"])
    app.include_router(verbali_noleggio.router, tags=["Verbali Noleggio"])
    app.include_router(verbali_noleggio_api.router, prefix="/api/verbali-noleggio", tags=["Verbali API"])
    app.include_router(verbali_riconciliazione.router, prefix="/api/verbali-riconciliazione", tags=["Verbali Riconciliazione"])
    # trattenute_verbali: smontato (audit 14/07/2026, piano residuo op.10) —
    # tutti i 7 endpoint del router erano "verificare" (zero chiamanti); solo
    # retro-verifica aveva un servizio vivo dietro (verifica_trattenute_retroattiva,
    # già chiamata direttamente dallo scheduler, non tramite questa route).
    # File conservato in git, non montato in produzione.
    from app.routers import admin_export
    app.include_router(admin_export.router, prefix="/api", tags=["Admin Export"])


# ─── AI Module ───────────────────────────────────────────────────────────────
def _register_ai(app: FastAPI):
    """Registra router AI/ML (opzionale - non blocca se fallisce)."""
    pass  # AI routers already registered in _register_email


