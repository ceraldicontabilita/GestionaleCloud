# AUDIT ATOMICO — GestionaleCloud (intera applicazione)

Data: 2026-07-14. Documento di **livello 0** (indice/sintesi navigabile):
non ripete a mano dati già generati meccanicamente da altri file —
li verifica, li aggiorna dove serviva, e li collega in un'unica mappa
coerente. Ogni numero sotto è stato **rigenerato o verificato oggi**
(non copiato da vecchie sessioni), tranne dove esplicitamente segnalato
come storico/superato.

**Come è organizzato questo documento**:
1. §1 Stack e albero di struttura
2. §2 Inventario ROUTER (108 prefissi, verificato a runtime)
3. §3 Inventario ENDPOINT (1059, rimando al file atomico)
4. §4 I 12 domini funzionali (come funziona ognuno)
5. §5 Collezioni MongoDB
6. §6 Cosa NON funziona/manca oggi (debito tecnico reale, verificato)
7. §7 Cosa è STATO implementato in questa sessione (14/07/2026)
8. §8 Indice di tutti i documenti di audit del repo

---

## 1. Stack e albero di struttura

| Layer | Tecnologia |
|---|---|
| Backend | FastAPI + Motor (MongoDB async) |
| Frontend | React 18 + Vite |
| DB | MongoDB Atlas, database `Gestionale`, cluster `cluster0.vofh7iz` |
| Deploy | push su `main` → Render → `impresasemplice.online` (`frontend/dist/` versionato) |
| Scheduler | APScheduler, unico punto `app/scheduler.py::start_scheduler()` avviato in `app/main.py::lifespan` |
| Design | Inline styles da `frontend/src/lib/utils.js` (no Tailwind/no component library CSS) |

### 1.1 Albero `app/` (backend, profondità 2)

```
app/
├── main.py                      ← entry point FastAPI (lifespan, CORS, middleware)
├── router_registry.py           ← UNICO punto di montaggio di tutti i router (12 gruppi _register_*)
├── database.py                  ← connessione Motor + classe Collections (legacy)
├── db_collections.py            ← costanti COLL_* (158) — "fonte di verità" dichiarata, uso reale minoritario
├── config.py                    ← Settings (env)
├── scheduler.py                 ← APScheduler, tutti i job automatici
├── f24_alert_system.py
├── agents/            (6 file)  ← agenti AI
├── cli/                (2 file)
├── config/              (1 file)
├── constants/          (4 file)
├── core/                (1 file)
├── engines/            (8 file)  ← tributi_engine, fiscale_engine, liquidazione_iva_engine, riepilogo_iva_engine, ...
├── exceptions/          (2 file)
├── handlers/            (9 file) ← handler legacy (non event bus)
├── knowledge/           (1 file)
├── middleware/          (4 file) ← auth, rate limit, performance/cache
├── models/             (11 file) ← Pydantic schemas
├── parsers/            (12 file) ← fattura_elettronica_parser, f24_parser, ...
├── repositories/       (11 file)
├── routers/            (78 file diretti + 12 sottopacchetti)
│   ├── accounting/      (8)  bilancio, piano_conti, centri_costo, contabilita_avanzata,
│   │                         contabilita_gestionale, prima_nota_salari, regole_categorizzazione
│   ├── bank/             (9)  bank_statement_import, estratto_conto, assegni, assegni_learning, pos_accredito, riconciliazione_f24_banca
│   ├── bonifici_module/  (7)  jobs, transfers, riconciliazione, associazioni
│   ├── employees/        (2)  dipendenti.py (28 endpoint, ridotto 14/07), (tfr è fuori, top-level)
│   ├── f24/              (5)  f24_main, f24_riconciliazione, f24_public, email_f24
│   ├── fatture_module/   (7)  crud, pagamento, metodo_pagamento (/api/fatture-ricevute)
│   ├── invoices/         (7)  invoices_main, invoices_emesse, fatture_upload, fatture_drive, corrispettivi
│   ├── operazioni_module/(3)  operazioni "da confermare" + smart matching
│   ├── prima_nota_module/(9)  cassa, banca, salari, attese, sync, stats, manutenzione
│   ├── reports/          (4)  dashboard, exports, simple_exports, report_pdf
│   ├── suppliers_module/ (7)  base, bulk, iban, import_export, validation
│   ├── warehouse/        (2)  dizionario_articoli
│   └── fatture_estera_verifica.py            ← NUOVO 14/07/2026 (top-level, non in sottopacchetto)
├── schemas/             (6 file)
├── scripts/            (19 file) ← script one-shot/migrazione (es. genera_mappa.py è in scripts/ separato)
├── services/          (117 file diretti + 3 sottopacchetti)
│   ├── handlers/         (9)  event bus handlers (fattura_handlers, dipendente_handlers, ...)
│   ├── noleggio/         (5)
│   └── suppliers/        (5)
├── static/               (1)
└── utils/               (19 file)
```

