# Matrice API — Audit canonico Fase C

Generato da `scripts/estrai_matrice_api.py` + `scripts/classifica_matrice.py`.
Dati grezzi (ogni chiamata frontend con file:riga e ogni endpoint con file:riga):
`memoria/AUDIT_MATRICE_DATI.json`.

## Riepilogo

- Endpoint backend registrati: **1108**
- Chiamate API nel frontend: **423**
- Chiamate frontend senza endpoint (ROTTE): **2** (vedi sotto)
- ATTIVO: **379**
- INTEGRAZIONE: **44**
- MANUTENZIONE: **16**
- SISTEMA: **4**
- DA_VERIFICARE: **665**
- Coppie (metodo, path) duplicate: **4**

## Chiamate frontend senza endpoint

- `POST /api/invoices` — frontend/src/api.js:105 — FALSO POSITIVO: helper `createInvoice` in api.js MAI importato da nessuna pagina: codice morto, non un bottone rotto
- `POST /api/prima-nota-banca/crea` — frontend/src/pages/RiconciliazioneUnificata.jsx:491 — FALSO POSITIVO: chiamata dentro un blocco COMMENTATO in RiconciliazioneUnificata.jsx: non eseguita

**Nessun bottone/pagina chiama davvero un endpoint inesistente.**

## Endpoint duplicati (stesso metodo+path da handler diversi)

- `GET /api/assegni`
    - app/routers/public_api.py:505 `list_assegni` [app.routers.public_api]
    - app/routers/bank/assegni.py:120 `list_assegni` [app.routers.bank.assegni]
- `GET /api/dashboard/stats`
    - app/routers/public_api.py:716 `get_dashboard_stats` [app.routers.public_api]
    - app/routers/reports/dashboard.py:161 `get_stats` [app.routers.reports.dashboard]
- `GET /api/verbali-noleggio/dettaglio/{P}`
    - app/utils/error_handler.py:563 `get_dettaglio_verbale` [app.routers.verbali_noleggio]
    - app/utils/error_handler.py:22 `get_verbale_dettaglio` [app.routers.verbali_noleggio_api]
- `POST /api/suppliers`
    - app/routers/public_api.py:215 `create_supplier` [app.routers.public_api]
    - app/routers/suppliers_module/base.py:467 `create_supplier` [app.routers.suppliers_module.base]

## Endpoint per modulo router

| Modulo | Attivi | Integrazione | Manutenzione | Sistema | Da verificare | Tot |
|---|---|---|---|---|---|---|
| employees.dipendenti | 1 | 0 | 0 | 0 | 50 | 51 |
| email_download | 0 | 0 | 0 | 0 | 39 | 39 |
| documenti | 9 | 0 | 0 | 0 | 23 | 32 |
| bank.assegni | 14 | 0 | 0 | 0 | 16 | 30 |
| public_api | 9 | 17 | 0 | 0 | 0 | 26 |
| verbali_riconciliazione | 5 | 0 | 0 | 0 | 21 | 26 |
| invoices.corrispettivi | 3 | 0 | 0 | 0 | 20 | 23 |
| f24.f24_main | 1 | 0 | 0 | 0 | 21 | 22 |
| iva | 10 | 0 | 0 | 0 | 9 | 19 |
| verbali_noleggio | 2 | 0 | 0 | 0 | 17 | 19 |
| f24.f24_riconciliazione | 0 | 0 | 0 | 0 | 18 | 18 |
| tfr | 1 | 0 | 0 | 0 | 16 | 17 |
| prima_nota_module.sync | 5 | 0 | 0 | 0 | 11 | 16 |
| prima_nota_module.manutenzione | 9 | 0 | 0 | 0 | 7 | 16 |
| suppliers_module.base | 7 | 0 | 0 | 0 | 9 | 16 |
| fornitori_learning | 10 | 0 | 0 | 0 | 6 | 16 |
| accounting.prima_nota_salari | 9 | 0 | 0 | 0 | 5 | 14 |
| commercialista | 7 | 0 | 0 | 0 | 7 | 14 |
| paypal_statements | 7 | 0 | 0 | 0 | 6 | 13 |
| noleggio | 8 | 0 | 0 | 0 | 5 | 13 |
| verbali_noleggio_api | 1 | 0 | 0 | 0 | 12 | 13 |
| accounting.piano_conti | 6 | 0 | 0 | 0 | 6 | 12 |
| contabilita_italiana | 1 | 0 | 0 | 0 | 11 | 12 |
| fiscalita_italiana | 4 | 0 | 0 | 0 | 8 | 12 |
| bank.estratto_conto | 4 | 0 | 0 | 0 | 8 | 12 |
| invoices.fatture_upload | 2 | 0 | 0 | 0 | 10 | 12 |
| openapi_it | 4 | 8 | 0 | 0 | 0 | 12 |
| accounting.centri_costo | 2 | 0 | 0 | 0 | 9 | 11 |
| warehouse.dizionario_articoli | 1 | 0 | 0 | 0 | 10 | 11 |
| cespiti | 8 | 0 | 0 | 0 | 3 | 11 |
| dati_provvisori | 0 | 0 | 0 | 0 | 11 | 11 |
| paypal_api | 6 | 0 | 0 | 0 | 5 | 11 |
| ai_parser | 0 | 0 | 0 | 0 | 11 | 11 |
| fatture_module.pagamento | 2 | 0 | 0 | 0 | 8 | 10 |
| libro_unico_parser | 0 | 0 | 0 | 0 | 10 | 10 |
| scadenze | 9 | 0 | 0 | 0 | 1 | 10 |
| admin | 4 | 0 | 6 | 0 | 0 | 10 |
| mutui | 3 | 0 | 0 | 0 | 7 | 10 |
| document_ai | 5 | 0 | 0 | 0 | 5 | 10 |
| f24.f24_public | 0 | 0 | 0 | 0 | 9 | 9 |
| prima_nota_module.cassa | 5 | 0 | 0 | 0 | 4 | 9 |
| accounting.contabilita_gestionale | 6 | 0 | 0 | 0 | 3 | 9 |
| accounting.contabilita_avanzata | 7 | 0 | 0 | 0 | 2 | 9 |
| bonifici_module.transfers | 5 | 0 | 0 | 0 | 4 | 9 |
| configurazioni | 8 | 0 | 0 | 0 | 1 | 9 |
| operazioni_module.smart | 6 | 0 | 0 | 0 | 3 | 9 |
| f24_email_settings | 8 | 0 | 0 | 0 | 0 | 8 |
| bonifici_module.associazioni | 7 | 0 | 0 | 0 | 1 | 8 |
| fatture_module.crud | 4 | 0 | 0 | 0 | 4 | 8 |
| reports.simple_exports | 8 | 0 | 0 | 0 | 0 | 8 |
| reports.dashboard | 2 | 0 | 0 | 0 | 6 | 8 |
| cash | 0 | 0 | 0 | 0 | 8 | 8 |
| rapido | 8 | 0 | 0 | 0 | 0 | 8 |
| pos_corrispettivi_check | 6 | 0 | 0 | 0 | 2 | 8 |
| sync_relazionale | 3 | 0 | 5 | 0 | 0 | 8 |
| pagopa | 3 | 5 | 0 | 0 | 0 | 8 |
| agenti | 8 | 0 | 0 | 0 | 0 | 8 |
| f24.email_f24 | 0 | 0 | 0 | 0 | 7 | 7 |
| prima_nota_module.banca | 3 | 0 | 0 | 0 | 4 | 7 |
| accounting.bilancio | 2 | 0 | 0 | 0 | 5 | 7 |
| accounting.regole_categorizzazione | 5 | 0 | 0 | 0 | 2 | 7 |
| gestione_riservata | 5 | 0 | 0 | 0 | 2 | 7 |
| verifica_coerenza | 4 | 0 | 0 | 0 | 3 | 7 |
| controllo_gestione | 1 | 0 | 0 | 0 | 6 | 7 |
| chiusura_esercizio | 6 | 0 | 0 | 0 | 1 | 7 |
| alerts | 4 | 0 | 0 | 0 | 3 | 7 |
| learning_machine | 2 | 0 | 0 | 0 | 5 | 7 |
| documenti_non_associati | 6 | 0 | 0 | 0 | 1 | 7 |
| trattenute_verbali | 0 | 0 | 0 | 0 | 7 | 7 |
| legal_pages | 0 | 0 | 0 | 0 | 6 | 6 |
| batch_operations | 0 | 0 | 0 | 0 | 6 | 6 |
| bank.bank_statement_import | 1 | 0 | 0 | 0 | 5 | 6 |
| bonifici_module.riconciliazione | 3 | 0 | 0 | 0 | 3 | 6 |
| bank.assegni_learning | 4 | 0 | 0 | 0 | 2 | 6 |
| f24_parser | 0 | 0 | 0 | 0 | 6 | 6 |
| settings | 2 | 0 | 0 | 0 | 4 | 6 |
| scadenzario_fornitori | 2 | 0 | 0 | 0 | 4 | 6 |
| openapi_imprese | 3 | 3 | 0 | 0 | 0 | 6 |
| openapi_automotive | 3 | 3 | 0 | 0 | 0 | 6 |
| multi_pagamento | 1 | 0 | 0 | 0 | 5 | 6 |
| app.main | 2 | 0 | 0 | 4 | 0 | 6 |
| whatsapp_webhook | 0 | 5 | 0 | 0 | 0 | 5 |
| bank.riconciliazione_f24_banca | 0 | 0 | 0 | 0 | 5 | 5 |
| bank.pos_accredito | 0 | 0 | 0 | 0 | 5 | 5 |
| invoices.invoices_emesse | 0 | 0 | 0 | 0 | 5 | 5 |
| reports.exports | 1 | 0 | 0 | 0 | 4 | 5 |
| suppliers_module.validation | 0 | 0 | 0 | 0 | 5 | 5 |
| admin_rollback | 5 | 0 | 0 | 0 | 0 | 5 |
| batch_reprocessing | 2 | 0 | 3 | 0 | 0 | 5 |
| learning_universal | 3 | 0 | 0 | 0 | 2 | 5 |
| previsioni_acquisti | 3 | 0 | 0 | 0 | 2 | 5 |
| email_scanner | 2 | 0 | 0 | 0 | 3 | 5 |
| documents_inbox_classify | 3 | 0 | 0 | 0 | 2 | 5 |
| f24_analisi | 1 | 0 | 0 | 0 | 3 | 4 |
| prima_nota_module.stats | 2 | 0 | 0 | 0 | 2 | 4 |
| prima_nota_module.salari | 1 | 0 | 0 | 0 | 3 | 4 |
| prima_nota_module.attese | 2 | 0 | 0 | 0 | 2 | 4 |
| bonifici_module.jobs | 0 | 0 | 0 | 0 | 4 | 4 |
| invoices.invoices_main | 2 | 0 | 0 | 0 | 2 | 4 |
| drive_cedolini | 0 | 0 | 0 | 0 | 4 | 4 |
| reports.report_pdf | 0 | 0 | 0 | 0 | 4 | 4 |
| suppliers_module.bulk | 0 | 0 | 0 | 0 | 4 | 4 |
| finanziaria | 1 | 0 | 0 | 0 | 3 | 4 |
| auth | 2 | 0 | 0 | 0 | 1 | 3 |
| prima_nota_module | 3 | 0 | 0 | 0 | 0 | 3 |
| invoices.fatture_drive | 2 | 0 | 0 | 0 | 1 | 3 |
| drive_corrispettivi | 0 | 0 | 0 | 0 | 3 | 3 |
| drive_quietanze | 0 | 0 | 0 | 0 | 3 | 3 |
| suppliers_module.iban | 0 | 0 | 0 | 0 | 3 | 3 |
| settings_router | 3 | 0 | 0 | 0 | 0 | 3 |
| pianificazione | 0 | 0 | 0 | 0 | 3 | 3 |
| mutui_parser | 0 | 0 | 0 | 0 | 3 | 3 |
| partite_aperte_api | 1 | 0 | 0 | 0 | 2 | 3 |
| pin_login | 1 | 0 | 0 | 0 | 1 | 2 |
| erp_bridge | 0 | 2 | 0 | 0 | 0 | 2 |
| distinte_bpm | 0 | 0 | 0 | 0 | 2 | 2 |
| documenti_fiscali | 2 | 0 | 0 | 0 | 0 | 2 |
| suppliers_module.import_export | 0 | 0 | 0 | 0 | 2 | 2 |
| chat_router | 1 | 0 | 0 | 0 | 1 | 2 |
| admin_export | 0 | 0 | 2 | 0 | 0 | 2 |
| bank.bonifici_import_unificato | 0 | 0 | 0 | 0 | 1 | 1 |
| operazioni_module | 1 | 0 | 0 | 0 | 0 | 1 |
| auto_repair | 1 | 0 | 0 | 0 | 0 | 1 |
| anagrafica_fornitori_xml | 1 | 0 | 0 | 0 | 0 | 1 |
| websocket_realtime | 0 | 1 | 0 | 0 | 0 | 1 |
| riconciliazione_stats_api | 1 | 0 | 0 | 0 | 0 | 1 |

