# MAPPA ROUTER — GestionaleCloud

Rigenerata automaticamente il 2026-07-07 (post audit/normalizzazione router)
importando `app.main:app` e leggendo la route table reale.
Totale: **1074 route API in 110 gruppi di prefisso**
(erano 1.378 a inizio giornata: −304 route morte/duplicate rimosse).

Colonna FE: ✓ = prefisso referenziato nel frontend; — = nessun riferimento
frontend (vivo via backend/scheduler/webhook/API esterna, verificato con doppio audit).

| Prefisso | Route | FE | Moduli |
|---|---:|:-:|---|
| `/` | 1 | — | main |
| `/api/admin` | 12 | ✓ | admin, admin_export |
| `/api/agenti` | 8 | ✓ | agenti |
| `/api/ai-parser` | 11 | ✓ | ai_parser |
| `/api/alerts` | 7 | ✓ | alerts |
| `/api/archivio-bonifici` | 27 | ✓ | bank.bonifici_import_unificato, bonifici_module.associazioni, bonifici_module.jobs, bonifici_module.riconciliazione, bonifici_module.transfers |
| `/api/assegni` | 38 | ✓ | bank.assegni, bank.assegni_learning, public_api |
| `/api/auth` | 5 | ✓ | auth, pin_login |
| `/api/auto-repair` | 1 | ✓ | auto_repair |
| `/api/bank` | 9 | ✓ | bank.bank_main, public_api |
| `/api/bank-statement` | 6 | ✓ | bank.bank_statement_import |
| `/api/batch` | 6 | ✓ | batch_operations |
| `/api/batch-reprocess` | 5 | ✓ | batch_reprocessing |
| `/api/bilancio` | 7 | ✓ | accounting.bilancio |
| `/api/cash` | 10 | ✓ | cash, public_api |
| `/api/centri-costo` | 11 | ✓ | accounting.centri_costo |
| `/api/cespiti` | 11 | ✓ | cespiti |
| `/api/chat` | 2 | ✓ | chat_router |
| `/api/chiusura-esercizio` | 7 | ✓ | chiusura_esercizio |
| `/api/commercialista` | 14 | ✓ | commercialista |
| `/api/conferma` | 1 | ✓ | dati_provvisori |
| `/api/conferma-tutte` | 1 | ✓ | dati_provvisori |
| `/api/config` | 9 | ✓ | configurazioni |
| `/api/contabilita` | 21 | ✓ | accounting.contabilita_avanzata, contabilita_italiana |
| `/api/contabilita-gestionale` | 9 | ✓ | accounting.contabilita_gestionale |
| `/api/controllo-gestione` | 7 | — | controllo_gestione |
| `/api/corrispettivi` | 25 | ✓ | invoices.corrispettivi |
| `/api/dashboard` | 9 | ✓ | public_api, reports.dashboard |
| `/api/data-deletion` | 1 | — | legal_pages |
| `/api/dati-provvisori` | 6 | — | dati_provvisori |
| `/api/dipendenti` | 51 | ✓ | employees.dipendenti |
| `/api/dizionario-articoli` | 11 | ✓ | warehouse.dizionario_articoli |
| `/api/document-ai` | 10 | ✓ | document_ai |
| `/api/documenti` | 32 | ✓ | documenti |
| `/api/documenti-inbox` | 5 | ✓ | documents_inbox_classify |
| `/api/documenti-non-associati` | 7 | ✓ | documenti_non_associati |
| `/api/email-download` | 39 | ✓ | email_download |
| `/api/email-scanner` | 5 | ✓ | email_scanner |
| `/api/erp` | 2 | — | erp_bridge |
| `/api/estratto-conto-movimenti` | 12 | ✓ | bank.estratto_conto |
| `/api/exports` | 13 | ✓ | reports.exports, reports.simple_exports |
| `/api/f24` | 22 | ✓ | f24.f24_main |
| `/api/f24-email` | 7 | — | f24.email_f24 |
| `/api/f24-email-settings` | 8 | ✓ | f24_email_settings |
| `/api/f24-public` | 11 | ✓ | f24.f24_public, public_api |
| `/api/f24-riconciliazione` | 23 | ✓ | bank.riconciliazione_f24_banca, f24.f24_riconciliazione |
| `/api/fatture` | 14 | ✓ | invoices.fatture_drive, invoices.fatture_upload |
| `/api/fatture-ricevute` | 18 | ✓ | fatture_module.crud, fatture_module.pagamento |
| `/api/finanziaria` | 4 | ✓ | finanziaria |
| `/api/fiscalita` | 12 | ✓ | fiscalita_italiana |
| `/api/fornitori-learning` | 14 | ✓ | fornitori_learning |
| `/api/genera-proposte` | 1 | ✓ | dati_provvisori |
| `/api/gestione-riservata` | 7 | ✓ | gestione_riservata |
| `/api/health` | 1 | ✓ | main |
| `/api/invoices` | 9 | ✓ | invoices.invoices_emesse, invoices.invoices_main |
| `/api/learning-machine` | 7 | ✓ | learning_machine |
| `/api/learning-universal` | 5 | ✓ | learning_universal |
| `/api/mutui` | 13 | ✓ | mutui, mutui_parser |
| `/api/noleggio` | 11 | ✓ | noleggio |
| `/api/openapi` | 10 | ✓ | openapi_it |
| `/api/openapi-automotive` | 6 | ✓ | openapi_automotive |
| `/api/openapi-imprese` | 6 | ✓ | openapi_imprese |
| `/api/operazioni-da-confermare` | 10 | ✓ | operazioni_module, operazioni_module.smart |
| `/api/pagamenti` | 6 | ✓ | multi_pagamento |
| `/api/paghe` | 18 | ✓ | distinte_bpm, f24_parser, libro_unico_parser |
| `/api/pagopa` | 7 | ✓ | pagopa |
| `/api/partite-aperte` | 3 | ✓ | partite_aperte_api |
| `/api/paypal-api` | 11 | ✓ | paypal_api |
| `/api/paypal-statements` | 13 | ✓ | paypal_statements |
| `/api/pianificazione` | 5 | ✓ | pianificazione, public_api |
| `/api/piano-conti` | 12 | ✓ | accounting.piano_conti |
| `/api/ping` | 1 | — | main |
| `/api/portal` | 1 | — | public_api |
| `/api/pos-accredito` | 5 | ✓ | bank.pos_accredito |
| `/api/pos-corrispettivi` | 8 | ✓ | pos_corrispettivi_check |
| `/api/previsioni-acquisti` | 5 | ✓ | previsioni_acquisti |
| `/api/prima-nota` | 57 | ✓ | prima_nota_module, prima_nota_module.banca, prima_nota_module.cassa, prima_nota_module.manutenzione, prima_nota_module.salari, prima_nota_module.stats, prima_nota_module.sync |
| `/api/prima-nota-salari` | 14 | ✓ | accounting.prima_nota_salari |
| `/api/privacy` | 1 | — | legal_pages |
| `/api/proposte` | 1 | ✓ | dati_provvisori |
| `/api/rapido` | 8 | ✓ | rapido |
| `/api/realtime` | 1 | — | websocket_realtime |
| `/api/regole` | 7 | ✓ | accounting.regole_categorizzazione |
| `/api/report-pdf` | 4 | ✓ | reports.report_pdf |
| `/api/ricerca-globale` | 1 | — | public_api |
| `/api/riconciliazione` | 1 | ✓ | riconciliazione_stats_api |
| `/api/rifiuta` | 1 | ✓ | dati_provvisori |
| `/api/scadenzario-fornitori` | 6 | ✓ | scadenzario_fornitori |
| `/api/scadenze` | 10 | ✓ | scadenze |
| `/api/schede-tecniche` | 7 | ✓ | schede_tecniche |
| `/api/settings` | 9 | ✓ | settings, settings_router |
| `/api/suppliers` | 32 | ✓ | public_api, suppliers_module.base, suppliers_module.bulk, suppliers_module.iban, suppliers_module.import_export, suppliers_module.validation |
| `/api/sync` | 8 | ✓ | sync_relazionale |
| `/api/system` | 1 | ✓ | main |
| `/api/terms` | 1 | — | legal_pages |
| `/api/tfr` | 17 | ✓ | tfr |
| `/api/todo` | 10 | ✓ | todo |
| `/api/v1` | 5 | — | public_api |
| `/api/verbali-noleggio` | 32 | ✓ | verbali_noleggio, verbali_noleggio_api |
| `/api/verbali-riconciliazione` | 26 | ✓ | verbali_riconciliazione |
| `/api/verifica-coerenza` | 7 | ✓ | verifica_coerenza |
| `/api/warehouse` | 6 | ✓ | public_api |
| `/api/whatsapp` | 5 | — | whatsapp_webhook |
| `/api/ws` | 2 | ✓ | websocket_realtime |
| `/data-deletion` | 1 | — | legal_pages |
| `/health` | 1 | — | main |
| `/openapi.json` | 1 | — | fastapi.applications |
| `/privacy` | 1 | — | legal_pages |
| `/terms` | 1 | — | legal_pages |
| `/{full_path:path}` | 1 | — | main |

