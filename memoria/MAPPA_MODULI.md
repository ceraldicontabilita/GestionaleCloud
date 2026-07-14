# MAPPA MODULI — come è costruita l'app (lettura router per router)

> Aggiornata 13/07/2026, numeri e §2 EMPLOYEES aggiornati 14/07/2026 dopo
> la sessione Dipendenti (rimozione contratti/libretti, HR esterno) +
> Fatture Estere (pipeline AI). Ricavata leggendo **tutti i file router**
> uno per uno + route table reale (`register_all_routers`) + uso nel
> frontend. Vedi `AUDIT_DEFINITIVO_SESSIONE_20260714.md` per il dettaglio
> tecnico di quella sessione.
>
> Mappe collegate (`MAPPA_ROUTER.md`/`MAPPA_ENDPOINT_COMPLETA.md`
> rigenerabili con `python scripts/genera_mappa.py`; `MAPPA_COLLEZIONI.md`
> aggiornata manualmente):
> - **`MAPPA_ROUTER.md`** — un prefisso per riga (endpoint, uso FE, file). **108 prefissi, 1059 endpoint** (rigenerata 14/07/2026).
> - **`MAPPA_ENDPOINT_COMPLETA.md`** — ogni singolo endpoint (metodo, path, uso FE).
> - **`MAPPA_COLLEZIONI.md`** — tutte le collezioni MongoDB usate.
> - Codice morto e duplicati: sezione §4-§6 di questo file.

## 1. Architettura

- **Stack**: FastAPI + Motor (async) · React 18 + Vite · MongoDB Atlas (DB `Gestionale`).
- **Deploy**: push su `main` → **Render** auto-deploy → `impresasemplice.online`.
- **Registrazione router**: unico punto `app/router_registry.py` → `register_all_routers(app)`,
  organizzato in 12 gruppi (`_register_auth/f24/accounting/bank/warehouse/invoices/
  employees/reports/core/email/noleggio/ai`).
- **Numeri reali (rigenerati 14/07/2026)**: **1059 endpoint** su **108 prefissi** / **111 tag**.
  Uso frontend: **630 endpoint** referenziati dal FE, **76** da chiamanti esterni
  (app collegate/webhook/chatbot/scheduler/API pubblica), **353** senza riferimento
  noto (candidati verifica — vedi §5, molti sono manutenzione one-shot o usati dalla chat).
  Calo rispetto al 13/07 (1117→1059, -58) dovuto principalmente alla rimozione di 17
  route contratti/libretti sanitari da `employees/dipendenti.py` (vedi §2 EMPLOYEES),
  compensato in minima parte dal nuovo router `/api/fatture-estere` (+3).

### Flusso dati principale
```
Email Aruba PEC / Gmail / Drive → download XML·P7M·PDF → parser →
  fatture passive → invoices  → auto-routing cassa/banca (metodo fornitore)
                              → aggiorna fornitore (fornitori)
                              → storia_fatture + scrittura in scritture_contabili (libro giornale)
  estratto conto XLS/CSV → estratto_conto_movimenti → riconciliazione con fatture/partite
  corrispettivi XML      → corrispettivi → split contanti (cassa) / POS (banca)
  cedolini PDF Zucchetti → cedolini → collega dipendente → prima_nota_salari
  F24 PDF                → f24_unificato → quietanza → riconciliazione banca
```

## 2. I 12 domini (moduli) e come funzionano

### AUTH & PUBLIC — `auth`, `pin_login`, `public_api`, `erp_bridge`, `legal_pages`, `whatsapp_webhook`, `utenti`
Login admin singolo via env (JWT HS256 in cookie httpOnly) + login PIN operatori
(`users`, coll `utenti_pin`). `public_api` = endpoint legacy misti + **API pubblica v1**
con `api_clients` (api-key). `erp_bridge` = ponte inbound da ceraldiapp.it → `fatture_passive`
(fail-closed: 503 senza `ERP_BRIDGE_SECRET`). `legal_pages` = privacy/terms/data-deletion
(doppia registrazione `/api/...` e `/...`). `whatsapp_webhook` = webhook Meta (solo log,
nessuna persistenza inbound).