## Endpoint DA VERIFICARE (orfani senza categoria nota)

Nessuna pagina li chiama e non appartengono a integrazione/manutenzione/sistema.
Candidati legacy: la rimozione va decisa caso per caso.

### employees.dipendenti (50)
- `POST /api/dipendenti` — app/utils/error_handler.py:716
- `POST /api/dipendenti/bulk-upsert` — app/utils/error_handler.py:392
- `POST /api/dipendenti/bulk-upsert/preview` — app/utils/error_handler.py:574
- `GET /api/dipendenti/buste-paga` — app/utils/error_handler.py:825
- `POST /api/dipendenti/buste-paga` — app/utils/error_handler.py:848
- `GET /api/dipendenti/buste-paga/dipendente/{dipendente_id}` — app/utils/error_handler.py:2410
- `POST /api/dipendenti/buste-paga/dipendente/{dipendente_id}/import` — app/utils/error_handler.py:2473
- `POST /api/dipendenti/buste-paga/import` — app/utils/error_handler.py:2289
- `GET /api/dipendenti/buste-paga/scan` — app/utils/error_handler.py:2256
- `GET /api/dipendenti/by-google-email` — app/routers/employees/dipendenti.py:91
- `GET /api/dipendenti/contratti` — app/utils/error_handler.py:920
- `POST /api/dipendenti/contratti` — app/utils/error_handler.py:1952
- `POST /api/dipendenti/contratti/import-excel` — app/utils/error_handler.py:2127
- `GET /api/dipendenti/contratti/scadenze` — app/utils/error_handler.py:2089
- `PUT /api/dipendenti/contratti/{contratto_id}` — app/utils/error_handler.py:2012
- `DELETE /api/dipendenti/contratti/{contratto_id}` — app/utils/error_handler.py:2078
- `POST /api/dipendenti/contratti/{contratto_id}/termina` — app/utils/error_handler.py:2041
- `GET /api/dipendenti/duplicati` — app/utils/error_handler.py:140
- `POST /api/dipendenti/duplicati/auto-merge` — app/utils/error_handler.py:174
- `POST /api/dipendenti/duplicati/merge` — app/utils/error_handler.py:151
- `POST /api/dipendenti/invita-multipli` — app/utils/error_handler.py:1287
- `POST /api/dipendenti/libretti-sanitari` — app/utils/error_handler.py:1317
- `GET /api/dipendenti/libretti-sanitari/all` — app/utils/error_handler.py:1307
- `POST /api/dipendenti/libretti-sanitari/genera-da-dipendenti` — app/utils/error_handler.py:1885
- `POST /api/dipendenti/libretti-sanitari/import-excel` — app/utils/error_handler.py:1711
- `GET /api/dipendenti/libretti-sanitari/scadenze` — app/utils/error_handler.py:1855
- `PUT /api/dipendenti/libretti-sanitari/{libretto_id}` — app/utils/error_handler.py:1342
- `DELETE /api/dipendenti/libretti-sanitari/{libretto_id}` — app/utils/error_handler.py:1363
- `GET /api/dipendenti/libretti/scadenze` — app/utils/error_handler.py:1214
- `GET /api/dipendenti/libro-unico/export-excel` — app/utils/error_handler.py:1581
- `GET /api/dipendenti/libro-unico/presenze` — app/utils/error_handler.py:1379
- `GET /api/dipendenti/libro-unico/salaries` — app/utils/error_handler.py:1393
- `PUT /api/dipendenti/libro-unico/salaries/{salary_id}` — app/utils/error_handler.py:1640
- `DELETE /api/dipendenti/libro-unico/salaries/{salary_id}` — app/utils/error_handler.py:1669
- `POST /api/dipendenti/libro-unico/upload` — app/utils/error_handler.py:1408
- `GET /api/dipendenti/mansioni` — app/utils/error_handler.py:378
- `GET /api/dipendenti/portale/stats` — app/utils/error_handler.py:1687
- `GET /api/dipendenti/report-ferie-permessi-tutti` — app/utils/error_handler.py:189
- `GET /api/dipendenti/stats` — app/utils/error_handler.py:107
- `POST /api/dipendenti/sync-iban` — app/utils/error_handler.py:330
- `GET /api/dipendenti/tipi-contratto` — app/utils/error_handler.py:385
- `GET /api/dipendenti/tipi-turno` — app/utils/error_handler.py:371
- `POST /api/dipendenti/turni/salva` — app/utils/error_handler.py:1188
- `GET /api/dipendenti/turni/settimana` — app/utils/error_handler.py:1149
- `GET /api/dipendenti/{dipendente_id}` — app/utils/error_handler.py:942
- `PUT /api/dipendenti/{dipendente_id}` — app/utils/error_handler.py:959
- `DELETE /api/dipendenti/{dipendente_id}` — app/utils/error_handler.py:1109
- `POST /api/dipendenti/{dipendente_id}/invita-portale` — app/utils/error_handler.py:1266
- `PUT /api/dipendenti/{dipendente_id}/libretto` — app/utils/error_handler.py:1237
- `GET /api/dipendenti/{dipendente_id}/report-ferie-permessi` — app/utils/error_handler.py:2574

### email_download (39)
- `POST /api/email-download/associa-documento` — app/routers/email_download.py:127
- `POST /api/email-download/associa-f24-filesystem` — app/routers/email_download.py:582
- `POST /api/email-download/auto-associa` — app/routers/email_download.py:153
- `POST /api/email-download/auto-associa-v2` — app/routers/email_download.py:168
- `GET /api/email-download/confronto-pos` — app/routers/email_download.py:734
- `GET /api/email-download/dizionario-email` — app/routers/email_download.py:1031
- `DELETE /api/email-download/dizionario-email/reset` — app/routers/email_download.py:1042
- `GET /api/email-download/documenti-non-associati` — app/routers/email_download.py:110
- `GET /api/email-download/documents-inbox-stats` — app/routers/email_download.py:555
- `POST /api/email-download/download-single-day` — app/routers/email_download.py:91
- `POST /api/email-download/estrai-importi-verbali` — app/routers/email_download.py:747
- `POST /api/email-download/fix-numeri-verbali` — app/routers/email_download.py:761
- `GET /api/email-download/inbox-documents` — app/routers/email_download.py:836
- `GET /api/email-download/mittenti` — app/routers/email_download.py:904
- `POST /api/email-download/mittenti` — app/routers/email_download.py:948
- `GET /api/email-download/mittenti/check` — app/routers/email_download.py:917
- `DELETE /api/email-download/mittenti/{mittente_id}` — app/routers/email_download.py:981
- `PUT /api/email-download/mittenti/{mittente_id}` — app/routers/email_download.py:998
- `POST /api/email-download/parse-f24-llm` — app/routers/email_download.py:646
- `POST /api/email-download/parse-verbali-llm` — app/routers/email_download.py:631
- `GET /api/email-download/paypal-transazioni` — app/routers/email_download.py:715
- `GET /api/email-download/pdf/{collection}/{pdf_id}` — app/routers/email_download.py:803
- `POST /api/email-download/popola-pdf-payslips` — app/routers/email_download.py:539
- `POST /api/email-download/processa-cedolini` — app/routers/email_download.py:597
- `POST /api/email-download/processa-fatture-email` — app/routers/email_download.py:186
- `POST /api/email-download/processa-fatture-email/batch` — app/routers/email_download.py:359
- `GET /api/email-download/processa-fatture-email/status` — app/routers/email_download.py:353
- `POST /api/email-download/processa-pipeline` — app/routers/email_download.py:614
- `DELETE /api/email-download/pulisci-duplicati` — app/routers/email_download.py:869
- `POST /api/email-download/riconcilia-paypal` — app/routers/email_download.py:703
- `POST /api/email-download/riconcilia-verbali` — app/routers/email_download.py:662
- `POST /api/email-download/riconcilia-verbali-avanzato` — app/routers/email_download.py:687
- `POST /api/email-download/riconciliazione-completa` — app/routers/email_download.py:724
- `POST /api/email-download/scarica-pdf-verbali-mancanti` — app/routers/email_download.py:675
- `POST /api/email-download/start-full-download` — app/routers/email_download.py:44
- `GET /api/email-download/statistiche` — app/routers/email_download.py:779
- `GET /api/email-download/status` — app/routers/email_download.py:38
- `POST /api/email-download/sync-email-now` — app/routers/email_download.py:1050
- `POST /api/email-download/sync-filesystem` — app/routers/email_download.py:566

