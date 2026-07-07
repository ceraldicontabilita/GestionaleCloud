# MAPPA ROUTER — GestionaleCloud

Generata automaticamente importando `app.main:app` e leggendo la route table reale
(quindi include solo le route effettivamente registrate da `app/router_registry.py`).
Totale: **1.378 route API in 142 gruppi di prefisso**.

Formato: `prefisso (n° route) [moduli in app/routers/ che le implementano]`

## Contabilità e Prima Nota

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/prima-nota` | 57 | prima_nota_module (banca, cassa, manutenzione, salari, stats, sync) |
| `/api/prima-nota-auto` | 10 | accounting.prima_nota_automation |
| `/api/prima-nota-salari` | 14 | accounting.prima_nota_salari |
| `/api/prima-nota-salari-v2` | 2 | accounting.prima_nota_salari_v2 |
| `/api/accounting` | 21 | accounting.accounting_main, accounting_extended, accounting_engine |
| `/api/accounting-engine` | 11 | accounting.accounting_engine_api |
| `/api/contabilita` | 21 | accounting.contabilita_avanzata, contabilita_italiana |
| `/api/contabilita-gestionale` | 9 | accounting.contabilita_gestionale |
| `/api/piano-conti` | 12 | accounting.piano_conti |
| `/api/bilancio` | 7 | accounting.bilancio |
| `/api/centri-costo` | 11 | accounting.centri_costo |
| `/api/iva` | 6 | accounting.iva_calcolo |
| `/api/liquidazione-iva` | 5 | accounting.liquidazione_iva |
| `/api/chiusura-esercizio` | 7 | chiusura_esercizio |
| `/api/regole` | 7 | accounting.regole_categorizzazione |
| `/api/chart-of-accounts` | 4 | chart_of_accounts |
| `/api/indici-bilancio` | 2 | indici_bilancio |
| `/api/fiscalita` | 12 | fiscalita_italiana |
| `/api/controllo-gestione` | 7 | controllo_gestione |
| `/api/finanziaria` | 4 | finanziaria |
| `/api/cespiti` | 11 | cespiti |
| `/api/mutui` | 13 | mutui, mutui_parser |
| `/api/partite-aperte` | 3 | partite_aperte_api |
| `/api/codici-tributari` | 5 | codici_tributari |

## Fatture e Fornitori

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/invoices` | 48 | invoices (invoices_main, invoices_main_overlay, invoices_emesse, invoices_export), public_api |
| `/api/fatture` | 21 | invoices.fatture_upload (CUORE import XML), fatture_overlay, fatture_drive |
| `/api/fatture-ricevute` | 18 | fatture_module (crud, pagamento) |
| `/api/corrispettivi` | 25 | invoices.corrispettivi |
| `/api/suppliers` = `/api/fornitori` | 32 | suppliers_module (base, bulk, iban, import_export, validation), public_api |
| `/api/fornitori-learning` | 14 | fornitori_learning |
| `/api/scadenzario-fornitori` | 7 | scadenzario_fornitori |
| `/api/schede-tecniche` | 7 | schede_tecniche |
| `/api/previsioni-acquisti` | 5 | previsioni_acquisti |

## Banca, Riconciliazione, Assegni, PayPal

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/assegni` | 37 | bank.assegni, bank.assegni_learning (+auto-match 4 livelli in bank.assegni_auto_match) |
| `/api/estratto-conto-movimenti` | 12 | bank.estratto_conto |
| `/api/estratto-conto` | 6 | bank.bank_statement_parser |
| `/api/bank-statement` | 6 | bank.bank_statement_import |
| `/api/bank-statement-bulk` | 6 | bank.bank_statement_bulk_import |
| `/api/bank` | 9 | bank.bank_main, public_api |
| `/api/bank-reconciliation` | 5 | bank.bank_reconciliation |
| `/api/archivio-bonifici` | 27 | bonifici_module (associazioni, jobs, riconciliazione, transfers), bank.bonifici_import_unificato |
| `/api/operazioni-da-confermare` | 13 | operazioni_module (smart, carta) |
| `/api/riconciliazione` | 9 | email_reconciliation, riconciliazione_stats_api |
| `/api/riconciliazione-auto` | 7 | accounting.riconciliazione_automatica |
| `/api/riconciliazione-intelligente` | 25 | riconciliazione_intelligente_api |
| `/api/paypal-statements` | 12 | paypal_statements |
| `/api/paypal-api` | 9 | paypal_api |
| `/api/pos-accredito` | 5 | bank.pos_accredito |
| `/api/pos-corrispettivi` | 8 | pos_corrispettivi_check |
| `/api/pagamenti` | 6 | multi_pagamento |
| `/api/ocr-assegni` | 6 | ocr_assegni |
| `/api/cash` | 10 | cash, public_api |
| `/api/cash-register` | 9 | cash_register |
| `/api/pagopa` | 7 | pagopa |

## F24

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/f24` | 22 | f24.f24_main |
| `/api/f24-riconciliazione` | 23 | f24.f24_riconciliazione, bank.riconciliazione_f24_banca |
| `/api/f24-avanzato` | 11 | f24.f24_gestione_avanzata |
| `/api/f24-public` | 11 | f24.f24_public, public_api |
| `/api/f24-email` | 7 | f24.email_f24 |
| `/api/f24-email-settings` | 8 | f24_email_settings |
| `/api/f24-notifiche` | 6 | f24.f24_notifiche |
| `/api/quietanze-f24` | 6 | f24.quietanze |