### F24 — `f24/f24_main`, `f24/f24_riconciliazione`, `f24/f24_public`, `f24/email_f24`, `f24_analisi`, `f24_email_settings`, `f24_parser`, `bank/riconciliazione_f24_banca`
Collezione canonica **`f24_unificato`** (+ `quietanze_f24`). Flusso: PDF F24 commercialista →
parse (`parser_f24`) → riconciliazione con quietanza e con banca; motore normativo
`tributi_engine` (DM10/RC01, ravvedimenti). ⚠️ **F24 frammentato su ≥5 collezioni**
(vedi §6): `f24_unificato`, `f24_commercialista` (alias, non più scritta), `f24_tributi`,
`f24_models`/`Collections.F24_MODELS` (chat/public), `f24_parser.py` con
`f24_pagamenti`/`tributi_pagati`/`distinte_f24` (sottosistema parallelo).

### ACCOUNTING/CONTABILITÀ — `accounting/{bilancio,piano_conti,centri_costo,contabilita_avanzata,contabilita_gestionale,prima_nota_salari,regole_categorizzazione}`, `contabilita_italiana`, `fiscalita_italiana`, `iva`, `cespiti`, `mutui(+parser)`, `chiusura_esercizio`, `controllo_gestione`, `batch_operations`
Bilancio (SP/CE art.2425), partita doppia, IVA per competenza, centri di costo (4 settori
HORECA + ribaltamento), cespiti/ammortamenti, chiusura esercizio, budget, mutui.
**`iva.py` è il modulo più maturo** (liquidazioni con stati/versioni, anti-doppia-detrazione,
`liquidazioni_iva` + `movimenti_iva_fattura`). Libro giornale/mastro in
`contabilita_gestionale` (coll `scritture_contabili`). ⚠️ **Due piani dei conti**
incompatibili (codici puntati `05.01.01` vs CEE 6-cifre `400100`) — vedi §6.

### BANK — `bank/{bank_statement_import,estratto_conto,assegni,assegni_learning,pos_accredito}`, `bonifici_module/*`, `paypal_statements`, `paypal_api`, `distinte_bpm`, `pagopa`
Importer **canonico estratto conto = `estratto_conto.py`** (→ `estratto_conto_movimenti`,
orchestratore riconciliazioni a valle). Assegni con modello **N:M a quote**
(`assegni_auto_match`, L1-L4). Bonifici (job PDF/ZIP → `bonifici_transfers`). PayPal
(estratti + API Reporting). PagoPA (ricevute + CBILL). ⚠️ `bank_statement_import.py` duplica
l'importer canonico; assegni hanno modelli legacy 1:1 concorrenti; PayPal ha 2 store mapping
+ 2 pipeline riconciliazione — vedi §5-§6.

### WAREHOUSE — `warehouse/dizionario_articoli`
Solo **Dizionario Articoli** (mappa descrizione→piano conti, categorizzazione euristica+AI).
Giacenze/inventario sono competenza dell'app HACCP esterna (coll condivisa `warehouse_inventory`).

### INVOICES/FATTURE — `invoices/{invoices_main,invoices_emesse,fatture_upload,fatture_drive,corrispettivi}`, `fatture_module/*`
`fatture_upload.py` = pipeline **canonica** import fatture passive (XML/P7M/ZIP, singolo+bulk,
crea fornitore, note credito, riconciliazione EC/assegni, storia+libro giornale).
`fatture_module` = `/api/fatture-ricevute` (archivio, pagamento, riconciliazione, PayPal).
Corrispettivi (upload XML/ZIP/CSV, scorporo IVA, sync Prima Nota). ⚠️ Doppia sorgente
`invoices` + `fatture_passive` con dedup a runtime — vedi §6.