### 1.2 Albero `frontend/src/` (profondità 2)

```
frontend/src/
├── main.jsx                     ← router piatto (createBrowserRouter, un solo array children)
├── navigation.config.js         ← UNICA fonte di verità dei menu (desktop/mobile/altro)
├── api.js                       ← istanza axios unica, interceptor auth
├── components/        (17 file diretti)
│   ├── ds/              (13)  Design System: Card, Table, Button, Badge, PageHeader, Input, Select, ListaAdattiva, HubTabs, Tabs, ...
│   ├── layout/           (1)
│   ├── prima-nota/       (3)
│   └── ui/              (47)  ConfirmDialog, toast (sonner), modali, ecc.
├── contexts/            (3 file)
├── hooks/                (9 file)
├── lib/                  (2 file)  utils.js (palette/design tokens), queryClient.js
├── pages/               (59 file diretti = 59 pagine standalone)
│   └── hub/              (11) *Hub.jsx — pagine "contenitore" con tab (FattureHub, PrimaNotaHub, ContabilitaHub, ...)
├── stores/               (2 file)
├── styles/               (2 file + 5 in ds/)
└── utils/                (3 file)
```

---

## 2. Inventario ROUTER — 108 prefissi, verificato a runtime oggi

Rigenerato **oggi** con `python scripts/genera_mappa.py` (legge la route
table REALE via `register_all_routers`, non un elenco scritto a mano — se
un router non è montato qui, ritorna 404 in produzione). Fonte completa:
**`memoria/MAPPA_ROUTER.md`**. Legenda FE: `✓` usato dal frontend ·
`ext` chiamante esterno legittimo (app collegate/webhook/chatbot/scheduler/API
pubblica) · `—` nessun riferimento noto nel FE (non necessariamente morto:
va incrociato con §6).

