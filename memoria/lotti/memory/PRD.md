# CeraldiApp - PRD & Stato

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Original Problem Statement
Gestionale full-stack (FastAPI + React + MongoDB Atlas) per Ceraldi Group: HACCP, contabilità, inventario bar/pasticceria, gestione ordini fornitori. Database "Gestionale" su Atlas.

## Architettura
- **Backend**: FastAPI, motor (MongoDB async), porta 8001
- **Frontend**: React (CRA), Tailwind, sessionStorage per kiosk tablet
- **DB**: MongoDB Atlas, DB_NAME="Gestionale"
- **Routes critiche**:
  - `/api/fornitori/*` (anagrafica, schede ricevimento, qualifica)
  - `/api/tablet-operatori/login` (PIN bcrypt)
  - `/api/fatture/*`
  - `/api/prodotti-master/*` (inventario unificato)
  - `/api/temperature_*` (HACCP)
  - `/api/lotti/*`, `/api/dashboard-economica/*`, `/api/produzione-consigliata/*`,
    `/api/ricerca-globale` (tracciabilità lotti, vedi sezione dedicata sotto)

## Tracciabilità lotti — 7 macro-funzionalità (Luglio 2026)
Richiesta di Enzo: migliorare la tracciabilità lotti senza collegare gli
scontrini di vendita (commercio al banco). Realizzata in 7 tranche
incrementali (0-6), ciascuna con PR/CI/merge separati — dettaglio
completo di ogni tranche in `memory/STATO.md` (04/07/2026), mappa
DB/endpoint in `memory/claude.md` v67. Riepilogo:

1. **Fondamenta dati** (Tranche 0): collection `movimenti_lotto` (audit
   trail: chi/quando/da dove/a dove/quanto/perché), campo `lotti.posizione`
   strutturato (parallelo a `frigo_numero`, non sostitutivo), semaforo
   scadenza a 4 livelli e valore economico calcolati (non persistiti).
2. **Scadenza intelligente + Gemello digitale del lotto** (Tranche 1):
   `GET /lotti/cosa-usare-oggi` (ordinato per urgenza/valore), scheda
   lotto aggregata con cronologia e azioni (sposta/congela/recupera/
   banco/smaltisci).
3. **Intelligenza operativa frigoriferi** (Tranche 2): spostamento
   massivo tracciato quando un'attrezzatura va in anomalia
   (`POST /anomalie/{id}/sposta-lotti-massivo`).
4. **Cronologia completa del lotto** (Tranche 3): timeline arricchita con
   anomalie collegate, rientro invenduto, abbattimento.
5. **Dashboard economica** (Tranche 4): valore lotti attivi/in scadenza/
   smaltiti, costo spreco, margine per prodotto/reparto, variazione
   prezzi materie prime, fornitori per incidenza spesa.
6. **Produzione consigliata** (Tranche 5): motore di suggerimento
   (storico produzione per giorno settimana, invenduto, festività,
   trend incassi) con decisioni persistite (accetta/modifica/ignora).
7. **Miglioramenti UI trasversali** (Tranche 6): ricerca globale
   multi-collezione, mappa visiva tracciabilità, pannello "Cosa devo fare
   oggi" in Dashboard.

**Seguito**: registro richiami eseguiti (`richiami_eseguiti`,
`POST /lotti/recall/esegui`) — distingue una ricerca on-demand
(`/lotti/recall/cerca`, preesistente) dalla registrazione FORMALE che un
richiamo è stato avviato, con evento collegato nella cronologia del lotto.

**Limiti onesti noti** (non implementati, dati che non esistono):
stampe etichetta non loggate (apertura finestra ≠ stampa reale); verifica
live non eseguibile dall'ambiente sandbox usato per costruire queste
tranche (limite di rete, non un bug applicativo).

## Bugfix completati (Apr 2026)
- **2026-04-30 (iter78)** — Cleanup finale ✅:
  - **Dedup `prodotti_master` fixato**: rebuild() aveva race condition (drop+insert non atomico) + indice unique mai creato per presenza duplicati. Root cause: 3 rebuild concurrent avevano triplicato i documenti (8077 righe con solo 2859 key uniche). **Fix**: riscritto `rebuild()` con `bulk_write` + `UpdateOne(upsert=True)` + cleanup stale docs. Indice unique su `key` creato. Ora rebuild idempotente e concurrent-safe.
  - **Risultato dedup**: 8077 → **2863** prodotti (2515 con prezzo). Test idempotenza: 2 rebuild consecutivi → stesso count.
  - **8 gruppi fornitori duplicati uniti automaticamente** (Naturissime, Dolciaria Acquaviva, Olive Miraglia, FLA, DRINK UP, EUREKA, GIEMME, INFOCERT) con master = versione con più fatture.
  - **Bug laterale fixato in `fornitori_dedup.py/merge`**: `DuplicateKeyError` su indice unique `partita_iva`. Fix: eliminare PRIMA il record duplicato poi aggiornare il master + try/except con fallback su campi safe.
  - **Duplicati residui: 0** ✅. 259 fornitori totali, 87 attivi.

