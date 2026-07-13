# MATRICE FUNZIONALE FINALE (§14) — 13 moduli principali

Data: 2026-07-13 · Deliverable §14 del PROMPT_DEFINITIVO.
Catena verificata sul codice reale: Route React → Pagina/Componente → Tab →
Pulsante/Azione → API → Router backend → Service/Engine → Collection → Test → Stato.
Ogni path API in tabella è stato verificato contro il decoratore/registrazione
backend (`app/router_registry.py` + file router); nessuna riga è inferita.

Contesto vincolante:
- Auth centralizzata: middleware globale `app/middleware/authentication.py`
  (ogni `/api/*` richiede JWT salvo allowlist minima, congelata da test).
- Collection canoniche: `invoices`, `fatture_emesse`, `f24_unificato`,
  `dipendenti`, `cedolini`, `suppliers`, `estratto_conto_movimenti`,
  `prima_nota_cassa`/`prima_nota_banca`, `documenti_classificati`, `corrispettivi`.
- Saldo Prima Nota: motore unico `prima_nota_module/common.aggrega_saldo_prima_nota`.
- Piano dei conti: SOLO ufficiale CEE (`app/services/piano_conti_ufficiale.py` +
  `mapping_piano_conti.py`).

---

## 1. Dashboard

Route `/` e `/dashboard` → `pages/hub/DashboardHub.jsx` → `Dashboard.jsx` (ricostruita: filtro Anno+Mese, card separate, scorciatoie-domanda chat).

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /dashboard | Dashboard.jsx | — | Trend mensile costi/ricavi | GET /api/dashboard/trend-mensile | dashboard.py | controllo_gestione | corrispettivi, invoices | — | OK |
| /dashboard | Dashboard.jsx | — | Card saldi Prima Nota | GET /api/prima-nota/stats | prima_nota_module/stats.py | aggrega_saldo_prima_nota | prima_nota_cassa/banca | test_p1_saldo_prima_nota.py | OK — motore unico (§6.4) |
| /dashboard | Dashboard.jsx | — | Widget F24 da pagare + scadenze | GET /api/scadenze · /api/scadenze/prossime | scadenze.py | conta_f24_da_pagare (P0.1) | f24_unificato | test_p0_01_widget_f24.py, test_quietanze_scadenze.py | OK |
| /dashboard | Dashboard.jsx | — | Costi/ricavi periodo | GET /api/controllo-gestione/costi-ricavi | controllo_gestione.py | controllo_gestione | corrispettivi, invoices, cedolini | — | OK |
| /dashboard | Dashboard.jsx | — | Card coerenza IVA | GET /api/verifica-coerenza/iva/{anno} · /confronto-iva-completo/{anno} | verifica_coerenza.py | riepilogo_iva_engine | invoices, liquidazioni_iva | test_iva_dashboard_chat.py | OK |
| /dashboard | Dashboard.jsx | — | Scorciatoie-domanda → chat | POST /api/chat/ask | chat_router.py | chat_ai_engine | (lettura multi-collection) | test_chat_ai_noleggio.py | OK |

## 2. Fatture (ricevute + emesse)

