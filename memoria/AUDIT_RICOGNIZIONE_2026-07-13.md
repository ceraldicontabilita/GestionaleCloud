# AUDIT RICOGNIZIONE COMPLETA — GestionaleCloud (13/07/2026)

Ricognizione dell'intera applicazione: **lettura di tutti i 137 file router** uno
per uno (8 analisi parallele), route table reale, incrocio con l'uso nel frontend,
registro collezioni. Questo file raccoglie **tutto ciò che è stato trovato** e
**tutto ciò che è stato fatto**.

Documenti-mappa collegati (rigenerabili con `python scripts/genera_mappa.py`):
`MAPPA_MODULI.md`, `MAPPA_ROUTER.md`, `MAPPA_ENDPOINT_COMPLETA.md`, `MAPPA_COLLEZIONI.md`.

---

## 0. Numeri

| Metrica | Valore |
|---|---:|
| File router | 137 |
| Endpoint montati (fine ricognizione) | 1105 (erano 1117) |
| Prefissi / tag | 107 / 110 |
| Endpoint usati dal frontend | 639 |
| Endpoint da chiamanti esterni (app collegate/webhook/chatbot/scheduler/API pubblica) | 76 |
| Endpoint senza riferimento noto (da verificare) | 390 |
| Collezioni MongoDB nel registro | 158 |
| Collezioni realmente accedute nel codice | ~154 |
| Test backend | 257 verdi |

Principio guida della pulizia: **se è usato, si tiene**. Non è stato toccato nulla
di agganciato a pagine/bottoni del frontend.

---

## 1. COSA È STATO RIMOSSO (con verifica)

### 1a. Emergent (piattaforma non più usata → ora Render)
- `frontend/src/App.js` + `frontend/src/index.js` — boilerplate dello scaffold
  (entry reale = `main.jsx` → `App.jsx`).
- `frontend/craco.config.js` — il build è **100% Vite** (`npm run build` = `vite build`).
- `frontend/plugins/visual-edits/` (dev-server-setup.js, babel-metadata-plugin.js) —
  tooling Emergent, referenziato solo dal craco morto.
- Tutte le menzioni testuali (PRD, BACKLOG, copilot-instructions, DashboardRelazionale,
  endpoints/03). **Verifica finale: zero occorrenze "emergent".** Build frontend OK.

### 1b. Codice morto backend (zero chiamanti)
- `app/routers/documenti_module/` (crud.py, monitor.py, common.py) — package **mai montato**,
  funzioni duplicate di `documenti.py` (487 righe).
- `destinazione_auto()` in `fatture_module/metodo_pagamento.py` — funzione senza chiamanti.
- `_get_notifiche_impl()` in `fiscalita_italiana.py` — funzione mai chiamata.
- costante `COLLECTION_FATTURE_NOLEGGIO` in `verbali_noleggio.py`.
- costanti `COL_JOBS`/`COL_TRANSFERS`/`COL_RICONCILIAZIONE_TASKS` in `bonifici_module/common.py`
  (puntavano a nomi collezione mai usati → fuorvianti).
- import inutilizzato `parse_paypal_date` in `fatture_module/pagamento.py`.
- riga commentata `F24_UPLOAD_DIR` in `f24/f24_main.py` (filesystem legacy).

### 1c. Stub non implementati e FE-inutilizzati
- `invoices_emesse` `POST /upload-xml` — salvava solo metadati senza parsare l'XML
  (record incompleti, fuorvianti); nessun chiamante frontend.
- `verbali_noleggio_api` `POST /scarica-posta` — stub "Funzionalità in sviluppo".

### 1d. Duplicati contabili unificati (tenuto il canonico usato dal frontend)
- **Budget**: rimossi `/api/controllo-gestione/budget*` (+ modelli BudgetInput/BudgetMensileInput).
  Canonico `/api/contabilita-gestionale/budget*` (pagina BudgetPrevisionale).
- **Chiusura/Apertura esercizio**: rimossi da `fiscalita_italiana.py` (motore CEE).
  Canonico `chiusura_esercizio.py` (pagina ChiusuraEsercizio).
- **Export**: rimosso `reports/exports.py` (stub `/excel` vuoto + alias repository).
  Canonico `reports/simple_exports.py`.