### EMPLOYEES/HR — `employees/dipendenti`, `tfr`, `libro_unico_parser`, `f24_parser`, `drive_{cedolini,corrispettivi,quietanze}`, `documenti_fiscali`, `iva`, `fatture_estera_verifica`
**Scelta utente 14/07/2026: il gestionale HR completo è un programma ESTERNO
(AppDipendenti).** In questo repo restano SOLO i dati contabili/fiscali:
anagrafica **`dipendenti`** minima (CRUD, bulk-upsert, dedupe — CF↔cedolino),
**cedolini** (`cedolini`), turni, portale dipendenti, TFR (Art.2120 + acconti +
riconciliazione banca), Libro Unico Zucchetti (presenze+buste). **Rimossi dal
codice**: CRUD contratti di lavoro (`contratti_dipendenti`), CRUD e import
massivo libretti sanitari (`libretti_sanitari`), 17 route in totale — vedi
`AUDIT_DEFINITIVO_SESSIONE_20260714.md` §2 per il dettaglio (route rimosse,
handler event bus aggiornati, file morti eliminati). Ingest Google Drive
(cedolini/corrispettivi/quietanze) invariato.
⚠️ `libro_unico_parser` scrive anagrafica in `employees` invece di `dipendenti`, e buste in
`buste_paga` invece di `cedolini` — vedi §6 (non toccato in questa sessione).

**Fatture ESTERE via email (nuovo 14/07/2026)** — modulo separato ma
strettamente collegato al flusso documentale HR/email: fornitori esteri
(fuori SDI) mandano PDF via email → estrazione AI (`document_ai_extractor`)
→ fattura vera in `invoices` con la stessa pipeline delle fatture XML
(`import_parsed_invoice`, condivisa con `process_xml_bytes`) → coda di
verifica umana (`fatture_estera_verifica.py`, `/api/fatture-estere/*`) →
rating di affidabilità per fornitore (`fatture_estere_verifiche`). Aggancia
gratis il matching PayPal/bonifico e l'alert scadenza già esistenti (nessun
motore di riconciliazione nuovo). Dettaglio completo, diagramma di flusso,
guardie dati: `AUDIT_DEFINITIVO_SESSIONE_20260714.md` §3.

### REPORTS — `reports/{dashboard,exports,simple_exports,report_pdf}`
Dashboard KPI, export Excel/JSON, report PDF (mensile/dipendenti/scadenze/magazzino).
⚠️ `exports.py` (via repository/service) e `simple_exports.py` (query diretta pandas) sono
**due implementazioni parallele** con collezioni divergenti; `dashboard.py /kpi` e `/stats`
restituiscono placeholder fissi a 0 — vedi §5.

### CORE — `suppliers_module/*`, `cash`, `settings(+router)`, `configurazioni`, `finanziaria`, `gestione_riservata`, `commercialista`, `scadenze`, `scadenzario_fornitori`, `pianificazione`, `alerts`, `mutui`, `auto_repair`, `rapido`, `dati_provvisori`, `batch_reprocessing`, `pos_corrispettivi_check`, `chat_router`, `learning_universal`, `learning_machine`, `fornitori_learning`, `openapi_{imprese,it,automotive}`, `sync_relazionale`, `pagopa`, `websocket_realtime`, `agenti`, `paypal_api`, `previsioni_acquisti`, `multi_pagamento`, `operazioni_module/*`, `verifica_coerenza`, `anagrafica_fornitori_xml`
Fornitori (`/api/suppliers` → coll **`fornitori`**), chat AI (Anthropic, `chat_router`),
scadenzario, alert, inserimento rapido, riconciliazione smart (`operazioni_module`),
verifica coerenza, integrazioni OpenAPI.it (imprese/AISP/automotive), agenti AI.

### EMAIL/DOCUMENTI/AI — `documenti`, `documenti_non_associati`, `documents_inbox_classify`, `document_ai`, `ai_parser`, `email_scanner`, `email_download`
Hub documenti `documents_inbox`, monitor IMAP, classificazione (regex + AI), parser AI
Anthropic (`ai_parser`, `document_ai`). ⚠️ 3 sistemi di scansione email paralleli; "classificati"
su 2 collezioni (`documents_classified` vs `documenti_classificati`) — vedi §6.