## Documenti, Email, AI

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/email-download` | 39 | email_download |
| `/api/documenti` | 32 | documenti |
| `/api/documenti-non-associati` | 7 | documenti_non_associati |
| `/api/documenti-inbox` | 5 | documents_inbox_classify |
| `/api/document-ai` | 10 | document_ai |
| `/api/ai-parser` | 11 | ai_parser |
| `/api/enhanced-parser` | 4 | enhanced_parser |
| `/api/email-scanner` | 5 | email_scanner |
| `/api/email-mongodb` | 4 | email_mongodb |
| `/api/import-manuale` | 6 | import_manuale |
| `/api/import-templates` | 4 | import_templates |
| `/api/chat` | 2 | chat_router |
| `/api/learning-machine` | 7 | learning_machine |
| `/api/learning-universal` | 5 | learning_universal |
| `/api/learning-cdc` | 5 | learning_machine_cdc |

## HR / Paghe (residuo: HR vive in AppDipendenti)

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/dipendenti` | 52 | employees.dipendenti |
| `/api/paghe` | 18 | distinte_bpm, f24_parser, libro_unico_parser |
| `/api/tfr` | 17 | tfr |
| `/api/inps` | 9 | inps_documenti |

## Noleggio / Verbali

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/verbali-noleggio` | 35 | verbali_noleggio, verbali_noleggio_api |
| `/api/verbali-riconciliazione` | 25 | verbali_riconciliazione |
| `/api/noleggio` | 14 | noleggio |
| `/api/noleggio-auto` | 6 | veicoli |
| `/api/alert-verbali` | 2 | alert_verbali |
| `/api/adr` | 7 | adr |

## Magazzino

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/dizionario-articoli` | 11 | warehouse.dizionario_articoli |
| `/api/warehouse` | 6 | public_api |

## Sistema, Admin, Integrazioni, Varie

| Prefisso | Route | Moduli |
|---|---:|---|
| `/api/auth` (+/login,/logout,/me) | 8 | auth, pin_login |
| `/api/admin` | 11 | admin, admin_export |
| `/api/config` | 11 | config, configurazioni |
| `/api/settings` | 9 | settings, settings_router |
| `/api/dashboard` | 9 | reports.dashboard, public_api |
| `/api/exports` | 13 | reports.exports, simple_exports |
| `/api/report-pdf` | 4 | reports.report_pdf |
| `/api/analytics` | 4 | reports.analytics |
| `/api/scadenze` | 10 | scadenze |
| `/api/alerts` | 7 | alerts |
| `/api/notifications` | 7 | notifications |
| `/api/todo` | 10 | todo |
| `/api/agenti` | 8 | agenti |
| `/api/rapido` | 8 | rapido |
| `/api/batch` | 6 | batch_operations |
| `/api/batch-reprocess` | 5 | batch_reprocessing |
| `/api/auto-repair` | 1 | auto_repair |
| `/api/sync` | 8 | sync_relazionale |
| `/api/verifica-coerenza` | 7 | verifica_coerenza |
| `/api/commercialista` | 14 | commercialista |
| `/api/gestione-riservata` | 7 | gestione_riservata |
| `/api/dati-provvisori` (+/proposte,/conferma,/conferma-tutte,/rifiuta,/genera-proposte) | 11 | dati_provvisori |
| `/api/openapi-imprese` | 6 | openapi_imprese (visure CCIAA) |
| `/api/openapi` | 10 | openapi_it |
| `/api/openapi-automotive` | 6 | openapi_automotive (targhe) |
| `/api/pianificazione` | 5 | pianificazione |
| `/api/whatsapp` | 5 | whatsapp_webhook |
| `/api/erp` | 2 | erp_bridge |
| `/api/realtime` | 1 | websocket_realtime |
| `/api/v1`, `/api/portal`, `/api/ricerca-globale` | 7 | public_api |
| `/privacy`, `/terms`, `/data-deletion` | 6 | legal_pages |
| `/api/health`, `/api/ping`, `/api/system`, `/health` | 4 | app.main |