### documenti (23)
- `GET /api/documenti/cartelle-email` — app/utils/error_handler.py:603
- `GET /api/documenti/categorie` — app/utils/error_handler.py:355
- `GET /api/documenti/confronto-cedolini-prima-nota` — app/utils/error_handler.py:1618
- `GET /api/documenti/documento/{doc_id}` — app/utils/error_handler.py:373
- `POST /api/documenti/elimina-processati` — app/utils/error_handler.py:525
- `GET /api/documenti/lock-status` — app/utils/error_handler.py:202
- `POST /api/documenti/monitor/start` — app/utils/error_handler.py:36
- `GET /api/documenti/monitor/status` — app/utils/error_handler.py:69
- `POST /api/documenti/monitor/stop` — app/utils/error_handler.py:57
- `POST /api/documenti/monitor/sync-now` — app/utils/error_handler.py:89
- `POST /api/documenti/processa-f24-scaricati` — app/utils/error_handler.py:917
- `POST /api/documenti/processa-tutti` — app/utils/error_handler.py:1937
- `POST /api/documenti/reimporta-da-filesystem` — app/utils/error_handler.py:1991
- `POST /api/documenti/ricategorizza-documenti` — app/utils/error_handler.py:1866
- `POST /api/documenti/riepilogo-cedolini` — app/utils/error_handler.py:1423
- `GET /api/documenti/riepilogo-cedolini` — app/utils/error_handler.py:1553
- `POST /api/documenti/scarica-da-email` — app/utils/error_handler.py:247
- `POST /api/documenti/sync-buste-paga` — app/utils/error_handler.py:1218
- `POST /api/documenti/sync-estratti-bnl` — app/utils/error_handler.py:1705
- `POST /api/documenti/sync-estratti-conto` — app/utils/error_handler.py:1057
- `GET /api/documenti/telegram/status` — app/utils/error_handler.py:103
- `POST /api/documenti/telegram/test` — app/utils/error_handler.py:119
- `GET /api/documenti/ultimo-sync` — app/utils/error_handler.py:1024

### f24.f24_main (21)
- `POST /api/f24` — app/routers/f24/f24_main.py:339
- `GET /api/f24/alerts/scadenze` — app/routers/f24/f24_main.py:545
- `GET /api/f24/codici/all` — app/routers/f24/f24_main.py:794
- `GET /api/f24/codici/{codice}` — app/routers/f24/f24_main.py:813
- `GET /api/f24/dashboard/summary` — app/routers/f24/f24_main.py:625
- `GET /api/f24/documents` — app/routers/f24/f24_main.py:261
- `DELETE /api/f24/documents/{doc_id}` — app/routers/f24/f24_main.py:279
- `GET /api/f24/quietanze` — app/routers/f24/f24_main.py:924
- `GET /api/f24/quietanze/statistiche/tributi` — app/routers/f24/f24_main.py:1029
- `POST /api/f24/quietanze/upload` — app/routers/f24/f24_main.py:834
- `GET /api/f24/quietanze/{f24_id}` — app/routers/f24/f24_main.py:989
- `DELETE /api/f24/quietanze/{f24_id}` — app/routers/f24/f24_main.py:1007
- `POST /api/f24/riconcilia` — app/routers/f24/f24_main.py:704
- `POST /api/f24/upload` — app/routers/f24/f24_main.py:483
- `POST /api/f24/upload-multiple` — app/routers/f24/f24_main.py:161
- `POST /api/f24/upload-pdf` — app/routers/f24/f24_main.py:386
- `POST /api/f24/upload-zip` — app/routers/f24/f24_main.py:50
- `PUT /api/f24/{f24_id}` — app/routers/f24/f24_main.py:510
- `DELETE /api/f24/{f24_id}` — app/routers/f24/f24_main.py:530
- `GET /api/f24/{f24_id}` — app/routers/f24/f24_main.py:498
- `POST /api/f24/{f24_id}/mark-paid` — app/routers/f24/f24_main.py:764

### verbali_riconciliazione (21)
- `POST /api/verbali-riconciliazione/associa-fattura` — app/utils/error_handler.py:243
- `POST /api/verbali-riconciliazione/automazione-completa` — app/utils/error_handler.py:1026
- `POST /api/verbali-riconciliazione/crea-prima-nota-verbale/{numero_verbale}` — app/utils/error_handler.py:1089
- `GET /api/verbali-riconciliazione/dettaglio-completo/{numero_verbale}` — app/utils/error_handler.py:1678
- `GET /api/verbali-riconciliazione/lista` — app/utils/error_handler.py:162
- `GET /api/verbali-riconciliazione/pending-status` — app/utils/error_handler.py:1168
- `GET /api/verbali-riconciliazione/per-dipendente/{driver_id}` — app/utils/error_handler.py:1244
- `GET /api/verbali-riconciliazione/per-driver/{driver_id}` — app/utils/error_handler.py:838
- `GET /api/verbali-riconciliazione/per-targa/{targa}` — app/utils/error_handler.py:1312
- `GET /api/verbali-riconciliazione/per-veicolo/{targa}` — app/utils/error_handler.py:864
- `GET /api/verbali-riconciliazione/quietanze-verbale/{numero_verbale}` — app/utils/error_handler.py:1815
- `GET /api/verbali-riconciliazione/quietanze-verbale/{numero_verbale}/pdf` — app/utils/error_handler.py:1834
- `POST /api/verbali-riconciliazione/registra-pagamento` — app/utils/error_handler.py:318
- `POST /api/verbali-riconciliazione/registra-quietanza/{numero_verbale}` — app/utils/error_handler.py:1390
- `POST /api/verbali-riconciliazione/riconcilia-estratto-conto-paypal` — app/utils/error_handler.py:1572
- `POST /api/verbali-riconciliazione/scan-email` — app/utils/error_handler.py:1455
- `POST /api/verbali-riconciliazione/scan-email-storico` — app/utils/error_handler.py:1495
- `POST /api/verbali-riconciliazione/scan-pagopa` — app/utils/error_handler.py:1793
- `POST /api/verbali-riconciliazione/scan-verbale/{numero_verbale}` — app/utils/error_handler.py:1525
- `GET /api/verbali-riconciliazione/scheduler-status` — app/utils/error_handler.py:1755
- `GET /api/verbali-riconciliazione/{numero_verbale}/pdf` — app/utils/error_handler.py:1339

### invoices.corrispettivi (20)
- `POST /api/corrispettivi/aggiorna-stati-mancanti` — app/routers/invoices/corrispettivi.py:1680
- `DELETE /api/corrispettivi/all` — app/utils/error_handler.py:408
- `POST /api/corrispettivi/auto-ricostruisci-dati` — app/utils/error_handler.py:856
- `POST /api/corrispettivi/cleanup-duplicati-forte` — app/utils/error_handler.py:827
- `POST /api/corrispettivi/elimina-duplicati` — app/utils/error_handler.py:737
- `POST /api/corrispettivi/hard-delete-bulk` — app/utils/error_handler.py:814
- `DELETE /api/corrispettivi/hard-delete/{corrispettivo_id}` — app/utils/error_handler.py:803
- `POST /api/corrispettivi/import-csv` — app/utils/error_handler.py:573
- `GET /api/corrispettivi/manuali-senza-xml` — app/routers/invoices/corrispettivi.py:1629
- `POST /api/corrispettivi/rebuild-prima-nota` — app/utils/error_handler.py:840
- `POST /api/corrispettivi/ricalcola-annulli-non-riscosso` — app/utils/error_handler.py:85
- `POST /api/corrispettivi/ricalcola-iva` — app/utils/error_handler.py:52
- `POST /api/corrispettivi/sincronizza-prima-nota` — app/utils/error_handler.py:291
- `GET /api/corrispettivi/template-csv` — app/utils/error_handler.py:719
- `GET /api/corrispettivi/totals` — app/utils/error_handler.py:135
- `POST /api/corrispettivi/upload-xml` — app/utils/error_handler.py:171
- `POST /api/corrispettivi/upload-xml-bulk` — app/utils/error_handler.py:222
- `POST /api/corrispettivi/upload-zip` — app/utils/error_handler.py:492
- `GET /api/corrispettivi/view-by-filename` — app/utils/error_handler.py:1268
- `GET /api/corrispettivi/{corrispettivo_id}/view` — app/utils/error_handler.py:1312