### NOLEGGIO/VERBALI — `noleggio`, `verbali_noleggio`, `verbali_noleggio_api`, `verbali_riconciliazione`, `trattenute_verbali`, `admin_export`
Flotta veicoli a noleggio (coll `veicoli_noleggio`), verbali/multe da Gmail
(`verbali_noleggio`), riconciliazione verbale→fattura→pagamento→driver, trattenute in
busta paga. ⚠️ **3 router verbali sovrapposti** con schemi divergenti — vedi §5.

### API ESTERNE usate
OpenAPI.it (Company/AISP/Automotive/Visure/XBRL), Anthropic (chat + parser AI documenti),
PayPal Reporting API, Meta WhatsApp Cloud API, Google Drive/Gmail (ingest), VIES/OpenCorporates
(arricchimento fornitori), SMTP (invio commercialista).

## 3. Codice morto ELIMINATO in questa sessione (13/07/2026)
### 3a. Codice morto (zero chiamanti)
- **`app/routers/documenti_module/`** (crud.py, monitor.py, common.py) — package mai montato,
  funzioni duplicate di `documenti.py`. 487 righe.
- **`destinazione_auto()`** in `fatture_module/metodo_pagamento.py` — funzione senza chiamanti.
- **`_get_notifiche_impl()`** in `fiscalita_italiana.py` — funzione mai chiamata (logica inline).
- **`COLLECTION_FATTURE_NOLEGGIO`** in `verbali_noleggio.py` — costante morta.
- **`COL_JOBS`/`COL_TRANSFERS`/`COL_RICONCILIAZIONE_TASKS`** in `bonifici_module/common.py` —
  costanti che puntavano a nomi collezione mai usati (fuorvianti).
- Import inutilizzato `parse_paypal_date` in `fatture_module/pagamento.py`.

### 3b. Duplicati contabili UNIFICATI (tenuto il canonico usato dal frontend)
- **Budget**: rimossi gli endpoint `/api/controllo-gestione/budget*` (FE-inutilizzati).
  Canonico = `/api/contabilita-gestionale/budget*` (usato da `BudgetPrevisionale.jsx`).
- **Chiusura/Apertura esercizio**: rimossi da `fiscalita_italiana.py` (partita doppia CEE,
  FE-inutilizzati). Canonico = `chiusura_esercizio.py` `/api/chiusura-esercizio/*`
  (usato da `ChiusuraEsercizio.jsx`).
- **Export**: rimosso `reports/exports.py` (stub `/excel` vuoto + alias repository, FE-inutilizzato).
  Canonico = `reports/simple_exports.py` (collezioni canoniche dirette).

### 3c. NON rimossi — risultano ancora AGGANCIATI a pagine frontend
La verifica sul frontend ha mostrato che questi "candidati" NON sono morti:
- **`f24_parser.py`**: è il motore di import F24 usato da `documenti.py` (upload F24).
- **`learning_machine.py`** → pagina `LearningMachine.jsx`.
- **`learning_universal.py`** → pagina `LearningMachineUniversale.jsx`.
- **Assegni legacy** (`auto-associa`, `cerca-combinazioni-assegni`, `assegni_learning`) →
  bottoni in `GestioneAssegni.jsx` e `LearningMachine.jsx`.
Rimuoverli richiede prima togliere/ricablare le pagine e i bottoni relativi — decisione
di prodotto, in attesa dell'utente.

### 3d. Codice morto ELIMINATO nella sessione 14/07/2026 (HR esterno + Fatture Estere AI)
- **17 route** rimosse da `employees/dipendenti.py`: CRUD contratti di lavoro,
  CRUD + import massivo libretti sanitari (scelta utente: HR completo è un
  programma esterno, AppDipendenti — qui restano solo cedolini/TFR/anagrafica minima).