---

# MAPPA PAGINA FRONTEND → API USATE

Per ogni pagina in `frontend/src/pages/`, i prefissi API che chiama
(estratti via grep sulle stringhe `/api/...`).

| Pagina | API usate |
|---|---|
| Admin.jsx | admin, config, fatture, health, prima-nota, sync |
| Agenti.jsx | agenti |
| ArchivioBonifici.jsx | archivio-bonifici |
| ArchivioFattureRicevute.jsx | fatture-ricevute |
| AuthCallback.jsx | auth |
| BatchProcessor.jsx | ai-parser, email-download, estratto-conto-movimenti, f24-riconciliazione |
| BatchReprocessing.jsx | batch-reprocess |
| Bilancio.jsx | bilancio |
| BilancioVerifica.jsx | contabilita-gestionale |
| BudgetPrevisionale.jsx | contabilita-gestionale |
| CalendarioFiscale.jsx | fiscalita |
| ChiusuraEsercizio.jsx | chiusura-esercizio |
| CoerenzaPOSCorrispettivi.jsx | corrispettivi, pos-corrispettivi |
| Commercialista.jsx | assegni, commercialista |
| ContabilitaAvanzata.jsx | contabilita |
| ControlloMensile.jsx | bank-statement, corrispettivi, prima-nota |
| Corrispettivi.jsx | corrispettivi |
| Dashboard.jsx | batch, contabilita, dashboard, email-download, f24-public, fatture-ricevute, fornitori-learning, gestione-riservata, noleggio, paghe, pos-accredito, report-pdf, scadenze |
| DashboardRelazionale.jsx | alerts, partite-aperte, riconciliazione |
| DatiProvvisoriPage.jsx | conferma, conferma-tutte, genera-proposte, proposte, rifiuta |
| DettaglioVerbale.jsx | fatture-ricevute, verbali-noleggio |
| DizionarioArticoli.jsx | dizionario-articoli |
| Documenti.jsx | document-ai, documenti, documenti-non-associati, settings, system |
| Finanziaria.jsx | finanziaria |
| Fornitori.jsx | fatture-ricevute, openapi-imprese, schede-tecniche, suppliers |
| GestioneAssegni.jsx | assegni, fatture-ricevute, invoices |
| GestioneCespiti.jsx | cespiti, scadenzario-fornitori, tfr |
| GestionePagoPA.jsx | bank-statement, pagopa |
| GestioneRiservata.jsx | gestione-riservata |
| ImportDocumenti.jsx | documenti, documenti-inbox |
| ImpostazioniF24Email.jsx | f24-email-settings, settings |
| InserimentoRapido.jsx | dipendenti, fatture-ricevute, invoices, rapido |
| IntegrazioniOpenAPI.jsx | openapi |
| LearningMachine.jsx | assegni, fornitori-learning, learning-machine |
| LearningMachineUniversale.jsx | learning-universal |
| Mutui.jsx | mutui |
| NoleggioAuto.jsx | fatture-ricevute, noleggio, openapi-automotive |
| Pianificazione.jsx | pianificazione |
| PianoDeiConti.jsx | dizionario-articoli, piano-conti |
| PrevisioniAcquisti.jsx | previsioni-acquisti |
| PrimaNota.jsx | archivio-bonifici, corrispettivi, estratto-conto-movimenti, f24, fatture-ricevute, pagamenti, prima-nota |
| PuliziaPrimaNota.jsx | prima-nota |
| RegoleCategorizzazione.jsx | contabilita, regole |
| RiconciliazionePaypal.jsx | fatture-ricevute, paypal-api, paypal-statements |
| RiconciliazioneUnificata.jsx | assegni, documenti-non-associati, estratto-conto-movimenti, fatture-ricevute, operazioni-da-confermare, prima-nota-banca, riconciliazione-intelligente |
| Scadenze.jsx | email-scanner, fatture, fatture-ricevute, scadenze |
| ToDo.jsx | todo |
| UtileObiettivo.jsx | centri-costo |
| VerbaliRiconciliazione.jsx | auto-repair, dipendenti, verbali-riconciliazione |
| VerificaCoerenza.jsx | verifica-coerenza |
| VerificaMovimentiBanca.jsx | prima-nota |
| Visure.jsx | openapi-imprese |

Nota: le pagine hub (`pages/hub/*.jsx`) non chiamano API direttamente, montano le pagine sopra.