### f24.f24_riconciliazione (18)
- `GET /api/f24-riconciliazione/alerts` — app/utils/error_handler.py:629
- `POST /api/f24-riconciliazione/alerts/{alert_id}/conferma-elimina` — app/utils/error_handler.py:656
- `POST /api/f24-riconciliazione/alerts/{alert_id}/ignora` — app/utils/error_handler.py:700
- `GET /api/f24-riconciliazione/commercialista` — app/utils/error_handler.py:390
- `POST /api/f24-riconciliazione/commercialista/upload` — app/utils/error_handler.py:36
- `GET /api/f24-riconciliazione/commercialista/{f24_id}` — app/utils/error_handler.py:504
- `PUT /api/f24-riconciliazione/commercialista/{f24_id}` — app/utils/error_handler.py:525
- `DELETE /api/f24-riconciliazione/commercialista/{f24_id}` — app/utils/error_handler.py:548
- `PUT /api/f24-riconciliazione/commercialista/{f24_id}/pagato` — app/utils/error_handler.py:440
- `GET /api/f24-riconciliazione/commercialista/{f24_id}/pdf` — app/utils/error_handler.py:462
- `GET /api/f24-riconciliazione/dashboard` — app/utils/error_handler.py:806
- `POST /api/f24-riconciliazione/fix-campo-anno` — app/utils/error_handler.py:1266
- `GET /api/f24-riconciliazione/quietanze` — app/utils/error_handler.py:952
- `POST /api/f24-riconciliazione/quietanze/upload-multiplo` — app/utils/error_handler.py:884
- `GET /api/f24-riconciliazione/quietanze/{quietanza_id}` — app/utils/error_handler.py:973
- `POST /api/f24-riconciliazione/riconcilia-quietanza` — app/utils/error_handler.py:257
- `POST /api/f24-riconciliazione/riconcilia-tutto` — app/utils/error_handler.py:986
- `GET /api/f24-riconciliazione/verifica-codice/{codice_tributo}` — app/utils/error_handler.py:724

### verbali_noleggio (17)
- `POST /api/verbali-noleggio/associa-fatture` — app/utils/error_handler.py:266
- `GET /api/verbali-noleggio/cartelle-verbali` — app/utils/error_handler.py:64
- `POST /api/verbali-noleggio/classifica-verbali-posta` — app/utils/error_handler.py:740
- `GET /api/verbali-noleggio/operazioni-sospese` — app/utils/error_handler.py:500
- `POST /api/verbali-noleggio/riclassifica-verbale` — app/utils/error_handler.py:838
- `POST /api/verbali-noleggio/riconcilia` — app/utils/error_handler.py:517
- `POST /api/verbali-noleggio/risolvi-sospeso` — app/utils/error_handler.py:537
- `POST /api/verbali-noleggio/scansiona-fatture` — app/utils/error_handler.py:431
- `POST /api/verbali-noleggio/scarica-tutti` — app/utils/error_handler.py:99
- `GET /api/verbali-noleggio/stats` — app/utils/error_handler.py:413
- `GET /api/verbali-noleggio/tutti-verbali` — app/utils/error_handler.py:657
- `GET /api/verbali-noleggio/verbale/{numero_verbale}` — app/utils/error_handler.py:249
- `GET /api/verbali-noleggio/verbali` — app/utils/error_handler.py:225
- `GET /api/verbali-noleggio/verbali-attesa-fattura` — app/utils/error_handler.py:765
- `GET /api/verbali-noleggio/verbali-completi` — app/utils/error_handler.py:452
- `GET /api/verbali-noleggio/verbali-privati` — app/utils/error_handler.py:796
- `POST /api/verbali-noleggio/verifica-nuove-fatture` — app/utils/error_handler.py:815

### bank.assegni (16)
- `POST /api/assegni/associa-beneficiari-robusto` — app/routers/bank/assegni.py:2061
- `POST /api/assegni/associa-pagamenti-multipli` — app/routers/bank/assegni.py:2194
- `POST /api/assegni/auto-match` — app/routers/bank/assegni.py:618
- `POST /api/assegni/conferma-proposta/{proposta_id}` — app/routers/bank/assegni.py:1568
- `PUT /api/assegni/correggi-associazione/{assegno_id}` — app/routers/bank/assegni.py:518
- `POST /api/assegni/correggi-numeri` — app/routers/bank/assegni.py:2007
- `GET /api/assegni/preview-combinazioni` — app/routers/bank/assegni.py:254
- `GET /api/assegni/proposte-associazione` — app/routers/bank/assegni.py:716
- `POST /api/assegni/pulisci-beneficiari-fittizi` — app/routers/bank/assegni.py:1616
- `POST /api/assegni/rifiuta-proposta/{proposta_id}` — app/routers/bank/assegni.py:1650
- `GET /api/assegni/stati` — app/routers/bank/assegni.py:39
- `POST /api/assegni/sync-da-estratto-conto` — app/routers/bank/assegni.py:1667
- `GET /api/assegni/verifica-associazioni` — app/routers/bank/assegni.py:339
- `GET /api/assegni/{assegno_id}` — app/routers/bank/assegni.py:735
- `POST /api/assegni/{assegno_id}/annulla` — app/routers/bank/assegni.py:1148
- `POST /api/assegni/{assegno_id}/emetti` — app/routers/bank/assegni.py:980

### tfr (16)
- `POST /api/tfr/accantonamento` — app/utils/error_handler.py:107
- `POST /api/tfr/acconti` — app/utils/error_handler.py:641
- `PUT /api/tfr/acconti/{acconto_id}` — app/utils/error_handler.py:787
- `DELETE /api/tfr/acconti/{acconto_id}` — app/utils/error_handler.py:893
- `POST /api/tfr/acconti/{acconto_id}/annulla-riconciliazione-banca` — app/utils/error_handler.py:1165
- `GET /api/tfr/acconti/{acconto_id}/candidati-banca` — app/utils/error_handler.py:928
- `POST /api/tfr/acconti/{acconto_id}/riconcilia-banca` — app/utils/error_handler.py:1096
- `GET /api/tfr/acconti/{dipendente_id}` — app/utils/error_handler.py:576
- `POST /api/tfr/calcola-batch/{anno}` — app/utils/error_handler.py:421
- `POST /api/tfr/cedolini/{cedolino_id}/annulla-scalatura-acconti` — app/utils/error_handler.py:1509
- `GET /api/tfr/cedolini/{cedolino_id}/preview-scalatura-acconti` — app/utils/error_handler.py:1300
- `POST /api/tfr/cedolini/{cedolino_id}/scala-acconti` — app/utils/error_handler.py:1429
- `POST /api/tfr/liquidazione` — app/utils/error_handler.py:211
- `GET /api/tfr/parse-payslips` — app/utils/error_handler.py:1558
- `GET /api/tfr/situazione/{dipendente_id}` — app/utils/error_handler.py:60
- `GET /api/tfr/storico-tfr/{dipendente_id}` — app/utils/error_handler.py:1604

### verbali_noleggio_api (12)
- `GET /api/verbali-noleggio/alert-pagamenti` — app/utils/error_handler.py:183
- `POST /api/verbali-noleggio/associa-driver` — app/utils/error_handler.py:353
- `POST /api/verbali-noleggio/bulk-assegna-pagamento` — app/utils/error_handler.py:494
- `GET /api/verbali-noleggio/lista` — app/utils/error_handler.py:124
- `GET /api/verbali-noleggio/note-consulente` — app/utils/error_handler.py:298
- `POST /api/verbali-noleggio/riconcilia-completo` — app/utils/error_handler.py:461
- `POST /api/verbali-noleggio/scan-gmail` — app/utils/error_handler.py:453
- `POST /api/verbali-noleggio/scarica-posta` — app/utils/error_handler.py:169
- `PUT /api/verbali-noleggio/{verbale_id}` — app/utils/error_handler.py:329
- `POST /api/verbali-noleggio/{verbale_id}/cerca-pagamento` — app/utils/error_handler.py:400
- `GET /api/verbali-noleggio/{verbale_id}/ricevuta-pdf` — app/utils/error_handler.py:432
- `POST /api/verbali-noleggio/{verbale_id}/upload-quietanza` — app/utils/error_handler.py:219

### prima_nota_module.sync (11)
- `POST /api/prima-nota/banca/sync-estratto-conto` — app/routers/prima_nota_module/sync.py:448
- `POST /api/prima-nota/cassa/crea-entrata-da-corrispettivo` — app/routers/prima_nota_module/sync.py:1303
- `POST /api/prima-nota/cassa/sync-fatture-pagate` — app/routers/prima_nota_module/sync.py:329
- `POST /api/prima-nota/collega-fatture` — app/routers/prima_nota_module/sync.py:1081
- `GET /api/prima-nota/corrispettivi-status` — app/routers/prima_nota_module/sync.py:422
- `POST /api/prima-nota/import-batch` — app/routers/prima_nota_module/sync.py:965
- `POST /api/prima-nota/movimento` — app/routers/prima_nota_module/sync.py:1021
- `POST /api/prima-nota/provvisori/annulla-auto-conferma` — app/routers/prima_nota_module/sync.py:1240
- `POST /api/prima-nota/provvisori/conferma-divisione` — app/routers/prima_nota_module/sync.py:803
- `POST /api/prima-nota/registra-fattura` — app/routers/prima_nota_module/sync.py:150
- `POST /api/prima-nota/sync-corrispettivi` — app/routers/prima_nota_module/sync.py:206

### contabilita_italiana (11)
- `POST /api/contabilita/assestamento/rateo-risconto` — app/routers/contabilita_italiana.py:1057
- `GET /api/contabilita/bilancio/conto-economico` — app/routers/contabilita_italiana.py:1199
- `GET /api/contabilita/bilancio/stato-patrimoniale` — app/routers/contabilita_italiana.py:1123
- `POST /api/contabilita/cassa-banca/prelievo` — app/routers/contabilita_italiana.py:736
- `POST /api/contabilita/cassa-banca/versamento` — app/routers/contabilita_italiana.py:697
- `GET /api/contabilita/cespiti` — app/routers/contabilita_italiana.py:675
- `POST /api/contabilita/cespiti/ammortamento` — app/routers/contabilita_italiana.py:569
- `POST /api/contabilita/cespiti/registra` — app/routers/contabilita_italiana.py:477
- `POST /api/contabilita/personale/acconto` — app/routers/contabilita_italiana.py:779
- `POST /api/contabilita/personale/busta-paga` — app/routers/contabilita_italiana.py:840
- `POST /api/contabilita/ritenute/registra` — app/routers/contabilita_italiana.py:968