- **2026-04-30 (iter77)** — Refactoring `fornitori.py` ✅:
  - File principale ridotto da **1296 → 897 righe** (-31%)
  - Creati 2 nuovi moduli:
    - `/app/backend/routers/fornitori_schede.py` (241 righe): Registro qualificati + Schede ricevimento + note
    - `/app/backend/routers/fornitori_qualifica.py` (178 righe): qualifica HACCP (in-attesa/approva/batch/auto/rinnovo/scadenze)
  - Tutti e 7 gli endpoint testati OK (200). Bug marginale fixato: `KeyError: 'nome'` in `registro-qualificati` (alcuni record fornitori senza campo nome). Ora filtrati via `.get()`.
  - Il file `fornitori.py` ora contiene solo: CRUD fornitori, approva/escludi, note, auto-classifica HORECA, anagrafica dettaglio (get+put).

- **2026-04-30 (iter76)** — Arricchimento fatture da Gestionale 🎯:
  - **Scoperta chiave**: il Gestionale `impresasemplice.online` in realtà **aveva già le righe prodotto** in `Gestionale.invoices.linee` (campo) per 1621/1697 fatture — ma il sync di CeraldiApp leggeva il campo sbagliato (`prodotti` invece di `linee`).
  - **Fix sync** in `/app/backend/routers/pec_import.py`: il sync ora mappa `linee[]` → `prodotti[]` con filtro automatico per righe meta ("Rif.scontrino...", "Totale...", ecc.).
  - **Nuovo endpoint `POST /api/sync-gestionale/arricchisci-prodotti`**: riarricchisce le fatture già importate senza dover rifare il sync. Match per (numero_fattura + P.IVA). Rilancia automaticamente: rebuild lotti_fornitori, importa sconti, rebuild prodotti_master.
  - **Bottone UI "Arricchisci da Gestionale"** in `ImportaFattureView.jsx` (tab Importa).
  - **Risultati eseguiti**:
    - 179 fatture arricchite (+1755 prodotti reali)
    - `lotti_fornitori`: 348 → **16893** (x48!) + 312 spese accessorie correttamente saltate
    - `prodotti_master`: 726 → **8077** (7063 con prezzo)
    - `sconti_merce`: 238 nuovi omaggi/sconti rilevati
    - BIG FOOD SRL visibile: prima 3 prodotti → ora **375** prodotti reali.

- **2026-04-30 (iter75)** — Task 2 completato (A + B):
  - **A. Rebuild automatico `prodotti_master`**: hook in `/app/backend/routers/pec_import.py` che ricostruisce la collezione unificata dopo ogni `gestionale_sync` orario. Così `OrdiniSmartView` e il nuovo Catalogo mostrano sempre dati freschi.
  - **B. Nuovo tab "Catalogo Prodotti Unificato"**: `/app/frontend/src/components/haccp/CatalogoUnificatoView.jsx`. Vista lettura-only che aggrega le 4+ fonti (fattura 244, acquaviva 376, prodotti_vendita 422, magazzino_bar 32 = **726 prodotti totali**, 484 con prezzo). Features: ricerca real-time, filtri per fonte/fornitore/con-prezzo, badge fonti colorati, modale dettaglio con storico prezzi e alias, export CSV, bottone rebuild manuale. Collegato nel dropdown "Altro" navbar.
  - Le 5 viste esistenti (MagazzinoBar, Ingredienti, MateriePrime, PrezziProdotti, ProdottiVendita) NON sono state toccate — continuano a gestire i flussi specifici (scadenze bar, prezzi singoli Acquaviva, ecc). Il nuovo Catalogo è complementare, non sostitutivo.

- **2026-04-30 (iter74)**: 
  - **Pagina Materie/Da-Fatture mostrava "Spese Trasporto" e "Spese Cancelleria"** come materie prime. Fix: aggiunto filtro `_is_spesa_accessoria()` in `/app/backend/routers/materie_prime.py` con pattern regex per escludere voci non-alimentari (spese, trasporti, bolli, imballaggi, cancelleria, abbuoni, arrotondamenti, interessi).
  - **Materie Prime: solo 1 parte dei prodotti visualizzati**. Root cause: `lotti_fornitori` conteneva solo le fatture processate via pec_import XML (84 su 1105 hanno prodotti dettagliati — le altre 1021 dal sync Gestionale sono solo header senza righe prodotto). Fix: endpoint `POST /api/materie-prime/rebuild-lotti-fornitori` che ricostruisce da tutte le fatture disponibili, ed è chiamato automaticamente dopo ogni `gestionale_sync`. Ora `lotti_fornitori` = 348 righe (tutte quelle disponibili). ⚠️ IMPORTANTE: per vedere più prodotti è necessario che `impresasemplice.online` parsifichi gli XML e popoli il campo `prodotti` di `Gestionale.invoices` (responsabilità Gestionale esterno).
  - **#sconti_merce non si aggiorna al ricevimento fatture**. Fix: hook `importa_sconti_da_fatture()` aggiunto in `pec_import.py` dopo ogni sync Gestionale. Nuovi sconti/omaggi vengono ora rilevati automaticamente.
  - **Auto-merge fornitori normalizzati**: nuovo endpoint `POST /api/fornitori/auto-merge-normalizzati` che unisce i duplicati con stesso P.IVA e nomi equivalenti (case/punteggiatura/SRL vs S.R.L.). 4 gruppi uniti automaticamente (DRINK UP, GIEMME, ALFA SERVICE, COFRUT).