- **File interi eliminati** (codice morto verificato, zero import esterni):
  `app/models/employee.py`, `app/services/employee_service.py`,
  `app/repositories/employee_repository.py`,
  `app/scripts/migra_employee_contracts_a_contratti.py`,
  `tests/test_p1_dipendenti_cessazione.py`, `frontend/src/components/attendance/`.
- **Collection dismesse** (dati non purgati, solo codice smesso di leggerle):
  `contratti_dipendenti`, `libretti_sanitari`, `employee_contracts`.
- **Aggiunto** (non rimozione): router `fatture_estera_verifica.py`
  (`/api/fatture-estere`, 3 endpoint) + refactor `fatture_upload.py`
  (`process_xml_bytes` diviso in `import_parsed_invoice` condivisa, riusata
  dalla nuova `process_fattura_estera_pdf`) + nuova collection
  `fatture_estere_verifiche`. Dettaglio completo:
  `AUDIT_DEFINITIVO_SESSIONE_20260714.md`.

## 4. Rami morti / stub (segnalati, non ancora rimossi — a basso rischio)
| Dove | Cosa | Perché |
|---|---|---|
| `invoices_emesse.py` | `POST /upload-xml` | stub: non parsa l'XML, salva solo metadati |
| `fatture_upload.py` | `auto_registra_prima_nota()` | ritorna sempre None → rami `if` morti |
| `pagamento.py` | ramo PDF di `import_paypal` | usa dati hardcoded `PAGAMENTI_PAYPAL_2024/2025` |
| `sync.py` | `auto_conferma_provvisori_per_metodo`, `annulla_auto_conferma` | stub + rollback a vuoto |
| `pos_corrispettivi_check.py` | `verifica-coerenza`, `anomalie-gravi` | **deprecati nel codice** (sostituiti da v2) |
| `documenti.py` | `processa-f24-scaricati`, `/documento/{id}/processa`, `reimporta-da-filesystem` | contratto parser errato / stub / filesystem legacy |
| `email_download.py` | `auto-associa` (v1) | sostituito da `auto-associa-v2` |
| `verbali_noleggio_api.py` | `scarica-posta` | stub "in sviluppo" |
| `f24_riconciliazione.py` | `fix-campo-anno` | migrazione one-off in produzione |
| `f24_main.py` | `upload-zip`, `upload-multiple`, `documents` | schema legacy mai parsato |
| `batch_operations.py` | `auto-riconcilia-tutto` | filtro `importo<0` su coll con importi positivi → non trova nulla |
| `admin.py` | `cleanup-trattenute-disciplinari`, `noleggio/backfill-dati-gestionali` | one-shot post-deploy già consumati |
| `reports/exports.py` | `GET /excel` | stub file vuoto |
| `reports/dashboard.py` | `/kpi`, `/stats` | placeholder fissi a 0 |
| `f24_parser.py` | `salva_tributi()` (nested) | definita, mai chiamata |

## 5. Sistemi PARALLELI / DUPLICATI — richiedono decisione (quale è il canonico)
> Non rimuovibili "alla cieca": due implementazioni coesistono e va scelta quella ufficiale.
1. **Chiusura esercizio**: `chiusura_esercizio.py` (gestionale) vs `fiscalita_italiana.py`
   `/chiusura-esercizio`+`/apertura-esercizio` (partita doppia CEE) — motori e collezioni diversi.
2. **Registrazione fatture in partita doppia**: `contabilita_avanzata /ricategorizza-fatture`
   vs `piano_conti /registra-tutte-fatture`+`/registra-corrispettivi` — stesso `movimenti_contabili`.
3. **Bilancio**: 4 implementazioni (`bilancio.py`, `piano_conti /bilancio`,
   `contabilita_avanzata /bilancio-dettagliato`, `contabilita_italiana /bilancio/*`).