| Prefisso | Endpoint | FE | Moduli (file router) |
|---|---:|:-:|---|
| `/api/admin` | 19 | ✓ | admin, admin_export, admin_rollback |
| `/api/agenti` | 8 | ext | agenti |
| `/api/ai-parser` | 11 | ext | ai_parser |
| `/api/alerts` | 7 | ✓ | alerts |
| `/api/anagrafica-fornitori` | 1 | ✓ | anagrafica_fornitori_xml |
| `/api/archivio-bonifici` | 28 | ✓ | bank.bonifici_import_unificato, bonifici_module.* |
| `/api/assegni` | 38 | ✓ | bank.assegni, bank.assegni_learning, public_api |
| `/api/auth` | 5 | ext | auth, pin_login |
| `/api/auto-repair` | 1 | ✓ | auto_repair |
| `/api/bank` | 2 | ✓ | public_api |
| `/api/bank-statement` | 6 | ✓ | bank.bank_statement_import |
| `/api/batch` | 6 | — | batch_operations |
| `/api/batch-reprocess` | 5 | ✓ | batch_reprocessing |
| `/api/bilancio` | 7 | ✓ | accounting.bilancio |
| `/api/cash` | 10 | ✓ | cash, public_api |
| `/api/cedolini` | 4 | — | drive_cedolini |
| `/api/centri-costo` | 10 | ✓ | accounting.centri_costo |
| `/api/cespiti` | 11 | ✓ | cespiti |
| `/api/chat` | 3 | ✓ | chat_router |
| `/api/chiusura-esercizio` | 7 | ✓ | chiusura_esercizio |
| `/api/commercialista` | 14 | ✓ | commercialista |
| `/api/conferma` | 1 | — | dati_provvisori |
| `/api/conferma-tutte` | 1 | — | dati_provvisori |
| `/api/config` | 9 | ✓ | configurazioni |
| `/api/contabilita` | 10 | ✓ | accounting.contabilita_avanzata, contabilita_italiana |
| `/api/contabilita-gestionale` | 14 | ✓ | accounting.contabilita_gestionale |
| `/api/controllo-gestione` | 4 | ✓ | controllo_gestione |
| `/api/corrispettivi` | 26 | ✓ | drive_corrispettivi, invoices.corrispettivi |
| `/api/dashboard` | 9 | ✓ | public_api, reports.dashboard |
| `/api/data-deletion` | 1 | — | legal_pages |
| `/api/dati-provvisori` | 6 | — | dati_provvisori |
| `/api/dipendenti` | 28 | ✓ | employees.dipendenti *(era 45 fino al 13/07 — vedi §7)* |
| `/api/dizionario-articoli` | 11 | ✓ | warehouse.dizionario_articoli |
| `/api/document-ai` | 10 | ✓ | document_ai |
| `/api/documenti` | 28 | ✓ | documenti |
| `/api/documenti-fiscali` | 2 | ✓ | documenti_fiscali |
| `/api/documenti-inbox` | 5 | ✓ | documents_inbox_classify |
| `/api/documenti-non-associati` | 7 | ✓ | documenti_non_associati |
| `/api/email-download` | 40 | ✓ | email_download |
| `/api/email-scanner` | 5 | ✓ | email_scanner |
| `/api/erp` | 2 | ext | erp_bridge |
| `/api/estratto-conto-movimenti` | 13 | ✓ | bank.estratto_conto |
| `/api/exports` | 8 | — | reports.simple_exports |
| `/api/f24` | 27 | ✓ | drive_quietanze, f24.f24_main |
| `/api/f24-analisi` | 4 | ✓ | f24_analisi |
| `/api/f24-email` | 7 | ✓ | f24.email_f24 |
| `/api/f24-email-settings` | 8 | ✓ | f24_email_settings |
| `/api/f24-public` | 11 | ext | f24.f24_public, public_api |
| `/api/f24-riconciliazione` | 23 | ✓ | bank.riconciliazione_f24_banca, f24.f24_riconciliazione |
| `/api/fatture` | 15 | ✓ | invoices.fatture_drive, invoices.fatture_upload |
| `/api/fatture-estere` | 3 | ✓ | fatture_estera_verifica **← NUOVO 14/07/2026** |
| `/api/fatture-ricevute` | 19 | ✓ | fatture_module.crud, fatture_module.pagamento |
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
| `/api/noleggio` | 13 | ✓ | noleggio |
| `/api/openapi` | 12 | ext | openapi_it |
| `/api/openapi-automotive` | 6 | ext | openapi_automotive |
| `/api/openapi-imprese` | 6 | ext | openapi_imprese |
| `/api/operazioni-da-confermare` | 10 | ✓ | operazioni_module, operazioni_module.smart |
| `/api/pagamenti` | 6 | ✓ | multi_pagamento |
| `/api/paghe` | 3 | — | distinte_bpm, f24_parser, libro_unico_parser |
| `/api/pagopa` | 8 | ✓ | pagopa |
| `/api/partite-aperte` | 3 | ✓ | partite_aperte_api |
| `/api/paypal-api` | 11 | ✓ | paypal_api |
| `/api/paypal-statements` | 13 | ✓ | paypal_statements |
| `/api/pianificazione` | 5 | ✓ | pianificazione, public_api |
| `/api/piano-conti` | 12 | ✓ | accounting.piano_conti |
| `/api/portal` | 1 | ext | public_api |
| `/api/pos-accredito` | 5 | — | bank.pos_accredito |
| `/api/pos-corrispettivi` | 8 | ✓ | pos_corrispettivi_check |
| `/api/previsioni-acquisti` | 5 | ✓ | previsioni_acquisti |
| `/api/prima-nota` | 63 | ✓ | prima_nota_module.* (8 sottomoduli) |
| `/api/prima-nota-salari` | 14 | ✓ | accounting.prima_nota_salari |
| `/api/privacy` | 1 | — | legal_pages |
| `/api/proposte` | 1 | — | dati_provvisori |
| `/api/rapido` | 8 | ✓ | rapido |
| `/api/realtime` | 1 | — | websocket_realtime |
| `/api/regole` | 7 | ✓ | accounting.regole_categorizzazione |
| `/api/report-pdf` | 4 | — | reports.report_pdf |
| `/api/ricerca-globale` | 1 | — | public_api |
| `/api/riconciliazione` | 1 | ✓ | riconciliazione_stats_api |
| `/api/rifiuta` | 1 | — | dati_provvisori |
| `/api/scadenzario-fornitori` | 6 | ✓ | scadenzario_fornitori |
| `/api/scadenze` | 10 | ✓ | scadenze |
| `/api/settings` | 12 | ✓ | settings, settings_router |
| `/api/suppliers` | 32 | ✓ | public_api, suppliers_module.* (5 sottomoduli) |
| `/api/sync` | 8 | ✓ | sync_relazionale |
| `/api/terms` | 1 | — | legal_pages |
| `/api/tfr` | 17 | ✓ | tfr |
| `/api/trattenute-verbali` | 7 | — | trattenute_verbali |
| `/api/utenti` | 4 | ✓ | utenti |
| `/api/v1` | 5 | ext | public_api |
| `/api/verbali-noleggio` | 31 | ✓ | verbali_noleggio, verbali_noleggio_api |
| `/api/verbali-riconciliazione` | 26 | ✓ | verbali_riconciliazione |
| `/api/verifica-coerenza` | 7 | ✓ | verifica_coerenza |
| `/api/warehouse` | 6 | ✓ | public_api |
| `/api/whatsapp` | 5 | ext | whatsapp_webhook |
| `/data-deletion`, `/privacy`, `/terms` | 1 ciascuno | ext | legal_pages (doppia registrazione senza `/api`) |

