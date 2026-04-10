# Ceraldi ERP — PRD

## Problema originale
Applicazione ERP full-stack (React + FastAPI + MongoDB Atlas) — **solo contabilità**, gestione fornitori, HR, prima nota, fatture SDI. Design system rigido: solo CSS inline da `lib/utils.js`. **Vietato Tailwind e Shadcn.**

## Architettura
- **Backend**: FastAPI + Motor (MongoDB Atlas) — DB: `azienda_erp_db` (`Gestionale`)
- **Frontend**: React + Vite (porta 3000) — routing SPA con React Router v6
- **Server entry**: `/app/backend/server.py` (NON cancellare — è il punto di avvio Supervisor)
- **Design**: tutti gli stili inline, costanti in `/app/frontend/src/lib/utils.js`
- **Collection fornitori**: `fornitori` (168 doc) — `Collections.SUPPLIERS = "fornitori"` ← collection CANONICA
- **Collection suppliers**: 53 doc — NON usata dal modulo principale (residuo, ignorare)

```
/app
├── app/
│   ├── main.py
│   ├── routers/
│   │   ├── invoices/corrispettivi.py   # Corrispettivi telematici
│   │   ├── prima_nota_module/          # Prima Nota (Cassa + Banca)
│   │   ├── suppliers_module/           # Anagrafica Fornitori (usa collection "fornitori")
│   │   ├── fatture_module/             # Fatture Ricevute
│   │   ├── openapi_imprese.py          # Aggiornamento anagrafica da Camera di Commercio
│   │   └── schede_tecniche.py          # Ricerca PDF schede tecniche (LLM + web + XML)
├── frontend/src/
│   ├── main.jsx                        # React Router routes
│   ├── lib/utils.js                    # Design system (COLORS, STYLES, button, badge, ecc.)
│   ├── pages/
│   │   ├── Dashboard.jsx               # Dashboard principale
│   │   ├── hub/FattureHub.jsx          # Hub fatture
│   │   ├── Fornitori.jsx               # Anagrafica fornitori + OpenAPI + Schede Tecniche
│   │   ├── ArchivioFattureRicevute.jsx # Archivio fatture (no tab interni)
│   │   └── CicloPassivoAdmin.jsx       # File esistente ma senza route attiva (da implementare)
│   └── components/layout/
│       ├── TopNav.jsx                  # Navigazione principale
│       └── SecondaryTabs.jsx           # Tab secondari per sezione
```

## ⚠️ COSE RIMOSSE (da non reintrodurre)
- Modulo Cucina (router cucina/, RicettarioAdmin, FoodCostAdmin, CatalogoOrdini, ProdottiVendita)
- Widget Cucina in Dashboard
- FiscoHub, MotoreContabile, LiquidazioneIVA, RiconciliazioneF24, CodiciTributari, F24.jsx
- Route `/archivio-fatture-ricevute` (duplicato → redirect a `/fatture`)
- Tab "Escludi da Tracciabilità" dal form fornitori

## Completato

### Sprint 1-6 (sessioni precedenti)
- Pulizia 34 file stub dal backend
- Router cucina: `ricette.py`, `food_cost.py`, `prodotti_vendita.py`, `ordini_fornitori.py`
- Pagine admin: `RicettarioAdmin`, `FoodCostAdmin`, `CatalogoOrdini`, `ProdottiVendita`
- Tab "Bozze" in OrdiniFornitori
- Fix bug lettura PEC (INBOX.lette)
- Scheduler PEC ogni ora
- Rimozione duplicati UI (FiscoHub, MotoreContabile, tab secondari)
- Fix timezone in centri_costo.py e documenti.py
- Ottimizzazione import CSV estratto conto (~2s)
- Drawer cliccabile Piano dei Conti con endpoint movimenti semantici