### dati_provvisori (11)
- `POST /api/conferma-tutte` — app/utils/error_handler.py:441
- `POST /api/conferma/{proposta_id}` — app/utils/error_handler.py:432
- `GET /api/dati-provvisori` — app/utils/error_handler.py:33
- `POST /api/dati-provvisori/riconcilia-estratto-conto` — app/utils/error_handler.py:310
- `POST /api/dati-provvisori/sposta-banca` — app/utils/error_handler.py:119
- `POST /api/dati-provvisori/sposta-cassa` — app/utils/error_handler.py:61
- `POST /api/dati-provvisori/upload-xml` — app/utils/error_handler.py:202
- `DELETE /api/dati-provvisori/{dato_id}` — app/utils/error_handler.py:179
- `POST /api/genera-proposte` — app/utils/error_handler.py:396
- `GET /api/proposte` — app/utils/error_handler.py:409
- `POST /api/rifiuta/{proposta_id}` — app/utils/error_handler.py:450

### ai_parser (11)
- `POST /api/ai-parser/batch-parse` — app/routers/ai_parser.py:323
- `GET /api/ai-parser/da-rivedere` — app/routers/ai_parser.py:400
- `POST /api/ai-parser/da-rivedere/process-batch` — app/routers/ai_parser.py:445
- `PUT /api/ai-parser/da-rivedere/{document_id}/classifica` — app/routers/ai_parser.py:465
- `POST /api/ai-parser/parse` — app/routers/ai_parser.py:26
- `POST /api/ai-parser/parse-busta-paga` — app/routers/ai_parser.py:244
- `POST /api/ai-parser/parse-f24` — app/routers/ai_parser.py:178
- `POST /api/ai-parser/parse-fattura` — app/routers/ai_parser.py:112
- `POST /api/ai-parser/process-email-batch` — app/routers/ai_parser.py:495
- `GET /api/ai-parser/statistiche` — app/routers/ai_parser.py:516
- `GET /api/ai-parser/test` — app/routers/ai_parser.py:372

### warehouse.dizionario_articoli (10)
- `PUT /api/dizionario-articoli/articolo/{descrizione_encoded}` — app/routers/warehouse/dizionario_articoli.py:786
- `POST /api/dizionario-articoli/categorizza-ai` — app/routers/warehouse/dizionario_articoli.py:983
- `GET /api/dizionario-articoli/cerca` — app/routers/warehouse/dizionario_articoli.py:951
- `GET /api/dizionario-articoli/dizionario` — app/routers/warehouse/dizionario_articoli.py:673
- `GET /api/dizionario-articoli/estrai-articoli` — app/routers/warehouse/dizionario_articoli.py:591
- `POST /api/dizionario-articoli/genera-dizionario` — app/routers/warehouse/dizionario_articoli.py:706
- `GET /api/dizionario-articoli/non-classificati` — app/routers/warehouse/dizionario_articoli.py:1003
- `DELETE /api/dizionario-articoli/reset-dizionario` — app/routers/warehouse/dizionario_articoli.py:969
- `POST /api/dizionario-articoli/ricategorizza-fatture` — app/routers/warehouse/dizionario_articoli.py:890
- `GET /api/dizionario-articoli/statistiche` — app/routers/warehouse/dizionario_articoli.py:837

### invoices.fatture_upload (10)
- `DELETE /api/fatture/all` — app/utils/error_handler.py:1243
- `POST /api/fatture/categorize-movements` — app/utils/error_handler.py:1362
- `POST /api/fatture/recalculate-iva` — app/utils/error_handler.py:1675
- `POST /api/fatture/sync-suppliers` — app/utils/error_handler.py:1259
- `POST /api/fatture/upload-xml` — app/utils/error_handler.py:984
- `POST /api/fatture/upload-xml-bulk` — app/utils/error_handler.py:1175
- `GET /api/fatture/{invoice_id}` — app/utils/error_handler.py:1450
- `PUT /api/fatture/{invoice_id}` — app/utils/error_handler.py:1458
- `PUT /api/fatture/{invoice_id}/classifica` — app/utils/error_handler.py:1466
- `GET /api/fatture/{invoice_id}/entita-correlate` — app/utils/error_handler.py:1643

### libro_unico_parser (10)
- `GET /api/paghe/acconti` — app/routers/libro_unico_parser.py:1139
- `POST /api/paghe/acconti/{busta_id}` — app/routers/libro_unico_parser.py:1175
- `DELETE /api/paghe/acconti/{busta_id}/{acconto_id}` — app/routers/libro_unico_parser.py:1224
- `GET /api/paghe/buste-paga` — app/routers/libro_unico_parser.py:1040
- `POST /api/paghe/import-libro-unico` — app/routers/libro_unico_parser.py:649
- `POST /api/paghe/parse-libro-unico` — app/routers/libro_unico_parser.py:499
- `POST /api/paghe/parse-libro-unico/dipendente/{indice}` — app/routers/libro_unico_parser.py:532
- `GET /api/paghe/presenze-mensili` — app/routers/libro_unico_parser.py:1082
- `GET /api/paghe/presenze-mensili/{codice_fiscale}/{periodo}` — app/routers/libro_unico_parser.py:1114
- `POST /api/paghe/riconcilia-stipendi` — app/routers/libro_unico_parser.py:1017

### f24.f24_public (9)
- `GET /api/f24-public/models` — app/utils/error_handler.py:31
- `PUT /api/f24-public/models/{f24_id}` — app/utils/error_handler.py:527
- `DELETE /api/f24-public/models/{f24_id}` — app/utils/error_handler.py:558
- `PUT /api/f24-public/models/{f24_id}/pagato` — app/utils/error_handler.py:510
- `GET /api/f24-public/pdf/{f24_id}` — app/utils/error_handler.py:445
- `GET /api/f24-public/scadenze-prossime` — app/utils/error_handler.py:147
- `GET /api/f24-public/test` — app/utils/error_handler.py:24
- `POST /api/f24-public/upload` — app/utils/error_handler.py:237
- `POST /api/f24-public/upload-overwrite` — app/utils/error_handler.py:576

### accounting.centri_costo (9)
- `GET /api/centri-costo` — app/routers/accounting/centri_costo.py:114
- `POST /api/centri-costo` — app/routers/accounting/centri_costo.py:160
- `POST /api/centri-costo/assegna-cdc-fatture` — app/routers/accounting/centri_costo.py:197
- `GET /api/centri-costo/mapping-categorie` — app/routers/accounting/centri_costo.py:187
- `POST /api/centri-costo/ribaltamento/aggiorna-chiavi` — app/routers/accounting/centri_costo.py:712
- `POST /api/centri-costo/ribaltamento/calcola` — app/routers/accounting/centri_costo.py:612
- `GET /api/centri-costo/ribaltamento/chiavi` — app/routers/accounting/centri_costo.py:602
- `GET /api/centri-costo/utile-obiettivo/per-cdc` — app/routers/accounting/centri_costo.py:486
- `GET /api/centri-costo/utile-obiettivo/suggerimenti` — app/routers/accounting/centri_costo.py:398

### iva (9)
- `GET /api/iva/fatture` — app/routers/iva.py:133
- `POST /api/iva/fatture/{fid}/correggi-periodo` — app/routers/iva.py:665
- `POST /api/iva/fatture/{fid}/escludi` — app/routers/iva.py:621
- `POST /api/iva/fatture/{fid}/includi` — app/routers/iva.py:630
- `POST /api/iva/fatture/{fid}/indetraibile` — app/routers/iva.py:648
- `POST /api/iva/fatture/{fid}/recupero-annuale` — app/routers/iva.py:657
- `POST /api/iva/fatture/{fid}/rinvia` — app/routers/iva.py:639
- `GET /api/iva/liquidazioni` — app/routers/iva.py:460
- `POST /api/iva/liquidazioni/{liq_id}/rettifica` — app/routers/iva.py:423

### suppliers_module.base (9)
- `GET /api/suppliers/scadenze` — app/routers/suppliers_module/base.py:301
- `GET /api/suppliers/stats` — app/routers/suppliers_module/base.py:280
- `GET /api/suppliers/{supplier_id}` — app/routers/suppliers_module/base.py:443
- `DELETE /api/suppliers/{supplier_id}` — app/routers/suppliers_module/base.py:690
- `GET /api/suppliers/{supplier_id}/dati-da-fatture` — app/routers/suppliers_module/base.py:1141
- `GET /api/suppliers/{supplier_id}/iban-from-invoices` — app/routers/suppliers_module/base.py:881
- `PUT /api/suppliers/{supplier_id}/metodo-pagamento` — app/routers/suppliers_module/base.py:928
- `PUT /api/suppliers/{supplier_id}/nome` — app/routers/suppliers_module/base.py:973
- `POST /api/suppliers/{supplier_id}/toggle-active` — app/routers/suppliers_module/base.py:639

### fiscalita_italiana (8)
- `GET /api/fiscalita/agevolazioni` — app/routers/fiscalita_italiana.py:632
- `POST /api/fiscalita/agevolazioni/simula` — app/routers/fiscalita_italiana.py:682
- `GET /api/fiscalita/agevolazioni/{agevolazione_id}` — app/routers/fiscalita_italiana.py:666
- `POST /api/fiscalita/apertura-esercizio` — app/routers/fiscalita_italiana.py:1297
- `GET /api/fiscalita/calendario/scadenze-imminenti` — app/routers/fiscalita_italiana.py:731
- `POST /api/fiscalita/chiusura-esercizio` — app/routers/fiscalita_italiana.py:1144
- `POST /api/fiscalita/f24/registra` — app/routers/fiscalita_italiana.py:1002
- `GET /api/fiscalita/f24/storico` — app/routers/fiscalita_italiana.py:1116

### bank.estratto_conto (8)
- `GET /api/estratto-conto-movimenti/categorie` — app/utils/error_handler.py:991
- `DELETE /api/estratto-conto-movimenti/clear` — app/utils/error_handler.py:1075
- `GET /api/estratto-conto-movimenti/export-excel` — app/utils/error_handler.py:1109
- `GET /api/estratto-conto-movimenti/fornitori` — app/utils/error_handler.py:1000
- `GET /api/estratto-conto-movimenti/movimenti-stipendi` — app/utils/error_handler.py:1445
- `POST /api/estratto-conto-movimenti/ricategorizza-batch` — app/utils/error_handler.py:1500
- `POST /api/estratto-conto-movimenti/riconcilia-stipendi` — app/utils/error_handler.py:1283
- `GET /api/estratto-conto-movimenti/riepilogo` — app/utils/error_handler.py:1009