### 1e. Documenti audit storici / point-in-time (superati dalle MAPPA_*)
Rimossi: `AUDIT_TECNICO_COMPLETO`, `AUDIT_PROFESSIONALE`, `AUDIT_REPORT_FINALE`,
`AUDIT_SICUREZZA/PRESTAZIONI/DATABASE/REACT/MATRICE(+json)`, le 6 `VERIFICA_*`,
`HANDOFF_*`, `STATO_STABILITA`, `PROMPT_SESSIONE`, `REGOLE_OPERATIVE_AUTORI`
(workflow Emergent), i diari root (`DIARIO`, `RIASSUNTO`, `PIANO_LAVORO_RELAZIONALE`,
`auth_testing`, `test_result`, `test_reports/`), e gli script non-CI dei report
(`audit_react`, `classifica_matrice`, `estrai_matrice_api`).
Tenuti: `AUDIT_STATIC_REPORT` (rigenerato dalla CI `audit-static.yml`),
`RICONCILIAZIONE_AUDIT` (referenziato dal codice), tutte le SPECIFICA/LOGICA/MAPPA.

---

## 2. COSA È STATO TROVATO MA NON RIMOSSO (è vivo / serve decisione)

### 2a. Sottosistemi paralleli ancora agganciati al frontend (NON toccati)
| Sistema | Pagina/uso frontend |
|---|---|
| `f24_parser.py` | motore di import F24 usato da `documenti.py` |
| `learning_machine.py` | pagina **LearningMachine.jsx** |
| `learning_universal.py` | pagina **LearningMachineUniversale.jsx** |
| Assegni legacy (`auto-associa`, `cerca-combinazioni-assegni`, `assegni_learning`) | bottoni in **GestioneAssegni.jsx** |

### 2b. Altri sistemi paralleli / duplicati (debito, decisione futura)
1. Registrazione fatture in partita doppia: `contabilita_avanzata /ricategorizza-fatture`
   vs `piano_conti /registra-tutte-fatture` (+`/registra-corrispettivi`).
2. Bilancio: 4 implementazioni (`bilancio.py`, `piano_conti /bilancio`,
   `contabilita_avanzata /bilancio-dettagliato`, `contabilita_italiana /bilancio/*`).
3. Cespiti: `cespiti.py` vs `contabilita_italiana /cespiti/*` (schemi incompatibili).
4. Importer estratto conto: `bank/estratto_conto.py` (canonico) vs `bank/bank_statement_import.py`.
5. PayPal: 2 store mapping fornitore + 2 pipeline riconciliazione con flag diversi.
6. Prima Nota Cassa: `cash.py` (coll `cash_movements`) parallela a `prima_nota_cassa`.
7. Import fornitori Excel: `/upload-excel` vs `/import-excel` (suppliers_module).
8. Tre router verbali: `verbali_noleggio` + `verbali_noleggio_api` + `verbali_riconciliazione`.
9. Dati provvisori: `dati_provvisori.py` (coll `dati_provvisori`) vs `sync.get_fatture_provvisorie`.
10. `erp_bridge.py` — attivo solo con `ERP_BRIDGE_SECRET`; `openapi_it.py` AISP — PSD2 mai configurato.

---

## 3. INCOERENZE DI SCHEMA TRASVERSALI (da sanare, non è codice da cancellare)
- **F24 su ≥5 collezioni**: `f24_unificato` (canonica), `f24_commercialista` (alias non più
  scritta, ma ancora letta da `f24_analisi`), `f24_tributi` (documents_inbox_classify),
  `f24_models`/`Collections.F24_MODELS` (chat/public), `f24_parser.py`
  (`f24_pagamenti`/`tributi_pagati`/`distinte_f24`).
- **`employees` vs `dipendenti`**: `libro_unico_parser` (STEP1) e `verbali_noleggio_api`
  usano `employees`; il resto `dipendenti` → collegamenti che falliscono in silenzio.
- **`cedolini` vs `buste_paga`**: `dipendenti.py`/`drive_cedolini`→`cedolini`;
  `libro_unico_parser`/`distinte_bpm`→`buste_paga`.
- **Due piani dei conti** (puntato `05.01.01` vs CEE 6-cifre `400100`): i router CEE
  (`contabilita_italiana`, `fiscalita_italiana`) scrivono header scritture in
  `prima_nota_cassa` → inquinano il saldo cassa letto dai bilanci.