### Sessione corrente (Aprile 2026)
- **Fix dati drawer Piano dei Conti**: logica semantica per conto (Cassa→prima_nota, Banca→prima_nota_banca, Debiti/Costi→fatture_passive, Ricavi→corrispettivi)
- **Fix reload tab hub**: pattern "mount-once, hide-with-CSS" su tutti gli hub (ContabilitaHub, CucinaHub, DocumentiHub, StrumentiHub, MagazzinoHub, FattureHub, PrimaNotaHub, AdminHub)
- **Pulizia navigazione**:
  - Eliminato `/archivio-fatture-ricevute` (duplicato di Fatture) — ora redirect a `/fatture`
  - Eliminato CucinaHub ovunque (frontend + backend) — non più pertinente per software contabile
  - Rinominato "Noleggio" → "Noleggio Auto" nel menu Altro per chiarezza
  - Rimosso tab "Archivio" secondario che puntava alla pagina duplicata

## Backlog Prioritizzato

### P0 — Nessuno al momento

### P1 — Alta priorità
- **Gestione Ciclo Passivo**: implementare `CicloPassivoAdmin.jsx` da `ISTRUZIONI_CICLO_PASSIVO.md`
- **Schede Tecniche via Gmail IMAP** (SBLOCCATO Apr 2026 — password funzionante): scansiona inbox Gmail per allegati PDF dai fornitori e li salva come schede tecniche

### P2 — Media priorità
- Verifica/fix `Portale.jsx` (potrebbe ancora usare Tailwind/Shadcn)
- Cleanup DB: rimuovere o consolidare collection `suppliers` (53 doc) duplicata con `fornitori`
- Scheduler aggiornamento automatico OpenAPI (1x/giorno aggiorna anagrafica fornitori)
- Dipendenti: consolidare `dipendenti` (34) + `employees` (31) in un'unica collection

### P3 — Bassa priorità
- Auth backend JWT con cookie HTTP-Only
- Notifiche push quando job schede tecniche completo

## Note Tecniche
- Backend collections reali: `prima_nota` (3), `prima_nota_banca` (21), `movimenti_bancari` (14834), `fatture_passive` (73), `corrispettivi` (25), `estratto_conto_movimenti` (25068)
- Filtro anno: `prima_nota` usa campo `data` (YYYY-MM-DD), `fatture_passive` usa campo `anno` (int), `corrispettivi` usa campo `anno` (int)
- Hub pattern: visitedTabs (Set) + display:none per tab inattivi

## API Principali
- `GET /api/piano-conti/conto/{codice}/movimenti?limit=40&anno=2026`
- `GET /api/cucina/ricette`, `POST /api/cucina/ricette`
- `GET /api/fatture-ricevute/archivio`
- `POST /api/email-download/pec/download-fatture-sync`
D

## Problema Originale
Applicazione ERP full-stack (React + FastAPI + MongoDB Atlas) per Ceraldi Caffè.
Aggiornamenti richiesti tramite file CERALDI_MASTER_ZIP.zip e ISTRUZIONI_CORRETTE_V2.md.

## Regole Fondamentali
- **Design system**: solo CSS inline con le costanti di `lib/utils.js`. Vietati Shadcn e Tailwind per le pagine gestionale.
- **Lingua**: rispondere SEMPRE in italiano.
- **DB**: MongoDB Atlas (`azienda_erp_db`) via `MONGO_URL` dal backend `.env`.
- **Backend script**: NON eliminare `/app/backend/server.py` (punto di avvio Supervisor).

## Architettura
```
/app
├── app/
│   ├── main.py
│   ├── routers/
│   │   ├── cucina/                     # Ricette, FoodCost, ProdottiVendita, OrdiniFornitori
│   │   ├── invoices/corrispettivi.py   # Corrispettivi telematici
│   │   ├── prima_nota_module/          # Prima Nota (Cassa + Banca)
│   │   ├── suppliers_module/           # Anagrafica Fornitori
│   │   └── fatture_module/             # Fatture Ricevute
├── frontend/src/
│   ├── main.jsx                        # React Router routes
│   ├── lib/utils.js                    # Design system (COLORS, STYLES, button, badge, ecc.)
│   ├── pages/
│   │   ├── Dashboard.jsx               # Dashboard principale (no widget cucina)
│   │   ├── hub/FattureHub.jsx          # Hub fatture (ArchivioContent | CorrispettiviContent)
│   │   ├── Corrispettivi.jsx           # Pagina corrispettivi (stato vuoto se no dati)
│   │   ├── ArchivioFattureRicevute.jsx # Archivio fatture — singola vista pulita (no tab interni)
│   │   ├── CicloPassivoAdmin.jsx       # File rimasto ma SENZA route attiva
│   │   ├── RicettarioAdmin.jsx         # Gestione ricette cucina
│   │   ├── FoodCostAdmin.jsx           # Gestione food cost
│   │   ├── CatalogoOrdini.jsx          # Catalogo ordini cucina
│   │   └── ProdottiVendita.jsx         # Prodotti vendita
│   └── components/layout/
│       ├── TopNav.jsx                  # Navigazione principale
│       └── SecondaryTabs.jsx           # Tab secondari per sezione
```