**Totale: 1059 endpoint reali.** I 3 prefissi con più endpoint:
`/api/prima-nota` (63), `/api/email-download` (40), `/api/assegni` (38).

### 2.1 Router ELIMINATI in questa sessione

Nessun **prefisso** intero è stato eliminato (nessun `app.include_router`
rimosso). È stato eliminato **contenuto interno** a un router esistente:

- `employees/dipendenti.py`: **17 endpoint rimossi** (contratti di lavoro,
  libretti sanitari) — il prefisso `/api/dipendenti` resta montato, passa
  da 45 a 28 endpoint.

Ed è stato **aggiunto** un router nuovo:
- `app/routers/fatture_estera_verifica.py` → prefisso `/api/fatture-estere`
  (3 endpoint), registrato in `router_registry.py::_register_invoices`.

Dettaglio riga-per-riga di entrambi: `AUDIT_DEFINITIVO_SESSIONE_20260714.md`.

---

## 3. Inventario ENDPOINT — 1059, atomico

Il dettaglio di **ogni singolo endpoint** (metodo, path esatto, uso
frontend, file) è generato meccanicamente e vive in
**`memoria/MAPPA_ENDPOINT_COMPLETA.md`** (1622 righe, organizzato per tag/
gruppo — es. "AI Parser (11)", "Dipendenti (28)", "Fatture Estere Verifica
(3)"). Non riprodotto qui per intero: è troppo grande per un documento di
sintesi e **si disallinea a ogni modifica** — l'unico modo corretto di
consultarlo è rigenerarlo (`python scripts/genera_mappa.py`) e leggerlo,
non copiarlo in un altro file statico.

Riepilogo uso: **630 endpoint** referenziati dal frontend, **76**
chiamanti esterni legittimi, **353** senza riferimento noto (candidati
verifica — molti sono script di manutenzione one-shot, tool della chat AI,
o endpoint dietro allowlist non ancora integrati in UI: **non equivale**
a "morto", vedi §6 per la lista di ciò che è *confermato* morto/duplicato).

---

## 4. I 12 domini funzionali — come funziona l'applicazione

Narrativa completa (letta file-router-per-file-router) in
**`memoria/MAPPA_MODULI.md`** (aggiornata oggi). Sintesi:

| Dominio | Router principali | Cosa fa |
|---|---|---|
| **Auth & Public** | `auth`, `pin_login`, `public_api`, `erp_bridge`, `legal_pages`, `whatsapp_webhook`, `utenti` | Login admin (JWT HS256 cookie) + login PIN operatori; API pubblica v1 con api-key; ponte inbound da ceraldiapp.it |
| **F24** | `f24/*`, `f24_analisi`, `f24_email_settings`, `bank/riconciliazione_f24_banca` | Collection canonica `f24_unificato`; parse PDF commercialista → riconciliazione quietanza+banca; motore normativo `tributi_engine` (DM10/RC01, ravvedimenti) |
| **Accounting/Contabilità** | `accounting/*`, `contabilita_italiana`, `fiscalita_italiana`, `iva`, `cespiti`, `mutui`, `chiusura_esercizio`, `controllo_gestione` | Bilancio (SP/CE art.2425), partita doppia, IVA per competenza (**modulo più maturo**: liquidazioni stati/versioni), centri di costo 4 settori HORECA, cespiti/ammortamenti, chiusura esercizio, budget, mutui |
| **Bank** | `bank/*`, `bonifici_module/*`, `paypal_statements`, `paypal_api`, `pagopa` | Importer canonico estratto conto (`estratto_conto.py`); assegni N:M a quote; bonifici (job PDF/ZIP); PayPal (estratti + API); PagoPA |
| **Warehouse** | `warehouse/dizionario_articoli` | Solo Dizionario Articoli (mappa descrizione→piano conti). Giacenze fisiche sono dell'app HACCP esterna |
| **Invoices/Fatture** | `invoices/*`, `fatture_module/*` | `fatture_upload.py` = pipeline canonica import fatture passive (XML/P7M/ZIP + **fatture estere PDF via AI, nuovo 14/07**), crea fornitore, note credito, riconciliazione EC/assegni |
| **Employees/HR** | `employees/dipendenti`, `tfr`, `libro_unico_parser`, `fatture_estera_verifica` | **Dal 14/07: solo anagrafica minima + cedolini + TFR** (HR completo su AppDipendenti esterna). Libro Unico Zucchetti, ingest Drive |
| **Reports** | `reports/*` | Dashboard KPI, export Excel/JSON, report PDF |
| **Core** | `suppliers_module/*`, `cash`, `settings`, `scadenze`, `alerts`, `chat_router`, `operazioni_module/*`, `verifica_coerenza`, ... | Fornitori (coll `fornitori`), chat AI Anthropic, scadenzario, alert, riconciliazione smart |
| **Email/Documenti/AI** | `documenti`, `documents_inbox_classify`, `document_ai`, `ai_parser`, `email_scanner`, `email_download` | Hub documenti `documents_inbox`, monitor IMAP, classificazione regex+AI, parser AI Anthropic |
| **Noleggio/Verbali** | `noleggio`, `verbali_noleggio*`, `verbali_riconciliazione`, `trattenute_verbali` | Flotta veicoli, verbali/multe da Gmail, riconciliazione verbale→fattura→pagamento→driver |
| **API esterne** | — | OpenAPI.it, Anthropic, PayPal Reporting, Meta WhatsApp Cloud, Google Drive/Gmail, VIES/OpenCorporates, SMTP |

### 4.1 Flusso dati principale (invariato)

```
Email Aruba PEC / Gmail / Drive → download XML·P7M·PDF → parser →
  fatture passive → invoices  → auto-routing cassa/banca (metodo fornitore)
                              → aggiorna fornitore (fornitori)
                              → scrittura in movimenti_contabili (libro giornale)
  fatture ESTERE (PDF email) → estrazione AI → invoices (stesso schema)   [NUOVO 14/07]
                              → coda verifica utente → rating fornitore
  estratto conto XLS/CSV → estratto_conto_movimenti → riconciliazione con fatture/partite
  corrispettivi XML      → corrispettivi → split contanti (cassa) / POS (banca)
  cedolini PDF Zucchetti → cedolini → collega dipendente → prima_nota_salari
  F24 PDF                → f24_unificato → quietanza → riconciliazione banca
```

---

## 5. Collezioni MongoDB

Inventario completo (158 collezioni registrate) in
**`memoria/MAPPA_COLLEZIONI.md`** (generata 13/07 dal registro
`app/db_collections.py`, 2 righe aggiornate oggi — vedi §7). Le 10 più
usate nel codice:

| Collezione | Usi | Ruolo |
|---|---:|---|
| `invoices` | 256 | Collezione UNICA fatture passive (italiane XML + estere PDF-AI) |
| `f24_unificato` | 148 | Collezione UNICA F24 |
| `documents_inbox` | 123 | Staging documenti da email |
| `verbali_noleggio` | 116 | Verbali/multe |
| `estratto_conto_movimenti` | 113 | Collezione UNICA movimenti bancari |
| `corrispettivi` | 107 | UNICA fonte ricavi |
| `prima_nota_cassa` | 82 | Prima nota cassa |
| `dipendenti` | 81 | Anagrafica HR minima (mai `employees`) |
| `prima_nota_banca` | 78 | Prima nota banca |
| `fornitori` | 67 | Anagrafica fornitori (mai `suppliers`) |

**Nota sulla convenzione dei nomi**: nonostante esistano DUE registri
dichiarati come "fonte di verità" (`Collections` in `app/database.py`,
legacy; `COLL_*` in `app/db_collections.py`, "unica" per dichiarazione nel
docstring), la pratica reale nel codice è **stringa letterale diretta**
`db["nome"]` nell'80%+ dei casi (1762 occorrenze contro 33 file che
importano da `Collections` e 8 da `db_collections.py`). Non è stato
uniformato in questa sessione né in quelle precedenti — è debito tecnico
noto, non bloccante.