---

# MAPPA PAGINA FRONTEND → API USATE

| Pagina | API usate |
|---|---|
| Admin.jsx | admin, config, fatture, health, prima-nota, sync |
| Agenti.jsx | agenti |
| ArchivioBonifici.jsx | archivio-bonifici |
| ArchivioFattureRicevute.jsx | fatture-ricevute |
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
| MappaGestionale.jsx | download |
| Mutui.jsx | mutui |
| NoleggioAuto.jsx | fatture-ricevute, noleggio, openapi-automotive |
| Pianificazione.jsx | pianificazione |
| PianoDeiConti.jsx | dizionario-articoli, piano-conti |
| PrevisioniAcquisti.jsx | previsioni-acquisti |
| PrimaNota.jsx | archivio-bonifici, corrispettivi, estratto-conto-movimenti, f24, fatture-ricevute, pagamenti, prima-nota |
| PuliziaPrimaNota.jsx | prima-nota |
| RegoleCategorizzazione.jsx | contabilita, regole |
| RiconciliazionePaypal.jsx | fatture-ricevute, paypal-api, paypal-statements |
| RiconciliazioneUnificata.jsx | assegni, documenti-non-associati, download, estratto-conto-movimenti, fatture-ricevute, operazioni-da-confermare, prima-nota-banca |
| Scadenze.jsx | email-scanner, fatture, fatture-ricevute, scadenze |
| ToDo.jsx | todo |
| UtileObiettivo.jsx | centri-costo |
| VerbaliRiconciliazione.jsx | auto-repair, dipendenti, verbali-riconciliazione |
| VerificaCoerenza.jsx | verifica-coerenza |
| VerificaMovimentiBanca.jsx | prima-nota |
| Visure.jsx | openapi-imprese |
| hub/VeicoliHub.jsx | noleggio |

Nota: le pagine hub (`pages/hub/*.jsx`) non chiamano API direttamente, montano le pagine sopra.