Route `/fatture` e `/fatture/:tab` → `pages/hub/FattureHub.jsx` (archivio, upload, emesse).

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /fatture | ArchivioFattureRicevute.jsx | Archivio | Lista archivio + filtri | GET /api/fatture-ricevute/archivio | fatture_ricevute.py | — | invoices | test_p1_fatture_passive.py | OK — collection canonica |
| /fatture | ArchivioFattureRicevute.jsx | Archivio | Elenco fornitori (filtro) | GET /api/fatture-ricevute/fornitori | fatture_ricevute.py | — | invoices, suppliers | — | OK |
| /fatture | ArchivioFattureRicevute.jsx | Archivio | Paga manuale (→ Prima Nota) | POST /api/fatture-ricevute/paga-manuale | fatture_ricevute.py | prima nota adapter | invoices + prima_nota_cassa/banca | test_p1_cash_adapter.py | OK |
| /fatture | ArchivioFattureRicevute.jsx | Archivio | Vedi fattura (viewer) | GET /api/invoices/{id}/html·/pdf | invoices/invoices_main.py | fattura_render | invoices | — | OK — DocumentViewerModal/iframe cookie |
| /fatture | FattureHub (upload) | Import | Upload XML/P7M | POST /api/fatture/upload | fatture_upload.py | parser XML SDI | invoices | test_p1_fatture_passive.py | OK — dedup invoice_key |
| /fatture | Admin.jsx | Drive | Sync fatture da Drive + pulizia per anno | POST /api/fatture/drive/sync · /pulizia-anno | drive_fatture.py | drive ingest | invoices, documents_inbox | test_drive_documenti_ingest.py | OK |
| /fatture | FattureEmesse | Emesse | Lista/creazione fatture emesse | GET/POST /api/fatture-emesse | fatture_emesse.py | — | fatture_emesse | test_p1_fatture_emesse.py | OK — canonica scelta dall'utente |
| — | (API esterna) | — | Lista fatture per integrazioni | GET /api/v1/fatture | public_api.py | richiedi_api_key | fatture_ricevute/emesse | — | Vivo ma canale /api/v1 oggi richiede anche JWT (vedi AUDIT_ESECUZIONE §10.1) |

## 3. Corrispettivi

Route `/corrispettivi` → `Corrispettivi.jsx` (ListaAdattiva); coerenza POS in `CoerenzaPOSCorrispettivi.jsx`.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /corrispettivi | Corrispettivi.jsx | — | Lista per anno/mese | GET /api/corrispettivi | invoices/corrispettivi.py | — | corrispettivi | test_p0_09_pos_corrispettivi.py | OK |
| /corrispettivi | Corrispettivi.jsx | — | Inserimento manuale | POST /api/corrispettivi/manuale | invoices/corrispettivi.py | sync prima nota | corrispettivi + prima_nota_cassa | test_p1_cash_adapter.py | OK — marcato manuale |
| /corrispettivi | Admin.jsx | Drive | Import XML ufficiali da Drive | POST /api/corrispettivi/drive/sync | drive_corrispettivi.py | drive ingest | corrispettivi | — | OK |
| /coerenza-pos | CoerenzaPOSCorrispettivi.jsx | — | Confronto POS ↔ corrispettivi ↔ banca | GET /api/pos-corrispettivi-check | pos_corrispettivi_check.py | motore coerenza POS (P0.9) | corrispettivi, prima_nota_cassa, estratto_conto_movimenti | test_p0_09_pos_corrispettivi.py | OK — guard su giorni incassati |
| /prima-nota | PuliziaPrimaNota.jsx | — | Risincronizza corrispettivi→cassa | POST /api/prima-nota/cassa/sync-corrispettivi | prima_nota_module/sync.py | corrispettivi_service | prima_nota_cassa | — | OK |

## 4. Fornitori

Route `/fornitori` → `pages/hub/FornitoriHub.jsx` → `Fornitori.jsx`.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /fornitori | Fornitori.jsx | — | Lista con filtri (metodo, cessato, anno ultima fattura) | GET /api/suppliers | suppliers_module/base.py | — | suppliers | test_p1_fornitori.py | OK |
| /fornitori | Fornitori.jsx | — | Aggiorna metodo pagamento | PUT /api/suppliers/{id} | suppliers_module/base.py | lookup tollerante (id/piva) | suppliers | test_p1_fornitori.py | OK — niente default "bonifico" |
| /fornitori | Fornitori.jsx | — | Estratto fatture fornitore (modale) | GET /api/fatture-ricevute/archivio?fornitore= | fatture_ricevute.py | — | invoices | — | OK — anno default "tutti" |
| /fornitori | Fornitori.jsx | — | Paga fattura dal modale | POST /api/fatture-ricevute/paga-manuale | fatture_ricevute.py | prima nota adapter | invoices + prima_nota_* | — | OK |
| — | (backend) | — | Creazione automatica fornitore da fattura | (interno import) | services/suppliers | ensure_supplier_exists + guardie fantasma | suppliers | test_fornitori_guardie.py | OK — no "Ceraldi Group" fantasma |
| — | (legacy) | — | Crea fornitore (route legacy) | POST /api/suppliers (public_api.py:216) | public_api.py | associazione fatture per P.IVA | suppliers, invoices | — | DOPPIONE del flusso suppliers_module: candidata a §13.2 (verificare chiamanti esterni prima di rimuovere) |