Collection **rimosse/aggiunte oggi**: vedi §7.

---

## 6. Cosa NON funziona / manca oggi — debito tecnico VERIFICATO

⚠️ **`memoria/BACKLOG.md` è datato Aprile 2026 ed è SUPERATO**: descrive
come "vuote"/"non implementate" pagine Mutui, Budget, Cespiti, Chiusura
Esercizio, Controllo Mensile — che oggi hanno router attivi e montati con
endpoint reali (`/api/mutui` 13, `/api/cespiti` 11,
`/api/chiusura-esercizio` 7, `/api/contabilita-gestionale` 14 inclusi
budget). **Non usarlo come riferimento per "cosa manca oggi"** — è tenuto
solo come archivio storico delle richieste originali. Le liste sotto sono
verificate al 13-14/07/2026.

### 6.1 Rami morti / stub confermati (basso rischio, segnalati non rimossi)

Da `MAPPA_MODULI.md` §4 — endpoint che esistono ma non fanno quello che
promettono (stub, dati hardcoded, contratto errato, deprecati sostituiti):

| Dove | Cosa | Perché |
|---|---|---|
| `invoices_emesse.py` | `POST /upload-xml` | stub: non parsa l'XML, salva solo metadati |
| `fatture_upload.py` | `auto_registra_prima_nota()` | ritorna sempre None in certi rami → `if` morti (⚠️ verificare: in questa sessione la funzione è stata riletta e riusata correttamente dal flusso fatture estere, ma il ramo storico segnalato qui non è stato riverificato oggi) |
| `pagamento.py` | ramo PDF di `import_paypal` | dati hardcoded `PAGAMENTI_PAYPAL_2024/2025` |
| `sync.py` | `auto_conferma_provvisori_per_metodo`, `annulla_auto_conferma` | stub + rollback a vuoto |
| `pos_corrispettivi_check.py` | `verifica-coerenza`, `anomalie-gravi` | deprecati (sostituiti da v2) |
| `documenti.py` | `processa-f24-scaricati`, `/documento/{id}/processa`, `reimporta-da-filesystem` | contratto parser errato / stub / filesystem legacy |
| `email_download.py` | `auto-associa` (v1) | sostituito da `auto-associa-v2` |
| `verbali_noleggio_api.py` | `scarica-posta` | stub "in sviluppo" |
| `f24_riconciliazione.py` | `fix-campo-anno` | migrazione one-off in produzione |
| `f24_main.py` | `upload-zip`, `upload-multiple`, `documents` | schema legacy mai parsato |
| `batch_operations.py` | `auto-riconcilia-tutto` | filtro `importo<0` su collection con importi positivi → non trova mai nulla |
| `reports/exports.py` | `GET /excel` | stub file vuoto |
| `reports/dashboard.py` | `/kpi`, `/stats` | placeholder fissi a 0 |