## Cosa è stato implementato

### Sessioni precedenti (completato)
- Eliminazione 34 file stub inutili dal backend
- Creazione router cucina: ricette.py, food_cost.py, prodotti_vendita.py, ordini_fornitori.py
- Creazione UI: RicettarioAdmin, FoodCostAdmin, CatalogoOrdini, ProdottiVendita
- Integrazione tab "Bozze" in OrdiniFornitori
- Fix Prima Nota: errore 422, deduplicazione Banca, query Cassa
- Fix Anagrafica Fornitori: piva vs partita_iva, card "Senza nome", filtro fatture
- Popolamento automatico form Anagrafica da XML
- Rimozione sezione Riconciliazione Unificata, /fatture/import, /previsioni-acquisti
- Deep Linking via useHashState.js (hook) + CopyLinkButton (componente)
- Fix errore 409 duplicati corrispettivi COR10
- Verifica credenziali IMAP Gmail e PEC

### Sessione corrente - Fix OpenAPI (Aprile 2026)
- **Token OpenAPI aggiornato**: `69d86ebe314b08523b0dceda` — ora funzionante (era 401)
- **Fix router openapi_imprese.py**:
  - Corretto db.fornitori → db["suppliers"] in tutti gli endpoint
  - Endpoint `fornitori-da-aggiornare`: ora filtra P.IVA 11 cifre numeriche, deduplicazione, legge nome da campo corretto
  - Endpoint `aggiorna-bulk`: rimosso upsert, aggiorna solo esistenti, mappa campo `nome`
  - Endpoint `aggiorna-fornitore`: usa collection `suppliers` e mappa `nome` + `ragione_sociale`
- **Risultato**: 45 fornitori ora visibili (vs 21 prima), bulk aggiornamento recupera 25 fornitori nascosti

### Sessione corrente - Fix Collection + UI Fornitori (Aprile 2026)
- **Bug critico risolto**: `Collections.SUPPLIERS = "fornitori"` — scoperto che il modulo usa `db["fornitori"]` (168 doc) non `db["suppliers"]` (53 doc inutilizzati). Corretti `openapi_imprese.py`, `schede_tecniche.py`, `manutenzione.py`
- **Comune popolato**: lanciato bulk OpenAPI update sulla collection corretta → 44/45 fornitori ora hanno comune/indirizzo/provincia/CAP/PEC da Camera di Commercio
- **UI Fornitori**: rimosso "Escludi da Tracciabilità" da form e card; "Dati Incompleti" ora conta fornitori senza comune (3) invece di senza email (45)

### Sessione corrente - Dati Fornitore da XML + Schede Tecniche + Formati IT (Aprile 2026)
- **Auto-populate da XML**: nuovo endpoint `POST /api/schede-tecniche/popola-fornitore/{id}` che estrae CedentePrestatore (telefono, email, indirizzo, comune, prov) dagli XML fatture
- **Alert dati mancanti**: banner giallo nel modal modifica fornitore quando mancano email/telefono, con bottone "Cerca in fatture"
- **Schede Tecniche - lista completa**: da 3 → 24 prodotti visibili (tutti gli XML, senza limite); stato "non_cercato" (🔍) per quelli non ancora cercati
- **Formato italiano**: date in gg/mm/aaaa e valori in formato italiano in Fornitori.jsx, GestionePagoPA, DocumentiDaRivedere, CorrezioneAI, Portale.jsx