- **Tre formule di saldo Prima Nota** (`list_*` con esclusioni vs `stats` senza vs
  `saldo_finale` parziale) → numeri divergenti tra endpoint.
- **`fatture_passive` vs `invoices`**: doppia lettura con dedup a runtime.
- **`suppliers` vs `fornitori`**: `public_api POST /suppliers` scrive in `suppliers`
  (invisibile al resto); canonica è `fornitori`.
- **"classificati"**: `documents_classified` vs `documenti_classificati`.

---

## 4. BUG e CORRETTEZZA emersi dalla lettura (segnalazioni, NON ancora corretti)
> Non richiesti in questa fase, ma trovati leggendo il codice. Da valutare a parte.

1. **`scadenze.py` dashboard-widget**: `f24_da_pagare_commercialista` interroga
   `f24_unificato` mentre i F24 da email sono in `f24_commercialista` → i F24 arrivati
   via email non vengono contati.
2. **`batch_operations.py /auto-riconcilia-tutto`**: filtra `importo < 0` su
   `estratto_conto_movimenti` che salva **sempre importi positivi** → non trova mai nulla.
3. **`libro_unico_parser.py`**: anagrafica upsert su `employees` ma lo STEP TFR cerca su
   `dipendenti` → il collegamento TFR/Prima Nota non trova il record appena creato.
4. **`verbali_riconciliazione.py riconcilia_verbale`**: cerca fatture su `items.descrizione`
   (campo `items` inesistente; il vero campo è `linee`) → ramo morto.
5. **`assegni.py /correggi-associazione`**: imposta `stato="associato"`, valore non presente
   in `ASSEGNO_STATI`.
6. **`estratto_conto.py /force-reimport`**: il docstring dichiara "cancella tutto l'anno" ma
   il codice NON cancella nulla (comportamento diverso dal nome).
7. **`riconciliazione_f24_banca.py`**: `POST /upload-estratto-bpm` popola `movimenti_f24_banca`
   ma `POST /riconcilia-f24` legge da `estratto_conto_movimenti` → collezione scritta mai riletta.
8. **`documenti.py /processa-f24-scaricati`**: contratto parser errato (`success`/`f24_data`
   che il parser non restituisce) → di fatto non funzionante.
9. **`multi_pagamento.registra_pagamento`**: scrittura Prima Nota non idempotente (`PAG-{id}`)
   fuori dallo schema di dedup `FATT-{id}` → possibili doppioni se la stessa fattura passa
   anche da `conferma_fattura_provvisoria`.
10. **`batch_reprocessing._job_state`** e i task riconciliazione bonifici: stato in variabile
    globale di modulo → non sopravvive al restart, non multi-worker.
11. **`gestione_riservata.py`**: gli endpoint `/movimenti` non verificano il codice riservato
    (protezione solo lato UI); login logga il codice errato in chiaro.
12. **token/api-key in query string**: `openapi_*` e API pubblica `v1` accettano il token via
    `?token=`/`?api_key=` (loggabile).

---

## 5. Come è costruita l'app (sintesi domini)
FastAPI + Motor (MongoDB) · React 18 + Vite · Deploy: push su `main` → Render →
`impresasemplice.online`. Registrazione router unica in `app/router_registry.py`
(12 gruppi). Flusso: PEC/Gmail/Drive → parser → `invoices` (+ auto-routing cassa/banca,
`fornitori`, `storia_fatture`, `scritture_contabili`); estratto conto → riconciliazione;
corrispettivi → split cassa/POS; cedolini → `cedolini`+`prima_nota_salari`; F24 →
`f24_unificato`. Dettaglio per dominio in `MAPPA_MODULI.md §2`.

API esterne usate: OpenAPI.it (Company/AISP/Automotive/Visure/XBRL), Anthropic (chat +
parser AI), PayPal Reporting, Meta WhatsApp, Google Drive/Gmail, VIES/OpenCorporates, SMTP.

---

## 6. Verifica finale
- Frontend build: **OK** (Vite).
- Backend: app boota (**1105 route**), **257 test verdi**, audit statico invariato.
- Git: tutto su `main` e sul branch di lavoro (stesso commit).