### fatture_module.pagamento (8)
- `POST /api/fatture-ricevute/aggiorna-metodi-pagamento` — app/routers/fatture_module/pagamento.py:296
- `POST /api/fatture-ricevute/backfill-autoroute` — app/routers/fatture_module/pagamento.py:369
- `POST /api/fatture-ricevute/cambia-metodo-pagamento` — app/routers/fatture_module/pagamento.py:131
- `POST /api/fatture-ricevute/import-paypal` — app/routers/fatture_module/pagamento.py:635
- `GET /api/fatture-ricevute/lista-paypal` — app/routers/fatture_module/pagamento.py:606
- `POST /api/fatture-ricevute/riconcilia-con-estratto-conto` — app/routers/fatture_module/pagamento.py:184
- `POST /api/fatture-ricevute/riconcilia-paypal` — app/routers/fatture_module/pagamento.py:563
- `GET /api/fatture-ricevute/verifica-incoerenze-estratto-conto` — app/routers/fatture_module/pagamento.py:259

### cash (8)
- `POST /api/cash/corrispettivi` — app/routers/cash.py:227
- `GET /api/cash/corrispettivi/{target_date}` — app/routers/cash.py:277
- `GET /api/cash/export/excel` — app/routers/cash.py:305
- `GET /api/cash/movements` — app/routers/cash.py:43
- `POST /api/cash/movements` — app/routers/cash.py:85
- `PUT /api/cash/movements/{movement_id}` — app/routers/cash.py:127
- `DELETE /api/cash/movements/{movement_id}` — app/routers/cash.py:166
- `GET /api/cash/stats` — app/routers/cash.py:191

### f24.email_f24 (7)
- `GET /api/f24-email/allegati` — app/routers/f24/email_f24.py:257
- `GET /api/f24-email/codici-tributo` — app/routers/f24/email_f24.py:294
- `GET /api/f24-email/log-download` — app/routers/f24/email_f24.py:282
- `GET /api/f24-email/mittenti` — app/routers/f24/email_f24.py:248
- `POST /api/f24-email/processa-allegati` — app/routers/f24/email_f24.py:99
- `POST /api/f24-email/scarica-e-processa` — app/routers/f24/email_f24.py:333
- `POST /api/f24-email/scarica-email` — app/routers/f24/email_f24.py:31

### prima_nota_module.manutenzione (7)
- `POST /api/prima-nota/cleanup-orphan-movements` — app/routers/prima_nota_module/manutenzione.py:132
- `POST /api/prima-nota/fix-categories-and-duplicates` — app/routers/prima_nota_module/manutenzione.py:287
- `POST /api/prima-nota/fix-tipo-movimento` — app/routers/prima_nota_module/manutenzione.py:25
- `POST /api/prima-nota/fix-versamenti-duplicati` — app/routers/prima_nota_module/manutenzione.py:240
- `POST /api/prima-nota/migrazione-pulisci-bancari-cassa` — app/routers/prima_nota_module/manutenzione.py:563
- `POST /api/prima-nota/recalculate-balances` — app/routers/prima_nota_module/manutenzione.py:83
- `POST /api/prima-nota/regenerate-from-invoices` — app/routers/prima_nota_module/manutenzione.py:168

### commercialista (7)
- `GET /api/commercialista/export-completo/{anno}/{mese}` — app/utils/error_handler.py:621
- `GET /api/commercialista/export-excel/{anno}/{mese}` — app/utils/error_handler.py:774
- `GET /api/commercialista/export-log` — app/utils/error_handler.py:1251
- `POST /api/commercialista/invia-carnet` — app/utils/error_handler.py:355
- `POST /api/commercialista/invia-fatture-cassa` — app/utils/error_handler.py:439
- `POST /api/commercialista/invia-prima-nota` — app/utils/error_handler.py:256
- `POST /api/commercialista/schedula-export` — app/utils/error_handler.py:1074

### mutui (7)
- `GET /api/mutui` — app/routers/mutui.py:104
- `POST /api/mutui/` — app/routers/mutui.py:563
- `GET /api/mutui/{mutuo_id}` — app/routers/mutui.py:214
- `PUT /api/mutui/{mutuo_id}` — app/routers/mutui.py:599
- `DELETE /api/mutui/{mutuo_id}` — app/routers/mutui.py:635
- `GET /api/mutui/{mutuo_id}/rate` — app/routers/mutui.py:242
- `PUT /api/mutui/{mutuo_id}/rate/{numero_rata}/riconcilia` — app/routers/mutui.py:473

### trattenute_verbali (7)
- `GET /api/trattenute-verbali/` — app/utils/error_handler.py:64
- `GET /api/trattenute-verbali/report-consulente` — app/utils/error_handler.py:301
- `POST /api/trattenute-verbali/retro-verifica` — app/utils/error_handler.py:285
- `POST /api/trattenute-verbali/{trattenuta_id}/comunica` — app/utils/error_handler.py:153
- `POST /api/trattenute-verbali/{trattenuta_id}/conferma` — app/utils/error_handler.py:100
- `POST /api/trattenute-verbali/{trattenuta_id}/escludi` — app/utils/error_handler.py:242
- `POST /api/trattenute-verbali/{trattenuta_id}/rimanda` — app/utils/error_handler.py:192

### legal_pages (6)
- `GET /api/data-deletion` — app/routers/legal_pages.py:138
- `GET /api/privacy` — app/routers/legal_pages.py:124
- `GET /api/terms` — app/routers/legal_pages.py:131
- `GET /data-deletion` — app/routers/legal_pages.py:138
- `GET /privacy` — app/routers/legal_pages.py:124
- `GET /terms` — app/routers/legal_pages.py:131

### accounting.piano_conti (6)
- `GET /api/piano-conti/movimenti` — app/utils/error_handler.py:1030
- `POST /api/piano-conti/registra-corrispettivi` — app/utils/error_handler.py:1228
- `POST /api/piano-conti/registra-fattura` — app/utils/error_handler.py:634
- `POST /api/piano-conti/registra-tutte-fatture` — app/utils/error_handler.py:1130
- `PUT /api/piano-conti/{conto_id}` — app/utils/error_handler.py:507
- `DELETE /api/piano-conti/{conto_id}` — app/utils/error_handler.py:532

### batch_operations (6)
- `POST /api/batch/auto-riconcilia-tutto` — app/routers/batch_operations.py:178
- `POST /api/batch/categorizza` — app/routers/batch_operations.py:126
- `POST /api/batch/chiudi-scadenze` — app/routers/batch_operations.py:158
- `POST /api/batch/paga` — app/routers/batch_operations.py:81
- `POST /api/batch/processa-fatture-pendenti` — app/routers/batch_operations.py:273
- `POST /api/batch/riconcilia` — app/routers/batch_operations.py:39

### paypal_statements (6)
- `POST /api/paypal-statements/auto-associa` — app/routers/paypal_statements.py:881
- `POST /api/paypal-statements/auto-cerca-gmail` — app/routers/paypal_statements.py:951
- `POST /api/paypal-statements/import-all-local` — app/routers/paypal_statements.py:279
- `POST /api/paypal-statements/import-pdf` — app/routers/paypal_statements.py:249
- `POST /api/paypal-statements/riconcilia-banca` — app/routers/paypal_statements.py:355
- `POST /api/paypal-statements/transazione/{transaction_id}/associa` — app/routers/paypal_statements.py:835

### f24_parser (6)
- `GET /api/paghe/distinte-f24` — app/routers/f24_parser.py:772
- `GET /api/paghe/f24/lista` — app/routers/f24_parser.py:800
- `POST /api/paghe/import-f24` — app/routers/f24_parser.py:396
- `POST /api/paghe/parse-f24` — app/routers/f24_parser.py:314
- `POST /api/paghe/riconcilia-f24` — app/routers/f24_parser.py:710
- `GET /api/paghe/tributi-pagati` — app/routers/f24_parser.py:732

### reports.dashboard (6)
- `GET /api/dashboard/bilancio-istantaneo` — app/routers/reports/dashboard.py:577
- `GET /api/dashboard/confronto-annuale` — app/routers/reports/dashboard.py:414
- `GET /api/dashboard/kpi` — app/routers/reports/dashboard.py:118
- `GET /api/dashboard/spese-per-categoria` — app/routers/reports/dashboard.py:332
- `GET /api/dashboard/stato-riconciliazione` — app/routers/reports/dashboard.py:491
- `GET /api/dashboard/stats` — app/routers/reports/dashboard.py:161

### controllo_gestione (6)
- `POST /api/controllo-gestione/budget` — app/utils/error_handler.py:268
- `GET /api/controllo-gestione/budget-vs-consuntivo/{anno}` — app/utils/error_handler.py:327
- `GET /api/controllo-gestione/budget/{anno}` — app/utils/error_handler.py:302
- `GET /api/controllo-gestione/costi-per-categoria` — app/utils/error_handler.py:192
- `GET /api/controllo-gestione/kpi/{anno}` — app/utils/error_handler.py:386
- `GET /api/controllo-gestione/trend-mensile` — app/utils/error_handler.py:152

### fornitori_learning (6)
- `POST /api/fornitori-learning/associa-magazzino` — app/routers/fornitori_learning.py:656
- `POST /api/fornitori-learning/classifica-f24` — app/routers/fornitori_learning.py:785
- `GET /api/fornitori-learning/f24-statistiche` — app/routers/fornitori_learning.py:856
- `GET /api/fornitori-learning/giacenze-fornitore/{fornitore_nome}` — app/routers/fornitori_learning.py:747
- `GET /api/fornitori-learning/prodotti-per-fornitore/{fornitore_nome}` — app/routers/fornitori_learning.py:718
- `POST /api/fornitori-learning/riclassifica-f24/{f24_id}` — app/routers/fornitori_learning.py:891