### 6.2 Sistemi PARALLELI/DUPLICATI — richiedono una decisione (quale è il canonico)

Da `MAPPA_MODULI.md` §5 — coppie/gruppi di implementazioni che coesistono
per lo stesso scopo, non rimovibili "alla cieca":

1. Chiusura esercizio: `chiusura_esercizio.py` vs `fiscalita_italiana.py`
2. Registrazione fatture partita doppia: `contabilita_avanzata` vs `piano_conti`
3. Bilancio: **4 implementazioni** (`bilancio.py`, `piano_conti`, `contabilita_avanzata`, `contabilita_italiana`)
4. Budget: `contabilita_gestionale.py` vs `controllo_gestione.py`
5. Cespiti: `cespiti.py` vs `contabilita_italiana` (schemi incompatibili)
6. Importer estratto conto: `bank/estratto_conto.py` (canonico) vs `bank/bank_statement_import.py`
7. Assegni: modello N:M (canonico) vs legacy 1:1 (5 endpoint diversi)
8. PayPal: 2 store mapping fornitore, 2 pipeline riconciliazione
9. Prima Nota Cassa: `cash.py` parallelo a `prima_nota_cassa`
10. Learning: `learning_machine.py`+`learning_universal.py` (collezioni fantasma) paralleli a `documents_inbox_classify`+`fornitori_learning`
11. Export: `reports/exports.py` vs `reports/simple_exports.py`
12. **3 router verbali sovrapposti**: `verbali_noleggio` + `verbali_noleggio_api` + `verbali_riconciliazione`
13. F24: `f24_parser.py` (sottosistema pdfplumber parallelo) vs `f24_main`/`f24_riconciliazione`
14. `erp_bridge.py` — attivo solo se `ERP_BRIDGE_SECRET` configurato
15. OpenAPI AISP (PSD2) — dipende da consensi mai configurati