- **2026-04-30 (iter73)**: 
  - **Scheduler HACCP non eseguiva più il job giornaliero** (ultima esecuzione 15/04). Root cause: APScheduler AsyncIOScheduler è in-memory → riavvii del backend (hot reload, deploy) perdono i trigger fissi (07:00, 08:00). Fix: aggiunto `_catchup_jobs_mancanti()` in `scheduler.py` che all'avvio controlla se i job critici di oggi (haccp_daily, check_scorta_minima, pipeline_aggiornamento) sono stati eseguiti. Se l'orario è passato e non c'è log success di oggi → esegue subito. Validato: 30/04 HACCP generato con 12 frigo + 20 freezer + sanificazione.
  - **Navbar con troppi tab (17) → scroll orizzontale obbligato**. Fix: creato `AltroDropdown.jsx`, spostato 8 tab secondari (Sconti, Backoffice, Colazione, Storico, Allergeni, Audit, Analytics, Backup) in dropdown dedicato. Navbar ora mostra solo 8 tab primari + "Altro".
  - **Deploy: env non tracciati in git**. Fix: riscritto `.gitignore` (da 108 righe duplicate a 41 righe pulite) con eccezioni `!backend/.env !frontend/.env`. Ora i `.env` app sono tracciati per deploy.
  - **Deploy: System Keys Render sbagliate**. Confermato all'utente: MONGO_URL/DB_NAME puntavano al DB managed vuoto invece del cluster Atlas reale. Risolto lato dashboard Render.
- **2026-04-29 (iter72)**: Risolti 3 bug critici (match anagrafica fornitore, 356 fatture duplicate, PIN tablet).
  1. **Modale Scheda Fornitore con numeri fattura incoerenti** — root cause: regex permissivo `nome_parole|altra_parola` matchava fornitori diversi (es. "GIUSEPPE" matchava sia GARGIULO GIUSEPPE che ELECTRONICS' HOUSE GIUSEPPE). **Fix**: match esatto `^...$` con fallback su P.IVA + dedup su (numero, data) (`/app/backend/routers/fornitori.py` linee 683-712).
  2. **12 fatture "Fornitore Sconosciuto"** (P.IVA 05867230657) — root cause: doppioni storici da `gestionale_sync` (stesse fatture salvate sia col nome corretto sia come "Sconosciuto"). **Fix**: eliminati 356 fatture duplicate totali (1460→1104) via dedup `(numero_fattura, data_fattura, fornitore)`. Aggiunto fallback P.IVA preventivo in `/app/backend/routers/pec_import.py` linee 163-185.
  3. **PIN Tablet Pasticceria 5678 non sblocca** — verificato funzionante via screenshot test: PIN sblocca correttamente. Era cache browser locale dell'utente.
  4. Consolidato GARGIULO GIUSEPPE duplicato (record fornitori unito).
- **Test**: 14/14 backend test passati (vedi `/app/test_reports/iteration_72.json`)

## Bugfix completati precedentemente
- Sostituito DB locale con MongoDB Atlas remoto
- Fix temperature HACCP "chiusura_stagionale" (40k record corrotti puliti)
- Fix duplicati fornitori (logica merge in GET)
- Rimosso auto-popolamento freezers vuoti (timeout)
- Sincronizzati `pezzi_ricetta_base` e `porzioni` nelle ricette
- Creata collezione `prodotti_master` (centralizzazione inventario)
- Azzerati 225 prezzi inventati Acquaviva
- Vista unificata `OrdiniSmartView.jsx` (Listino + Comparatore + Carrello)
- Pulizia 246 prodotti orfani da `listino_prodotti`

## Roadmap (P1 - Backlog)
- **Refactoring frontend inventario**: 5 viste magazzino (`MagazzinoBarView`, `IngredientiView`, ecc.) leggono ancora dalle vecchie singole collezioni → migrare a `prodotti_master`.
- **Deduplica fornitori per P.IVA**: ~20 P.IVA hanno 2 record fornitori (es. "Drink Up S.r.l." vs "DRINK UP SRL"). Da unificare con UI di merge manuale.
- **Refactoring server.py / fornitori.py**: file molto lunghi (>1000 righe). Splittare in submodules.

## Future / P2
- Indice MongoDB case-insensitive su `fatture.fornitore` per velocizzare anagrafica
- Endpoint segregati per anagrafica/KPI/omaggi (alleggerire response)
- Test pytest in `/app/backend/tests` (regressioni)

## Credenziali test
Vedi `/app/memory/test_credentials.md`