### bank.riconciliazione_f24_banca (5)
- `GET /api/f24-riconciliazione/estratti-conto` — app/routers/bank/riconciliazione_f24_banca.py:335
- `GET /api/f24-riconciliazione/movimenti-f24-banca` — app/routers/bank/riconciliazione_f24_banca.py:119
- `POST /api/f24-riconciliazione/riconcilia-f24` — app/routers/bank/riconciliazione_f24_banca.py:159
- `GET /api/f24-riconciliazione/stato-riconciliazione` — app/routers/bank/riconciliazione_f24_banca.py:282
- `POST /api/f24-riconciliazione/upload-estratto-bpm` — app/routers/bank/riconciliazione_f24_banca.py:39

### accounting.prima_nota_salari (5)
- `POST /api/prima-nota-salari/consolida-record` — app/routers/accounting/prima_nota_salari.py:623
- `GET /api/prima-nota-salari/export-excel` — app/routers/accounting/prima_nota_salari.py:763
- `GET /api/prima-nota-salari/salari` — app/routers/accounting/prima_nota_salari.py:71
- `GET /api/prima-nota-salari/salari/riepilogo` — app/routers/accounting/prima_nota_salari.py:100
- `PUT /api/prima-nota-salari/salari/{record_id}/riconcilia` — app/routers/accounting/prima_nota_salari.py:743

### accounting.bilancio (5)
- `GET /api/bilancio/confronto-annuale` — app/utils/error_handler.py:941
- `GET /api/bilancio/conto-economico-dettagliato` — app/utils/error_handler.py:409
- `GET /api/bilancio/export-pdf` — app/utils/error_handler.py:808
- `GET /api/bilancio/export/pdf/confronto` — app/utils/error_handler.py:1274
- `GET /api/bilancio/riepilogo` — app/utils/error_handler.py:391

### bank.bank_statement_import (5)
- `POST /api/bank-statement/cleanup-duplicati` — app/utils/error_handler.py:942
- `GET /api/bank-statement/formati-supportati` — app/utils/error_handler.py:1028
- `POST /api/bank-statement/import` — app/utils/error_handler.py:665
- `POST /api/bank-statement/riconcilia-manuale` — app/utils/error_handler.py:912
- `GET /api/bank-statement/stats` — app/utils/error_handler.py:890

### bank.pos_accredito (5)
- `GET /api/pos-accredito/accrediti-attesi/{data_accredito}` — app/utils/error_handler.py:133
- `GET /api/pos-accredito/calcola-accredito` — app/utils/error_handler.py:28
- `GET /api/pos-accredito/calendario-mensile/{anno}/{mese}` — app/utils/error_handler.py:60
- `GET /api/pos-accredito/festivi/{anno}` — app/utils/error_handler.py:76
- `GET /api/pos-accredito/riconciliazione-pos/{anno}/{mese}` — app/utils/error_handler.py:172

### invoices.invoices_emesse (5)
- `GET /api/invoices/emesse` — app/routers/invoices/invoices_emesse.py:15
- `POST /api/invoices/emesse` — app/routers/invoices/invoices_emesse.py:42
- `POST /api/invoices/emesse/upload-xml` — app/routers/invoices/invoices_emesse.py:74
- `GET /api/invoices/emesse/{invoice_id}` — app/routers/invoices/invoices_emesse.py:28
- `DELETE /api/invoices/emesse/{invoice_id}` — app/routers/invoices/invoices_emesse.py:60

### suppliers_module.validation (5)
- `POST /api/suppliers/aggiorna-dizionario-metodo` — app/routers/suppliers_module/validation.py:133
- `GET /api/suppliers/dizionario-metodi-pagamento` — app/routers/suppliers_module/validation.py:72
- `GET /api/suppliers/payment-methods` — app/routers/suppliers_module/validation.py:15
- `GET /api/suppliers/payment-terms` — app/routers/suppliers_module/validation.py:24
- `GET /api/suppliers/validazione-p0` — app/routers/suppliers_module/validation.py:30

### learning_machine (5)
- `GET /api/learning-machine/documenti` — app/routers/learning_machine.py:271
- `POST /api/learning-machine/feedback` — app/routers/learning_machine.py:309
- `DELETE /api/learning-machine/reset-learning` — app/routers/learning_machine.py:555
- `POST /api/learning-machine/scan` — app/routers/learning_machine.py:384
- `GET /api/learning-machine/statistiche-feedback` — app/routers/learning_machine.py:521

### paypal_api (5)
- `GET /api/paypal-api/ricevuta-pdf/{transaction_id}` — app/routers/paypal_api.py:204
- `POST /api/paypal-api/smappa-fornitore` — app/routers/paypal_api.py:536
- `GET /api/paypal-api/status` — app/routers/paypal_api.py:129
- `POST /api/paypal-api/sync/month` — app/routers/paypal_api.py:117
- `POST /api/paypal-api/webhook` — app/routers/paypal_api.py:39

### multi_pagamento (5)
- `POST /api/pagamenti/assegno-multi-fatture` — app/utils/error_handler.py:193
- `POST /api/pagamenti/fattura-multi-metodo` — app/utils/error_handler.py:242
- `GET /api/pagamenti/fattura/{fattura_id}` — app/utils/error_handler.py:66
- `GET /api/pagamenti/riepilogo-fornitore/{piva}` — app/utils/error_handler.py:281
- `DELETE /api/pagamenti/{pagamento_id}` — app/utils/error_handler.py:312

### document_ai (5)
- `GET /api/document-ai/document-types` — app/routers/document_ai.py:163
- `POST /api/document-ai/extract-base64` — app/routers/document_ai.py:96
- `POST /api/document-ai/extract-text-only` — app/routers/document_ai.py:136
- `POST /api/document-ai/process-classified-email` — app/routers/document_ai.py:259
- `POST /api/document-ai/reprocess-and-save` — app/routers/document_ai.py:396

### noleggio (5)
- `POST /api/noleggio/controllo-canoni` — app/utils/error_handler.py:123
- `GET /api/noleggio/export-pdf-costi` — app/utils/error_handler.py:412
- `POST /api/noleggio/veicoli` — app/utils/error_handler.py:779
- `GET /api/noleggio/veicoli/{targa}/completo` — app/utils/error_handler.py:390
- `GET /api/noleggio/verbali-dipendente` — app/utils/error_handler.py:955

### prima_nota_module.cassa (4)
- `GET /api/prima-nota/cassa/analisi-movimenti-bancari-errati` — app/routers/prima_nota_module/cassa.py:252
- `DELETE /api/prima-nota/cassa/delete-by-source/{source}` — app/routers/prima_nota_module/cassa.py:221
- `PUT /api/prima-nota/cassa/{movimento_id}` — app/routers/prima_nota_module/cassa.py:140
- `GET /api/prima-nota/cassa/{movimento_id}/fattura` — app/routers/prima_nota_module/cassa.py:228

### prima_nota_module.banca (4)
- `POST /api/prima-nota/banca` — app/routers/prima_nota_module/banca.py:80
- `DELETE /api/prima-nota/banca/delete-by-source/{source}` — app/routers/prima_nota_module/banca.py:207
- `PUT /api/prima-nota/banca/{movimento_id}` — app/routers/prima_nota_module/banca.py:114
- `GET /api/prima-nota/banca/{movimento_id}/fattura` — app/routers/prima_nota_module/banca.py:214

### bonifici_module.jobs (4)
- `POST /api/archivio-bonifici/jobs` — app/routers/bonifici_module/jobs.py:20
- `GET /api/archivio-bonifici/jobs` — app/routers/bonifici_module/jobs.py:39
- `GET /api/archivio-bonifici/jobs/{job_id}` — app/routers/bonifici_module/jobs.py:46
- `POST /api/archivio-bonifici/jobs/{job_id}/upload` — app/routers/bonifici_module/jobs.py:55

### bonifici_module.transfers (4)
- `GET /api/archivio-bonifici/download-zip/{year}` — app/routers/bonifici_module/transfers.py:273
- `GET /api/archivio-bonifici/export` — app/routers/bonifici_module/transfers.py:198
- `DELETE /api/archivio-bonifici/transfers/bulk` — app/routers/bonifici_module/transfers.py:166
- `GET /api/archivio-bonifici/transfers/{transfer_id}/pdf` — app/routers/bonifici_module/transfers.py:93

### fatture_module.crud (4)
- `PUT /api/fatture-ricevute/fattura/{fattura_id}` — app/routers/fatture_module/crud.py:526
- `GET /api/fatture-ricevute/fattura/{fattura_id}/pdf/{allegato_id}` — app/routers/fatture_module/crud.py:480
- `GET /api/fatture-ricevute/fattura/{fattura_id}/view-assoinvoice` — app/routers/fatture_module/crud.py:384
- `POST /api/fatture-ricevute/pulisci-duplicati` — app/routers/fatture_module/crud.py:661

### drive_cedolini (4)
- `POST /api/cedolini/drive/quadratura` — app/routers/drive_cedolini.py:87
- `GET /api/cedolini/drive/status` — app/routers/drive_cedolini.py:64
- `POST /api/cedolini/drive/sync` — app/routers/drive_cedolini.py:71
- `GET /api/cedolini/{cedolino_id}/pdf` — app/routers/drive_cedolini.py:22

### reports.report_pdf (4)
- `GET /api/report-pdf/dipendenti` — app/routers/reports/report_pdf.py:243
- `GET /api/report-pdf/magazzino` — app/routers/reports/report_pdf.py:504
- `GET /api/report-pdf/mensile` — app/routers/reports/report_pdf.py:73
- `GET /api/report-pdf/scadenze` — app/routers/reports/report_pdf.py:349

### reports.exports (4)
- `GET /api/exports/accounting/excel` — app/routers/reports/exports.py:219
- `GET /api/exports/employees/excel` — app/routers/reports/exports.py:177
- `GET /api/exports/invoices/excel` — app/routers/reports/exports.py:75
- `GET /api/exports/warehouse/excel` — app/routers/reports/exports.py:125

### suppliers_module.bulk (4)
- `POST /api/suppliers/aggiorna-metodi-bulk` — app/routers/suppliers_module/bulk.py:143
- `POST /api/suppliers/aggiorna-tutti-bulk` — app/routers/suppliers_module/bulk.py:20
- `POST /api/suppliers/correggi-nomi-mancanti` — app/routers/suppliers_module/bulk.py:224
- `POST /api/suppliers/sincronizza-da-fatture` — app/routers/suppliers_module/bulk.py:298