### Sessione corrente - Gmail IMAP + Scan Email Schede Tecniche (Aprile 2026)
- **Gmail IMAP sbloccato**: password `nugg fttp swvx djqd` funzionante, 2955 messaggi accessibili
- **Scan email per schede tecniche**: job `_esegui_ricerca` ora cerca anche negli allegati Gmail (Prova 3) prima di segnare "non trovato"
- **PRD aggiornato**: rimossi riferimenti al modulo Cucina, corretti nomi collection, backlog aggiornato

### Sessione corrente (completato)
- **Corrispettivi**: rimosso stub vuoto dal DB → pagina mostra correttamente stato vuoto
- **Widget Cucina Dashboard**: RIMOSSO
- **SecondaryTabs**: rimosso tab "Import XML" dalla sezione Fatture
- **CicloPassivoHub.jsx**: rimosso redirect, route /ciclo-passivo → redirect a /fatture
- **Route /ciclo-passivo/import**: ELIMINATA da main.jsx
- **ArchivioFattureRicevute.jsx**: eliminati tab interni
- **BUG FIX CRITICO PEC**: `aruba_pec_downloader.py` ora cerca in INBOX + INBOX.lette (137 email trovate, 59 fatture importate)
- **BUG FIX**: `centri_costo.py` — aggiunto `timezone` all'import datetime (NameError risolto)
- **Deep Linking esteso**: useHashState + CopyLinkButton aggiunti in PrimaNota, F24, Fornitori
- **SCHEDULER PEC**: task orario `pec_hourly_download_task` aggiunto allo scheduler (APScheduler)
- **FIX sync PEC timeout**: endpoint background corretto (`await` rimosso da `Database.get_db()`). GestioneEmailMittenti e CicloPassivoAdmin ora usano background endpoint (risposta in <0.3s invece di timeout a 33s)
- **Scheduler riabilitato** in `main.py`: PEC ogni ora, Gmail ogni 10min, Verbali ogni ora, F24 alle 8/14
- **RIMOSSA pagina `/fisco`** e hub FiscoHub.jsx — eliminati 6 file: FiscoHub, MotoreContabile, LiquidazioneIVA, RiconciliazioneF24, CodiciTributari, F24.jsx
- **RIMOSSO tab `/contabilita/motore`** (MotoreContabile) dalla ContabilitaHub — duplicato di BilancioVerifica
- Voce "Fisco" rimossa dal TopNav, SecondaryTabs, App.jsx
- **FIX CRITICO UnboundLocalError `timezone`**: `from datetime import timezone` era DENTRO la funzione `upload_documento_automatico` (documenti.py:2602) — causava errore su ogni upload estratto conto CSV
- **Import estratto conto ottimizzato**: da ~3400 query MongoDB singole (timeout 60s) a 1 query bulk + insert_many (2.5s). Import diretto dall'upload-auto senza step intermedio.

## Backlog / Task futuri
- **P3**: Auth backend con Cookies HTTP-Only

## Key API Endpoints
- `GET /api/corrispettivi?anno=YYYY` — lista corrispettivi
- `GET /api/fatture-ricevute/archivio` — archivio fatture ricevute
- `GET /api/fatture-ricevute/statistiche` — stats fatture
- `POST /api/fatture-ricevute/paga-manuale` — registra pagamento
- `POST /api/prima-nota/cassa` / `/banca` — movimenti prima nota
- `GET /api/openapi-imprese/status` — verifica token OpenAPI
- `POST /api/openapi-imprese/aggiorna-bulk` — aggiorna tutti i fornitori da Camera di Commercio
- `POST /api/schede-tecniche/cerca/{fornitore_id}` — avvia job ricerca PDF schede tecniche
- `POST /api/schede-tecniche/popola-fornitore/{id}` — popola dati fornitore dagli XML fatture
- `GET /api/schede-tecniche/fornitore/{id}` — tutti i prodotti del fornitore (DB + XML non cercati)