## 5. Prima Nota

(Ricognizione integrale — righe principali; motore saldo unico verificato in `cassa.py:56`, `banca.py:54`, `stats.py`, `manutenzione.py`.)

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /prima-nota | PrimaNota.jsx | CASSA | Lista + saldo cassa | GET /api/prima-nota/cassa | prima_nota_module/cassa.py | aggrega_saldo_prima_nota | prima_nota_cassa | test_p1_saldo_prima_nota.py | OK |
| /prima-nota | PrimaNota.jsx | CASSA | Crea corrispettivo/POS/versamento/movimento | POST /api/prima-nota/cassa | prima_nota_module/cassa.py | — | prima_nota_cassa | test_p1_cash_adapter.py | OK |
| /prima-nota | PrimaNota.jsx | BANCA | Lista + saldo banca | GET /api/prima-nota/banca | prima_nota_module/banca.py | aggrega_saldo_prima_nota | prima_nota_banca | test_p1_saldo_prima_nota.py | ⚠ il FE ricalcola il saldo in JS fondendo l'estratto conto (anomalia A1) |
| /prima-nota | PrimaNota.jsx | BANCA | Movimenti estratto conto + import CSV | GET /api/estratto-conto-movimenti/movimenti · POST /import | bank/estratto_conto.py | aggregazione propria | estratto_conto_movimenti | — | ⚠ saldo con pipeline propria (anomalia A2) |
| /prima-nota | PrimaNota.jsx | CASSA/BANCA | Elimina / Sposta movimento | DELETE /api/prima-nota/{tipo}/{id} · POST /sposta-movimento | cassa.py, banca.py, manutenzione.py | BusinessRules.can_delete_movement | prima_nota_* + invoices | — | OK — sgancia fattura pagata |
| /prima-nota | PrimaNota.jsx | PROVVISORI | Lista + conferma fatture provvisorie (cassa/banca/sospesa) | GET /api/prima-nota/provvisori · POST /provvisori/conferma | prima_nota_module/sync.py | dati_provvisori_service | invoices + prima_nota_* | — | OK — fix bug "sospesa" |
| /prima-nota | PrimaNota.jsx | PROVVISORI | Fatture attese Aruba (anticipo) | GET /api/prima-nota/attese · POST /attese/conferma | prima_nota_module/attese.py | aruba_notifiche | fatture_attese | — | OK |
| /prima-nota/salari | PrimaNotaSalariTab.jsx | SALARI | Lista/import paghe e bonifici, progressivi, export | GET/POST /api/prima-nota-salari/* | accounting/prima_nota_salari.py | — | prima_nota_salari | — | OK |
| /prima-nota/pulizia | PuliziaPrimaNota.jsx | — | Diagnosi + dedup (anteprima/applica) + smista per metodo | GET /api/prima-nota/diagnostica-* · POST /dedup-fatture · /provvisori/auto-conferma-per-metodo | prima_nota_module/manutenzione.py, sync.py | deduplica | prima_nota_* + invoices | — | OK — soft-delete |
| — | (manutenzione) | — | Ricalcolo saldi globale | POST /api/prima-nota/recalculate-balances | prima_nota_module/manutenzione.py | aggrega_saldo_prima_nota | prima_nota_* | — | OK (§6.4) |

## 6. Contabilità

Route `/contabilita` e `/contabilita/:sezione` → `ContabilitaHub.jsx`.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /contabilita | PianoDeiConti.jsx | piano-conti | Lista conti + crea conto/regola | GET/POST /api/piano-conti/ · /regole | accounting/piano_conti.py | piano_conti_ufficiale | piano_conti, regole_categorizzazione | test_p1_mapping_piano_conti.py | OK |
| /contabilita | PianoDeiConti.jsx | piano-conti | Bilancio riclassificato CEE | GET /api/piano-conti/bilancio?anno= | accounting/piano_conti.py | mapping_piano_conti.classifica_saldi_ufficiale | invoices, corrispettivi, prima_nota_* | test_p1_bilancio_ufficiale.py | OK — SOLO schema CEE ufficiale |
| /contabilita/bilancio | Bilancio.jsx | bilancio | SP + CE (con voci_ufficiali) | GET /api/bilancio/stato-patrimoniale · /conto-economico | accounting/bilancio.py | piano_conti_ufficiale | invoices, corrispettivi, prima_nota_*, cedolini, fatture_emesse | test_p1_bilancio_ufficiale.py | OK |
| /contabilita/verifica | BilancioVerifica.jsx | verifica | Bilancio di verifica (partita doppia) | GET /api/contabilita-gestionale/bilancio-verifica | accounting/contabilita_gestionale.py | libro_giornale | scritture_contabili | test_libro_giornale.py | OK |
| /contabilita/cespiti | GestioneCespiti.jsx | cespiti | CRUD cespiti + registra ammortamenti + scan fatture | /api/cespiti/* | cespiti.py | — | cespiti, movimenti_contabili | — | ⚠ nessun test (anomalia A6) |
| /contabilita/chiusura | ChiusuraEsercizio.jsx | chiusura | Verifica preliminare + esegui chiusura | GET/POST /api/chiusura-esercizio/* | chiusura_esercizio.py | — | chiusure_esercizio, movimenti_contabili | — | ⚠ nessun test; scrive movimenti_contabili non scritture_contabili (A6/A7) |
| /contabilita/avanzata | ContabilitaAvanzata.jsx | avanzata | IRAP, ricategorizza, piano esteso, liquidità | /api/contabilita/aliquote-irap · /ricategorizza-fatture · /inizializza-piano-esteso · /disponibilita-liquide | contabilita_avanzata.py + contabilita_italiana.py | calcolo_imposte, categorizzazione | invoices, piano_conti, prima_nota_* | — | OK (path disgiunti, nessuna collisione) |
| /contabilita/budget | BudgetPrevisionale.jsx | budget | Budget vs consuntivo (CRUD) | /api/contabilita-gestionale/budget* | accounting/contabilita_gestionale.py | — | budget_contabile, scritture_contabili | — | OK |

## 7. IVA

Route `/iva` → `GestioneIVA.jsx`; motori in `app/engines/`.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /iva | GestioneIVA.jsx | — | IVA disponibile non utilizzata | GET /api/iva/fatture/non-utilizzate | iva.py | — | invoices | test_iva_fatture.py | OK |
| /iva | GestioneIVA.jsx | — | Calcola pregresso + ultimo ricalcolo persistito | POST /api/iva/ricalcola-attribuzione · GET /ultimo | iva.py | engines/iva_fatture | invoices + iva_ricalcolo_log | test_iva_ricalcolo.py | OK — regola del 15, dic/gen |
| /iva | GestioneIVA.jsx | — | Dashboard mese + liquidazione periodo | GET /api/iva/dashboard/{anno}/{mese} · /liquidazioni/{periodo} | iva.py | — | invoices, liquidazioni_iva | test_iva_dashboard_chat.py | OK |
| /iva | GestioneIVA.jsx | — | Calcola liquidazione mensile | POST /api/iva/liquidazioni/calcola | iva.py | engines/liquidazione_iva_engine | liquidazioni_iva + invoices | test_liquidazione_iva_engine.py, test_p1_iva_scenari.py | OK |
| /iva | GestioneIVA.jsx | — | Conferma / Riapri liquidazione | POST /api/iva/liquidazioni/{id}/conferma · /riapri | iva.py | liquidazione_iva_engine | liquidazioni_iva, invoices, movimenti_iva_fattura | test_liquidazione_iva_engine.py | OK — anti doppia detrazione (§17.10) |
| /iva | GestioneIVA.jsx | — | Riepilogo annuale + anomalie | GET /api/iva/riepilogo-annuale/{anno} · /anomalie | iva.py | engines/riepilogo_iva_engine | invoices + liquidazioni_iva | test_riepilogo_iva.py | OK |
| — | (senza UI) | — | Azioni manuali per fattura (escludi/rinvia/indetraibile/…) + rettifica | POST /api/iva/fatture/{id}/* · /liquidazioni/{id}/rettifica | iva.py | liquidazione_iva_engine | invoices, movimenti_iva_fattura | test_p1_iva_scenari.py (parz.) | ⚠ endpoint vivi non azionabili dalla UI (anomalia A5) |

## 8. F24

FE: widget Scadenze, tab F24 in RiconciliazioneUnificata, impostazioni email; backend `f24_main`, `scadenze`, `operazioni_da_confermare`, motori tributi/fiscale.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /scadenze | Scadenze.jsx | — | F24 da pagare + scadenze | GET /api/scadenze · /prossime | scadenze.py | conta_f24_da_pagare | f24_unificato | test_p0_01_widget_f24.py | OK |
| /riconciliazione | RiconciliazioneUnificata.jsx | F24 | Conferma F24 smart (banca) / ignora / manuale | POST /api/operazioni-da-confermare/smart/conferma-f24 · /ignora · /riconcilia-manuale | operazioni_da_confermare.py | tributi_engine (associazione coerente) | f24_unificato, estratto_conto_movimenti, prima_nota_banca | test_p0_07_f24_banca.py | OK — specifica vincolante F24 |
| /riconciliazione | RiconciliazioneUnificata.jsx | F24 | Vedi PDF F24 (viewer) | GET pdf_url · /api/download/{file_path} | download.py | — | (file) | — | OK — DocumentViewerModal, cookie |
| /riconciliazione | RiconciliazioneUnificata.jsx | F24 | Elimina F24 | DELETE /api/f24/{id} | f24/f24_main.py | — | f24_unificato | test_p1_f24_consolidamento.py | OK |
| (Impostazioni) | ImpostazioniF24Email.jsx / F24EmailSync.jsx | — | Mittenti attendibili, scan manuale, log | GET/POST /api/f24-email-settings/* | f24/f24_email_settings.py | email ingest F24 | f24_unificato, documents_inbox, mittenti | — | OK — parametri via UI (regola parametri) |
| /documenti | Documenti.jsx | — | Sync F24 automatico da email | POST /api/documenti/sync-f24-automatico | documenti.py | email_download + parser F24 | documents_inbox, f24_unificato | test_p0_08_f24_parser_contract.py | OK |
| — | (backend) | — | Fascicolo F24 (F24↔quietanza↔cedolini↔banca) | GET /api/f24/{id}/fascicolo | f24/f24_main.py | fascicolo materializzato | f24_unificato | test_fascicolo_f24.py | OK |
| — | (senza UI) | — | Parse/import paghe F24, distinte BPM | POST /api/paghe/* | f24_parser.py, distinte_bpm.py | parser LUL/F24 | f24_unificato, cedolini | test_p0_08_f24_parser_contract.py | ⚠ orfani lato FE (anomalia B3) |

## 9. Quietanze

Canale Drive acceso su scelta utente; regola cardine: quietanza senza F24 = alert bloccante, MAI ricostruzione automatica.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| (Admin/scheduler) | Admin.jsx + job orario | — | Ingest quietanze da Drive + quadratura | POST /api/f24/quietanze/drive/sync | f24/drive_quietanze.py | motore unico import quietanze | f24_unificato (fascicolo), documents_inbox | test_quietanze_import.py | OK — idempotente |
| /scadenze | Scadenze.jsx | — | Stato pagato da quietanza | GET /api/scadenze | scadenze.py | quietanza→status | f24_unificato | test_quietanze_scadenze.py | OK |
| — | (motore) | — | Quietanza orfana → alert bloccante | (interno ingest) | drive_quietanze.py | tributi_engine: QUIETANZA_PRESENTE_F24_MANCANTE | f24_unificato, alert | test regressione §9.3 | OK — nessuna ricostruzione automatica (§17.12) |
| — | (motore) | — | Doppia quietanza → possibile doppio pagamento | (interno ingest) | drive_quietanze.py | tributi_engine | f24_unificato | test_tributi_fiscale_engine.py | OK |
| /riconciliazione | RiconciliazioneUnificata.jsx | Documenti | Associa quietanza a F24 | POST /api/documenti-non-associati/associa | documenti_non_associati.py | associazione coerente periodo/causale | documenti_non_associati, f24_unificato | — | OK |

## 10. Riconciliazione

Route `/riconciliazione` → `pages/hub/RiconciliazioneHub.jsx` → `RiconciliazioneUnificata.jsx` (+ verbali, PagoPA, PayPal).

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /riconciliazione | RiconciliazioneUnificata.jsx | Smart | Cerca stipendi / conferma / ignora / manuale | POST /api/operazioni-da-confermare/smart/* | operazioni_da_confermare.py | matching smart | estratto_conto_movimenti, prima_nota_banca, f24_unificato, prima_nota_salari | test_p0_02_auto_riconcilia.py | OK — guard 409 |
| /riconciliazione | RiconciliazioneUnificata.jsx | Smart | Crea movimento banca da EC | POST /api/prima-nota-banca/crea | prima_nota_banca (adapter) | — | prima_nota_banca | — | OK — marca EC riconciliato |
| /riconciliazione | RiconciliazioneUnificata.jsx | Documenti | Lista/associa/PDF documenti non associati | GET/POST /api/documenti-non-associati/* | documenti_non_associati.py | — | documenti_non_associati, mittenti_email | — | OK — viewer canonico |
| /riconciliazione | RiconciliazioneUnificata.jsx | — | Auto-ricostruisci dati fattura | POST /api/fatture-ricevute/auto-ricostruisci-dati | fatture_ricevute.py | — | invoices | — | OK |
| /verbali-riconciliazione | VerbaliRiconciliazione.jsx | — | Riconcilia verbale su righe fattura | POST /api/verbali-riconciliazione/riconcilia | verbali_riconciliazione.py | ricerca su linee.* (P0.4) | invoices, verbali | test_p0_04_verbali_linee.py | OK |
| /pagopa | GestionePagoPA.jsx | — | Ricevute PagoPA + viewer PDF | GET /api/pagopa/ricevute · /{id}/pdf | pagopa.py | — | pagopa_ricevute | — | OK — DocumentViewerModal |
| /paypal | PaypalTransactionDetailModal | — | Verbale PDF (blob autenticato) | GET (blob) verbale | paypal router | — | paypal_transactions, verbali | — | OK — revoca objectURL |
| — | (batch) | — | Auto-riconcilia tutto | POST /api/batch/auto-riconcilia-tutto | batch_operations.py | filtro_uscite_da_riconciliare (P0.2) | prima_nota_*, estratto_conto_movimenti | test_p0_02_auto_riconcilia.py | OK |

## 11. Documenti

(Ricognizione integrale dell'agente — righe principali.)

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| /documenti | Documenti.jsx | Documenti | Lista + statistiche | GET /api/documenti/lista · /statistiche | documenti.py | — | documents_inbox (+f24_unificato) | — | ⚠ legge documents_inbox, non la canonica (anomalia B1) |
| /documenti | Documenti.jsx | Classificati AI | Doc estratti + stats | GET /api/document-ai/extracted-documents · /classified-documents-stats | document_ai.py | document AI | extracted_documents + documenti_classificati | test_p1_documenti_classificati.py | OK ma collezioni diverse dal tab lista (B1) |
| /documenti | Documenti.jsx | Estrazione AI | Estrai / processa tutti | POST /api/document-ai/extract · /process-all-classified | document_ai.py | AI parser | documenti_classificati | test_drive_documenti_ingest.py | OK |
| /documenti | Documenti.jsx | — | Viewer PDF / processa / cambia categoria / elimina | GET /documento/{id}/download · POST /processa · /cambia-categoria · DELETE | documenti.py | — | documents_inbox | — | OK — viewer canonico fetchUrl |
| /documenti | Documenti.jsx | — | Scarica da email + sync F24 | POST /api/documenti/scarica-da-email · /sync-f24-automatico | documenti.py | email_download | documents_inbox, f24_unificato | — | OK |
| /documenti/import | ImportDocumenti.jsx | Inbox | Auto-classify, import F24/CU | POST /api/documenti-inbox/* | documents_inbox_classify.py | email_classifier | documents_inbox→documenti_classificati/f24_unificato/dipendenti | test_classificazione_unificata.py | OK |
| /documenti-fiscali | DocumentiFiscali.jsx | — | Lista + upload (dichiarazione IVA, avvisi) | GET /api/documenti-fiscali/lista · POST /upload | documenti_fiscali.py | tassonomia | documenti fiscali | test_documenti_fiscali.py | OK |

## 12. Dipendenti contabili

HR anagrafico in app esterna; qui il lato contabile (salari, TFR, cedolini).

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| (varie) | InserimentoRapido, VerbaliRiconciliazione | — | Lista dipendenti (lettura) | GET /api/dipendenti | employees/dipendenti.py | — | dipendenti | test_p0_03_employees_dipendenti.py, test_p1_dipendenti_cessazione.py | OK — canonica |
| /prima-nota/salari | PrimaNotaSalariTab.jsx | Salari | Lista, import paghe/bonifici, progressivi, aggiustamento, export | /api/prima-nota-salari/* | accounting/prima_nota_salari.py | — | prima_nota_salari | — | OK |
| /contabilita/cespiti | GestioneCespiti.jsx | — | Riepilogo TFR aziendale | GET /api/tfr/riepilogo-aziendale | tfr.py | calcoli TFR | dipendenti | test_tfr_calcoli.py | OK |
| — | (chat/scheduler) | — | Download cedolino via chat | (tool AI in /ask) | chat_ai_engine | strumenti tipizzati | cedolini | test_p1_cedolini.py | OK |
| — | (senza UI) | — | Cedolini da Drive (sync/status/pdf) | POST /api/cedolini/drive/sync | drive_cedolini.py | drive ingest | cedolini, documents_inbox | test_drive_cedolini_ingest.py | ⚠ non chiamato dal FE (anomalia B3) |
| — | (senza UI) | — | Parse/import Libro Unico | POST /api/paghe/parse-libro-unico · /import-libro-unico | libro_unico_parser.py | parser LUL | dipendenti, cedolini | test_p0_03_employees_dipendenti.py | ⚠ orfano lato FE (B3) |

## 13. Chat

`ChatIntelligente.jsx` globale (montato in App.jsx); backend `/api/chat`.

| Route React | Pagina | Tab | Azione | API | Router backend | Service/Engine | Collection | Test | Stato |
|---|---|---|---|---|---|---|---|---|---|
| (globale) | ChatIntelligente.jsx | — | Invio messaggio | POST /api/chat/ask | chat_router.py | chat_ai_engine (Claude) o motore parole chiave | chat_history (scrive); legge invoices/f24_unificato/dipendenti/suppliers/corrispettivi | test_chat_ai_noleggio.py, test_iva_dashboard_chat.py | OK |
| (globale) | ChatIntelligente.jsx | — | Tool AI: cerca fatture/movimenti/cedolini/documenti/verbali + analizza F24 | (tool in /ask) | services/chat_ai_engine.py | tributi_engine, iva_engine | invoices, estratto_conto_movimenti, cedolini, documenti_classificati, f24_unificato | test_tributi_fiscale_engine.py | OK — F24 secondo specifica vincolante |
| (globale) | ChatIntelligente.jsx | — | Scarica documento / Vai a (citazioni) | GET /api/.../pdf (link generati) | vari | chat_ai_engine.download_url | — | — | OK |
| — | (senza UI) | — | Storico server + health | GET /api/chat/history · /health | chat_router.py | — | chat_history | — | ⚠ non chiamati dal FE (anomalia B6) |

---

## Anomalie rilevate (ricognizione 2026-07-13)

Contabilità/Prima Nota (evidenze file:riga nella ricognizione):
- **A1** — Il tab BANCA di Prima Nota non usa il saldo del motore unico: fonde `estratto_conto_movimenti` + `prima_nota_banca` e ricalcola in JS (`PrimaNota.jsx:244-265` vs `banca.py:54`). Cassa invece usa il motore. Rischio: due logiche di saldo per la Banca.
- **A2** — `GET /api/estratto-conto-movimenti/movimenti` calcola il saldo con pipeline propria (`bank/estratto_conto.py:1000-1014`), non con `aggrega_saldo_prima_nota`: è la fonte reale del saldo Banca in UI.
- **A3** — Libro giornale/mastro/partitario (`contabilita_gestionale.py:1025,1065,374+`) esposti ma senza chiamanti FE: partita doppia raggiungibile solo via bilancio-verifica.
- **A4** — `contabilita_italiana.py` quasi interamente orfano lato FE (solo `/disponibilita-liquide` usato); i suoi `/cespiti*` duplicano concettualmente `cespiti.py`.
- **A5** — Azioni manuali IVA per-fattura e rettifica liquidazione (`iva.py:440,650-703`) senza UI.
- **A6** — `cespiti.py` e `chiusura_esercizio.py` senza test pur scrivendo stato contabile.
- **A7** — Chiusura/ammortamenti scrivono `movimenti_contabili` mentre il libro giornale vive in `scritture_contabili`: due collezioni contabili parallele.

Documenti/Dipendenti/Chat:
- **B1** — Tre collezioni per i documenti: tab lista legge `documents_inbox`, tab AI legge `extracted_documents`, la canonica è `documenti_classificati` → i tab mostrano insiemi diversi.
- **B2** — Alias legacy `documents_classified` deprecato con migrazione pendente (`app/scripts/migra_documents_classified.py`).
- **B3** — Pipeline paghe (`/api/paghe/*`, `/api/cedolini/*`, distinte BPM) viva ma non azionabile dalla UI.
- **B4** — Widget "buste paga da pagare" e riepilogo cedolini (`documenti.py:1260,1465,1595,1660`) senza chiamanti FE.
- **B5** — Chat protetta solo dal middleware globale (nessun `Depends` per-route): accettabile (non è in allowlist) ma senza secondo livello.
- **B6** — `/api/chat/history` e `/health` mai usati dal FE: lo storico server-side è ignorato dalla UI.
- **B7** — `f24_unificato` con 4 schemi coesistenti (gestiti in `chat_router.py:78-105`): consolidamento dati da completare con le migrazioni al deploy.

Fatture/Fornitori:
- **C1** — `POST /api/suppliers` legacy in `public_api.py:216` doppione del flusso `suppliers_module`: rimuovibile solo dopo verifica chiamanti esterni (app esterna sullo stesso DB).
- **C2** — Canale `/api/v1` (API key) oggi richiede anche JWT: di fatto spento verso l'esterno (decisione lasciata all'utente, vedi AUDIT_ESECUZIONE_DEFINITIVO §10.1).

Le anomalie NON sono regressioni introdotte: sono lo stato reale fotografato, da smaltire come backlog (molte coincidono con i debiti già tracciati nel PROMPT: §6.7 PayPal, §13.2 codice morto, armonizzazione campi).