### settings (4)
- `GET /api/settings` — app/routers/settings.py:40
- `PUT /api/settings` — app/routers/settings.py:152
- `GET /api/settings/logo` — app/routers/settings.py:70
- `POST /api/settings/logo` — app/routers/settings.py:108

### scadenzario_fornitori (4)
- `PUT /api/scadenzario-fornitori/aggiorna-scadenza` — app/utils/error_handler.py:319
- `GET /api/scadenzario-fornitori/aging` — app/utils/error_handler.py:345
- `GET /api/scadenzario-fornitori/cash-flow-previsionale` — app/utils/error_handler.py:248
- `GET /api/scadenzario-fornitori/scadenze-integrate` — app/utils/error_handler.py:420

### f24_analisi (3)
- `GET /api/f24-analisi/doppi-pagamenti` — app/routers/f24_analisi.py:39
- `GET /api/f24-analisi/{f24_id}` — app/routers/f24_analisi.py:173
- `GET /api/f24-analisi/{f24_id}/associazione` — app/routers/f24_analisi.py:187

### prima_nota_module.salari (3)
- `GET /api/prima-nota/salari` — app/routers/prima_nota_module/salari.py:14
- `POST /api/prima-nota/salari` — app/routers/prima_nota_module/salari.py:62
- `GET /api/prima-nota/salari/stats` — app/routers/prima_nota_module/salari.py:104

### accounting.contabilita_gestionale (3)
- `GET /api/contabilita-gestionale/partitario/clienti` — app/routers/accounting/contabilita_gestionale.py:544
- `GET /api/contabilita-gestionale/partitario/fornitori` — app/routers/accounting/contabilita_gestionale.py:374
- `GET /api/contabilita-gestionale/partitario/fornitori/{piva}` — app/routers/accounting/contabilita_gestionale.py:522

### bonifici_module.riconciliazione (3)
- `POST /api/archivio-bonifici/associa-dipendenti` — app/routers/bonifici_module/riconciliazione.py:302
- `GET /api/archivio-bonifici/dashboard` — app/routers/bonifici_module/riconciliazione.py:247
- `POST /api/archivio-bonifici/reset-riconciliazione` — app/routers/bonifici_module/riconciliazione.py:290

### drive_corrispettivi (3)
- `POST /api/corrispettivi/drive/quadratura` — app/routers/drive_corrispettivi.py:41
- `GET /api/corrispettivi/drive/status` — app/routers/drive_corrispettivi.py:20
- `POST /api/corrispettivi/drive/sync` — app/routers/drive_corrispettivi.py:27

### drive_quietanze (3)
- `POST /api/f24/quietanze/drive/quadratura` — app/routers/drive_quietanze.py:44
- `GET /api/f24/quietanze/drive/status` — app/routers/drive_quietanze.py:21
- `POST /api/f24/quietanze/drive/sync` — app/routers/drive_quietanze.py:28

### suppliers_module.iban (3)
- `POST /api/suppliers/ricerca-iban-singolo/{supplier_id}` — app/routers/suppliers_module/iban.py:186
- `POST /api/suppliers/ricerca-iban-web` — app/routers/suppliers_module/iban.py:21
- `POST /api/suppliers/sync-iban` — app/routers/suppliers_module/iban.py:256

### finanziaria (3)
- `GET /api/finanziaria/cost-categories` — app/routers/finanziaria.py:244
- `GET /api/finanziaria/costi` — app/routers/finanziaria.py:233
- `POST /api/finanziaria/costo` — app/routers/finanziaria.py:265

### pianificazione (3)
- `GET /api/pianificazione/costi-previsionali` — app/routers/pianificazione.py:15
- `POST /api/pianificazione/costi-previsionali` — app/routers/pianificazione.py:28
- `DELETE /api/pianificazione/costi-previsionali/{costo_id}` — app/routers/pianificazione.py:45

### verifica_coerenza (3)
- `GET /api/verifica-coerenza/discrepanze/{anno}` — app/routers/verifica_coerenza.py:55
- `GET /api/verifica-coerenza/riepilogo-giornaliero` — app/routers/verifica_coerenza.py:249
- `GET /api/verifica-coerenza/verifica-bonifici-vs-banca/{anno}` — app/routers/verifica_coerenza.py:180

### operazioni_module.smart (3)
- `GET /api/operazioni-da-confermare/smart/cerca-fatture` — app/routers/operazioni_module/smart.py:288
- `GET /api/operazioni-da-confermare/smart/movimento/{movimento_id}` — app/routers/operazioni_module/smart.py:81
- `POST /api/operazioni-da-confermare/smart/riconcilia-auto` — app/routers/operazioni_module/smart.py:102

### cespiti (3)
- `GET /api/cespiti/calcolo/{anno}` — app/utils/error_handler.py:251
- `POST /api/cespiti/dismissione` — app/utils/error_handler.py:572
- `GET /api/cespiti/{cespite_id}` — app/utils/error_handler.py:473

### alerts (3)
- `GET /api/alerts/fornitori-senza-metodo` — app/routers/alerts.py:129
- `POST /api/alerts/risolvi-fornitore/{fornitore_piva}` — app/routers/alerts.py:196
- `DELETE /api/alerts/{alert_id}` — app/routers/alerts.py:183

### mutui_parser (3)
- `POST /api/mutui/import-pdf` — app/routers/mutui_parser.py:187
- `POST /api/mutui/parse-multiple` — app/routers/mutui_parser.py:313
- `POST /api/mutui/parse-pdf` — app/routers/mutui_parser.py:149

### email_scanner (3)
- `GET /api/email-scanner/cartelle` — app/routers/email_scanner.py:19
- `POST /api/email-scanner/scansiona` — app/routers/email_scanner.py:35
- `POST /api/email-scanner/scansiona-e-associa` — app/routers/email_scanner.py:92

### prima_nota_module.stats (2)
- `GET /api/prima-nota/export/excel` — app/routers/prima_nota_module/stats.py:139
- `GET /api/prima-nota/saldo-finale` — app/routers/prima_nota_module/stats.py:106

### prima_nota_module.attese (2)
- `POST /api/prima-nota/attese/scan` — app/routers/prima_nota_module/attese.py:72
- `POST /api/prima-nota/attese/{attesa_id}/annulla` — app/routers/prima_nota_module/attese.py:82

### accounting.contabilita_avanzata (2)
- `GET /api/contabilita/categorizzazione-preview` — app/utils/error_handler.py:642
- `GET /api/contabilita/piano-conti-esteso` — app/utils/error_handler.py:39

### accounting.regole_categorizzazione (2)
- `POST /api/regole/categorie` — app/routers/accounting/regole_categorizzazione.py:553
- `POST /api/regole/descrizione` — app/routers/accounting/regole_categorizzazione.py:504

### bank.assegni_learning (2)
- `POST /api/assegni/learning/associa-combinazioni-avanzato` — app/routers/bank/assegni_learning.py:495
- `GET /api/assegni/learning/suggerimenti/{importo}` — app/routers/bank/assegni_learning.py:259

### distinte_bpm (2)
- `POST /api/paghe/import-distinte-bpm` — app/routers/distinte_bpm.py:106
- `POST /api/paghe/riconcilia-pagamento-manuale` — app/routers/distinte_bpm.py:268

### invoices.invoices_main (2)
- `GET /api/invoices/bank-pending` — app/routers/invoices/invoices_main.py:160
- `GET /api/invoices/by-month/{year}/{month}` — app/routers/invoices/invoices_main.py:191

### suppliers_module.import_export (2)
- `POST /api/suppliers/import-excel` — app/routers/suppliers_module/import_export.py:117
- `POST /api/suppliers/upload-excel` — app/routers/suppliers_module/import_export.py:18

### gestione_riservata (2)
- `GET /api/gestione-riservata/movimenti` — app/routers/gestione_riservata.py:43
- `GET /api/gestione-riservata/volume-affari-reale` — app/routers/gestione_riservata.py:202

### pos_corrispettivi_check (2)
- `GET /api/pos-corrispettivi/anomalie-gravi` — app/utils/error_handler.py:458
- `GET /api/pos-corrispettivi/chiusura-giornaliera/audit` — app/utils/error_handler.py:651

### learning_universal (2)
- `POST /api/learning-universal/apply-suggestions` — app/routers/learning_universal.py:547
- `GET /api/learning-universal/suggestions/{module}` — app/routers/learning_universal.py:472

### previsioni_acquisti (2)
- `GET /api/previsioni-acquisti/confronto-ordine` — app/routers/previsioni_acquisti.py:390
- `GET /api/previsioni-acquisti/prodotti` — app/routers/previsioni_acquisti.py:95

### documents_inbox_classify (2)
- `GET /api/documenti-inbox/cross-check-f24` — app/utils/error_handler.py:387
- `GET /api/documenti-inbox/statistics` — app/utils/error_handler.py:266

### partite_aperte_api (2)
- `GET /api/partite-aperte/lista` — app/routers/partite_aperte_api.py:45
- `GET /api/partite-aperte/scadute` — app/routers/partite_aperte_api.py:72

### auth (1)
- `POST /api/auth/logout` — app/routers/auth.py:112

### pin_login (1)
- `GET /api/auth/pin-login/health` — app/routers/pin_login.py:242

### bonifici_module.associazioni (1)
- `GET /api/archivio-bonifici/dipendente/{dipendente_id}` — app/routers/bonifici_module/associazioni.py:338

### bank.bonifici_import_unificato (1)
- `POST /api/archivio-bonifici/jobs/import` — app/routers/bank/bonifici_import_unificato.py:26

### invoices.fatture_drive (1)
- `POST /api/fatture/drive/quadratura` — app/routers/invoices/fatture_drive.py:43

### configurazioni (1)
- `PUT /api/config/parole-chiave` — app/routers/configurazioni.py:223

### scadenze (1)
- `GET /api/scadenze/` — app/utils/error_handler.py:47

### chiusura_esercizio (1)
- `GET /api/chiusura-esercizio/saldi-iniziali/{anno}` — app/utils/error_handler.py:508

### chat_router (1)
- `GET /api/chat/history` — app/routers/chat_router.py:353

### documenti_non_associati (1)
- `GET /api/documenti-non-associati/pdf/{documento_id}` — app/routers/documenti_non_associati.py:465