### 6.3 Incoerenze di SCHEMA trasversali

Da `MAPPA_MODULI.md` §6:
- F24 frammentato su ≥5 collezioni (unificare su `f24_unificato`)
- `employees` vs `dipendenti`: `libro_unico_parser` e `verbali_noleggio_api` scrivono ancora su `employees` → collegamenti falliti in silenzio
- `cedolini` vs `buste_paga`: stesso problema, moduli diversi scrivono su collection diverse
- Due piani dei conti incompatibili (codici puntati vs CEE 6 cifre)
- Tre formule di saldo Prima Nota che danno numeri divergenti
- `fatture_passive` vs `invoices`: doppia lettura con dedup a runtime
- `suppliers` vs `fornitori`: un solo endpoint scrive ancora sull'alias sbagliato
- "classificati": `documents_classified` vs `documenti_classificati`

### 6.4 Automatismi dichiarati ma NON schedulati (prima di oggi)

Da `memoria/AUDIT_AUTOMATISMI.md` (audit dedicato, sola lettura, 14/07):
metodologia = per ogni automatismo dichiarato, verifica se è
`app.scheduler.py::start_scheduler()` o agganciato a un evento reale.
**Risolti in questa sessione**: scansione notifiche Aruba (job
`aruba_notifiche_scan`), fatture estere via email (job
`mittenti_email_sync` + estrazione AI, oggi anche coda di verifica).
**Ancora aperti**: anomalie IVA calcolate solo su richiesta (mai
proattive); cespiti/ammortamenti e TFR annuale restano 100% manuali per
scelta (corretto, azioni deliberate) ma senza nemmeno un promemoria "è ora
di farlo".

---

## 7. Cosa è STATO implementato in questa sessione (14/07/2026)

Dettaglio tecnico completo, endpoint-per-endpoint, con diagrammi di
flusso: **`memoria/AUDIT_DEFINITIVO_SESSIONE_20260714.md`**. Sintesi:

**A — Dipendenti**: rimossi contratti di lavoro e libretti sanitari dal
codice (17 endpoint, 7 file eliminati, 3 collection dismesse) — scelta
utente: il gestionale HR completo è un programma esterno (AppDipendenti).
Restano anagrafica minima, cedolini, TFR.

**B — Fatture Estere**: da "PDF solo archiviato" a pipeline completa —
estrazione AI → fattura vera nello schema canonico → aggancio automatico
al matching PayPal/bonifico e all'alert scadenza già esistenti (nessun
motore di riconciliazione nuovo scritto) → aggancio fornitore anche su
P.IVA in formato UE non italiano → coda di verifica umana con rating di
affidabilità per fornitore (nuova collection `fatture_estere_verifiche`,
nuovo router `/api/fatture-estere`).

Verifica: 374 test passati (2 skipped), build frontend OK, nessuna
regressione sui 357 test pre-esistenti.

---

## 8. Indice documenti di audit del repo (`memoria/*.md`)