4. **Budget**: `contabilita_gestionale.py` vs `controllo_gestione.py` (stessa coll `budget`).
5. **Cespiti**: `cespiti.py` vs `contabilita_italiana /cespiti/*` (schemi incompatibili).
6. **Importer estratto conto**: `bank/estratto_conto.py` (canonico) vs `bank/bank_statement_import.py`.
7. **Assegni**: modello N:M `assegni_auto_match /auto-match` (canonico) vs legacy 1:1
   (`assegni /auto-associa`, `/associa-beneficiari-robusto`, `/associa-pagamenti-multipli`,
   `/cerca-combinazioni-assegni`, tutto `assegni_learning`).
8. **PayPal**: 2 store mapping fornitore (`paypal_mapping_fornitori` vs `fornitori.paypal_account_id`),
   2 pipeline riconciliazione (`paypal_api /riconcilia` vs `paypal_statements /riconcilia-banca`).
9. **Prima Nota Cassa**: `cash.py` (coll `cash_movements`) parallelo a `prima_nota_cassa`.
10. **Learning**: `learning_machine.py` + `learning_universal.py` (collezioni fantasma,
    credenziali env obsolete) paralleli a `documents_inbox_classify` + `fornitori_learning`.
11. **Export**: `reports/exports.py` vs `reports/simple_exports.py`.
12. **Tre router verbali**: `verbali_noleggio` + `verbali_noleggio_api` + `verbali_riconciliazione`.
13. **F24**: `f24_parser.py` (sottosistema pdfplumber con `f24_pagamenti`/`tributi_pagati`/
    `distinte_f24`) parallelo a `f24_main`/`f24_riconciliazione` (`f24_unificato` + `parser_f24`).
14. **erp_bridge.py** — attivo solo se configurato `ERP_BRIDGE_SECRET`; se Tracciabilità non torna, candidato rimozione.
15. **OpenAPI AISP (PSD2)** in `openapi_it.py` — dipende da consensi mai configurati.

## 6. Incoerenze di SCHEMA trasversali (da sanare, non è codice da cancellare)
- **F24 su ≥5 collezioni** (vedi §2 F24): unificare su `f24_unificato`.
- **`employees` vs `dipendenti`**: `libro_unico_parser` (STEP1) e `verbali_noleggio_api`
  usano `employees`; tutto il resto `dipendenti` → collegamenti che falliscono in silenzio.
- **`cedolini` vs `buste_paga`**: `dipendenti.py`/`drive_cedolini`→`cedolini`;
  `libro_unico_parser`/`distinte_bpm`→`buste_paga`.
- **Due piani dei conti** (puntato vs CEE): i router CEE scrivono header scritture in
  `prima_nota_cassa` → inquinano il saldo cassa letto dai bilanci.
- **Tre formule di saldo Prima Nota** (`list_*` con esclusioni vs `stats` senza vs
  `saldo_finale` parziale) → numeri divergenti tra endpoint.
- **`fatture_passive` vs `invoices`**: doppia lettura con dedup a runtime.
- **`suppliers` vs `fornitori`**: `public_api POST /suppliers` scrive in `suppliers`
  (invisibile al resto); canonica è `fornitori`.
- **"classificati"**: `documents_classified` vs `documenti_classificati`.

## 7. Regole cardine (non violare)
1. Fatture ricevute = **costi** in `invoices`; ricavi solo da `corrispettivi`.
2. Fornitori: collection **`fornitori`** (`suppliers` è solo alias API).
3. Dipendenti: **`dipendenti`** (mai `employees`).
4. F24: **`f24_unificato`** (mai `f24_models` nei nuovi sviluppi).
5. Magazzino: **`warehouse_inventory`** (`warehouse_stocks` deprecata).
6. Saldo F24 mai costo automatico; RC01 = periodo precedente (vedi SPECIFICA_F24).
7. Scritture in partita doppia → `scritture_contabili` (vedi LOGICA_LIBRO_MASTRO).
8. Router nuovo → registrarlo in `app/router_registry.py`, altrimenti 404.
