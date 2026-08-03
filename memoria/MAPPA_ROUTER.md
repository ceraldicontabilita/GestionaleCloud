# MAPPA ROUTER — GestionaleCloud

> rigenerata via scripts/genera_mappa.py — leggendo la route table reale di `register_all_routers`.
> Totale **1041 endpoint** in **107 prefissi**.

Colonna FE: `✓` prefisso usato dal frontend · `ext` chiamante esterno (app collegata / webhook / chatbot / scheduler / API pubblica) · `—` nessun riferimento noto (candidato verifica).

| Prefisso | Endpoint | FE | Moduli (file router) |
|---|---:|:-:|---|
| `/api/admin` | 17 | ✓ | admin, admin_export, admin_rollback |
| `/api/agenti` | 16 | ext | agenti |
| `/api/ai-parser` | 11 | ext | ai_parser |
| `/api/alerts` | 7 | ✓ | alerts |
| `/api/anagrafica-fornitori` | 2 | ✓ | anagrafica_fornitori_xml |
| `/api/archivio-bonifici` | 28 | ✓ | bank.bonifici_import_unificato, bonifici_module.associazioni, bonifici_module.jobs, bonifici_module.riconciliazione, bonifici_module.transfers |
| `/api/assegni` | 39 | ✓ | bank.assegni, bank.assegni_learning, public_api |
| `/api/auth` | 11 | ext | auth, mfa, pin_login |
| `/api/auto-repair` | 1 | ✓ | auto_repair |
| `/api/bank` | 2 | ✓ | public_api |
| `/api/bank-statement` | 6 | ✓ | bank.bank_statement_import |
| `/api/batch-reprocess` | 5 | ✓ | batch_reprocessing |
| `/api/bilancio` | 7 | ✓ | accounting.bilancio |
| `/api/cash` | 10 | ✓ | cash, public_api |
| `/api/cedolini` | 2 | — | drive_cedolini |
| `/api/centri-costo` | 10 | ✓ | accounting.centri_costo |
| `/api/cespiti` | 12 | ✓ | cespiti |
| `/api/chat` | 3 | ✓ | chat_router |
| `/api/chiusura-esercizio` | 7 | ✓ | chiusura_esercizio |
| `/api/collaudo` | 3 | ✓ | collaudo |
| `/api/commercialista` | 14 | ✓ | commercialista |
| `/api/conferma` | 1 | — | dati_provvisori |
| `/api/conferma-tutte` | 1 | — | dati_provvisori |
| `/api/config` | 9 | ✓ | configurazioni |
| `/api/config-import` | 3 | ✓ | config_import |
| `/api/contabilita` | 10 | ✓ | accounting.contabilita_avanzata, contabilita_italiana |
| `/api/contabilita-gestionale` | 14 | ✓ | accounting.contabilita_gestionale |
| `/api/controllo-gestione` | 4 | ✓ | controllo_gestione |
| `/api/corrispettivi` | 27 | ✓ | drive_corrispettivi, invoices.corrispettivi |
| `/api/dashboard` | 9 | ✓ | public_api, reports.dashboard |
| `/api/data-deletion` | 1 | — | legal_pages |
| `/api/dati-provvisori` | 1 | — | dati_provvisori |
| `/api/dipendenti` | 28 | ✓ | employees.dipendenti |
| `/api/dizionario-articoli` | 11 | ✓ | warehouse.dizionario_articoli |
| `/api/document-ai` | 10 | ✓ | document_ai |
| `/api/documenti` | 30 | ✓ | documenti |
| `/api/documenti-fiscali` | 2 | ✓ | documenti_fiscali |
| `/api/documenti-inbox` | 5 | ✓ | documents_inbox_classify |
| `/api/documenti-non-associati` | 9 | ✓ | documenti_non_associati |
| `/api/email-download` | 41 | ✓ | email_download |
| `/api/email-scanner` | 5 | ✓ | email_scanner |
| `/api/erp` | 2 | ext | erp_bridge |
| `/api/estratto-conto-movimenti` | 15 | ✓ | bank.estratto_conto |
| `/api/f24` | 27 | ✓ | drive_quietanze, f24.f24_main |
| `/api/f24-analisi` | 4 | ✓ | f24_analisi |
| `/api/f24-email` | 7 | ✓ | f24.email_f24 |
| `/api/f24-email-settings` | 8 | ✓ | f24_email_settings |
| `/api/f24-public` | 11 | ext | f24.f24_public, public_api |
| `/api/f24-riconciliazione` | 23 | ✓ | bank.riconciliazione_f24_banca, f24.f24_riconciliazione |
| `/api/fatture` | 15 | ✓ | invoices.fatture_drive, invoices.fatture_upload |
| `/api/fatture-estere` | 3 | ✓ | fatture_estera_verifica |
| `/api/fatture-ricevute` | 23 | ✓ | fatture_module.crud, fatture_module.export_selezione, fatture_module.pagamento |
| `/api/finanziamenti-soci` | 4 | ✓ | finanziamenti_soci |
| `/api/finanziaria` | 4 | ✓ | finanziaria |
| `/api/fiscalita` | 10 | ✓ | fiscalita_italiana |
| `/api/fornitori-learning` | 16 | ✓ | fornitori_learning |
| `/api/genera-proposte` | 1 | — | dati_provvisori |
| `/api/gestione-riservata` | 7 | ✓ | gestione_riservata |
| `/api/invoices` | 8 | ✓ | invoices.invoices_emesse, invoices.invoices_main |
| `/api/iva` | 19 | ✓ | iva |
| `/api/learning-machine` | 7 | ✓ | learning_machine |
| `/api/learning-universal` | 5 | ✓ | learning_universal |
| `/api/mutui` | 13 | ✓ | mutui, mutui_parser |
| `/api/nexi` | 4 | ✓ | nexi_carta |
| `/api/noleggio` | 13 | ✓ | noleggio |
| `/api/openapi` | 12 | ext | openapi_it |
| `/api/openapi-automotive` | 6 | ext | openapi_automotive |
| `/api/openapi-imprese` | 6 | ext | openapi_imprese |
| `/api/operazioni-da-confermare` | 12 | ✓ | operazioni_module, operazioni_module.smart |
| `/api/pagamenti` | 6 | ✓ | multi_pagamento |
| `/api/pagopa` | 8 | ✓ | pagopa |
| `/api/partite-aperte` | 3 | ✓ | partite_aperte_api |
| `/api/paypal-api` | 11 | ✓ | paypal_api |
| `/api/paypal-statements` | 14 | ✓ | paypal_statements |
| `/api/pianificazione` | 5 | ✓ | pianificazione, public_api |
| `/api/piano-conti` | 12 | ✓ | accounting.piano_conti |
| `/api/portal` | 1 | ext | public_api |
| `/api/pos-corrispettivi` | 9 | ✓ | pos_corrispettivi_check |
| `/api/previsioni-acquisti` | 5 | ✓ | previsioni_acquisti |
| `/api/prima-nota` | 73 | ✓ | prima_nota_module, prima_nota_module.banca, prima_nota_module.cassa, prima_nota_module.manutenzione, prima_nota_module.salari, prima_nota_module.stats, prima_nota_module.sync |
| `/api/prima-nota-salari` | 18 | ✓ | accounting.prima_nota_salari |
| `/api/privacy` | 1 | — | legal_pages |
| `/api/proposte` | 1 | — | dati_provvisori |
| `/api/rapido` | 8 | ✓ | rapido |
| `/api/regole` | 7 | ✓ | accounting.regole_categorizzazione |
| `/api/ricerca-globale` | 1 | — | public_api |
| `/api/riconciliazione` | 1 | ✓ | riconciliazione_stats_api |
| `/api/rifiuta` | 1 | — | dati_provvisori |
| `/api/ritenute` | 3 | ✓ | ritenute |
| `/api/scadenzario-fornitori` | 6 | ✓ | scadenzario_fornitori |
| `/api/scadenze` | 10 | ✓ | scadenze |
| `/api/settings` | 12 | ✓ | settings, settings_router |
| `/api/suppliers` | 34 | ✓ | public_api, suppliers_module.base, suppliers_module.bulk, suppliers_module.iban, suppliers_module.import_export, suppliers_module.validation |
| `/api/sync` | 8 | ✓ | sync_relazionale |
| `/api/terms` | 1 | — | legal_pages |
| `/api/tfr` | 17 | ✓ | tfr |
| `/api/utenti` | 4 | ✓ | utenti |
| `/api/v1` | 5 | ext | public_api |
| `/api/verbali-noleggio` | 5 | ✓ | verbali_noleggio, verbali_noleggio_api |
| `/api/verbali-riconciliazione` | 7 | ✓ | verbali_riconciliazione |
| `/api/verifica-coerenza` | 7 | ✓ | verifica_coerenza |
| `/api/voci-bilancio` | 4 | ✓ | voci_bilancio |
| `/api/warehouse` | 6 | ✓ | public_api |
| `/api/whatsapp` | 5 | ext | whatsapp_webhook |
| `/data-deletion` | 1 | ext | legal_pages |
| `/privacy` | 1 | ext | legal_pages |
| `/terms` | 1 | ext | legal_pages |