| File | Contenuto | Stato |
|---|---|---|
| `INDEX.md` | Scheda rapida: stack, collezioni canoniche, route principali, regole critiche | Vivo, da tenere aggiornato |
| `MAPPA_MODULI.md` | Narrativa architetturale per dominio, codice morto, sistemi paralleli | Aggiornato oggi |
| `MAPPA_ROUTER.md` | 108 prefissi, endpoint/prefisso, uso FE | **Rigenerato oggi** (script) |
| `MAPPA_ENDPOINT_COMPLETA.md` | 1059 endpoint atomici | **Rigenerato oggi** (script) |
| `MAPPA_COLLEZIONI.md` | 158 collezioni, usi, note | Aggiornato oggi (manuale, 2 righe) |
| `AUDIT_DEFINITIVO_SESSIONE_20260714.md` | Dettaglio tecnico sessione odierna (Dipendenti + Fatture Estere) | Nuovo oggi |
| `AUDIT_ATOMICO_APPLICAZIONE.md` | **Questo file** — indice/sintesi generale | Nuovo oggi |
| `AUDIT_AUTOMATISMI.md` | Automatismi dichiarati vs realmente schedulati | Aggiornato oggi |
| `AUDIT_STATIC_REPORT.md` | Report CI audit statico continuo | Generato da CI |
| `AUDIT_ESECUZIONE_DEFINITIVO.md` | Checklist §17 esecuzione (19 criteri) | 13/07 |
| `AUDIT_VIEWER_DOCUMENTI.md` | Censimento viewer documentale | 13/07 |
| `AUDIT_RICOGNIZIONE_2026-07-13.md` | Ricognizione pre-audit canonico | 13/07 |
| `AUDIT_PERFORMANCE_N1.md` | Query N+1 note | Storico |
| `AUDIT_PRIMITIVE_FRONTEND.md` | alert()/confirm() → toast/ConfirmDialog | Storico, completato |
| `MATRICE_FUNZIONALE_FINALE.md` | Matrice Frontend→Route→Endpoint→Engine→Collection (13 moduli) | 13/07 |
| `MAPPA_APPLICAZIONE.md` | Mappa applicativa (versione precedente/parallela a MAPPA_MODULI) | Da verificare se ancora attuale |
| `LOGICA_OPERATIVA.md` | Logica di dominio per singola funzionalità | Vivo |
| `SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` | Specifica vincolante utente motore fiscale/paghe | Vincolante, non modificare senza autorizzazione |
| `SPECIFICA_IVA.md` | Specifica IVA | Vincolante |
| `PIANO_CONTI_UFFICIALE_CERALDI.md` | Piano dei conti CEE ufficiale | Vincolante (regola CLAUDE.md) |
| `PIANO_MIGRAZIONE_COLLECTION.md` / `PIANO_CONSOLIDAMENTO_COLLECTION.md` | Piani di consolidamento collection (solo documento, non eseguiti) | Storico/pianificazione |
| `BACKLOG.md` | Backlog operativo | **SUPERATO (Aprile 2026) — vedi §6 sopra** |
| `PRD.md` | Product requirements | Storico |
| `REPORT_SESSIONE_RISTRUTTURAZIONE.md` | Report di una sessione di ristrutturazione precedente | Storico |
| `BUG_CORRETTI_2026-07.md` | Log bug fix di luglio | Storico |
| `ANALISI_MOTORI_CONTABILI.md` | Analisi motori contabili | Storico |
| `LOGICA_LIBRO_MASTRO.md` | Logica libro giornale/mastro | Vivo |
| `VERIFICA_CONFORMITA_REGISTRI.md` | Conformità art.2214-2220, DPR 600/73 | Storico |
| `FORNITORI_REGOLA_CANONICA.md` | Regola canonica fornitori | Vivo |
| `PROMPT_DEFINITIVO_CLAUDE_GESTIONALECLOUD.md` | Prompt/specifica originale di progetto | Storico, riferimento |

**Nota per chi legge in futuro**: quando la struttura cambia ancora,
rigenera SEMPRE `MAPPA_ROUTER.md`/`MAPPA_ENDPOINT_COMPLETA.md` con
`python scripts/genera_mappa.py` prima di fidarti di un numero scritto a
mano in un documento — è l'unica fonte che non può disallinearsi dal
codice reale, perché legge la route table a runtime.
