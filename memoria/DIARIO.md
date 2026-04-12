# Diario di Sviluppo — Ceraldi ERP
> Storico delle sessioni di sviluppo, bug risolti, decisioni prese

---

## CHAT 8 — Fix reload continuo + responsive completo (10 Aprile 2026)

### Root cause del reload continuo

`isMobile` usato dentro sub-componenti definiti FUORI dall'`export default`:
- `TabAnagrafica`, `TabCedolini`, `TabMovimenti`, `TabGiustificativi` in `HRDipendenti.jsx`
- `PrimaNotaDesktop`, `EditMovimentoModal` in `PrimaNota.jsx`
- `SupplierModal` in `Fornitori.jsx`
- `DocumentRow` in `DocumentiDaRivedere.jsx`

Questi sub-componenti usavano `isMobile` senza avere il proprio `useIsMobile()`.
Ogni mount lanciava `ReferenceError: isMobile is not defined` → ErrorBoundary → loop reload.

**Fix**: `useIsMobile()` aggiunto in ogni sub-componente + reset corretto al cambio dipendente (`key` + `visitedTabs` reset).

### Altri bug risolti in questa chat

**Bug frontend:**
- `LearningMachine` usata nelle route ma non importata con `lazy()` → `ReferenceError` → loop reload
  - Fix: aggiunta riga `const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"))` in `main.jsx`

**Bug backend:**
- `settings_router` registrato due volte in `main.py` → rimosso il duplicato
- Router Tracciabilità registrati due volte (blocco vecchio + nuovo `_TR_ROUTERS`) → rimosso blocco vecchio

### Responsive completato

Pagine adattate per mobile:
- `ArchivioFattureRicevute.jsx`: vista mobile a card (fornitore, data, numero, totale, bottoni)
- `Fornitori.jsx`: grid da `minmax(320px,1fr)` a `1fr` su mobile (1 colonna)
- Rimossi `minWidth` fissi (700/800/900/1000/1400px) da tutte le tabelle
- `styles.css`: CSS globale mobile `@media (max-width: 768px)` aggiunto:
  - Tabelle scrollabili (`min-width: 480px`)
  - Padding celle ridotto
  - Grid forzate a 1 colonna

### Stato finale verificato (Aprile 2026)
- HR funziona: dipendenti caricano con tutti i tab
- 5 tab (Anagrafica, Contratti, Cedolini, Movimenti, Giustificativi) visibili
- Zero crash, zero reload
- Build OK, backend healthy

---

## CHAT 7 — HR Redesign + PEC fix (Aprile 2026)

### Redesign HR completo
- **Eliminata**: `GestioneDipendentiUnificata.jsx` (2.183 righe monolitiche)
- **Create**: 4 pagine separate in `pages/hr/`: `HRDipendenti`, `HRCedolini`, `HRPresenze`, `HRTFR`
- Route: `/dipendenti`, `/dipendenti/cedolini`, `/dipendenti/presenze`, `/dipendenti/tfr`

### Fix PEC Aruba (bug critico)
- `aruba_pec_downloader.py` ora cerca in `INBOX` + `INBOX.lette` (prima solo `INBOX`)
- Risultato: 137 email trovate, 59 fatture importate (vs 0 prima)

### Fix tecnici
- `centri_costo.py`: aggiunto `timezone` all'import `datetime` (NameError risolto)
- `documenti.py` riga 2602: `from datetime import timezone` era DENTRO la funzione → `UnboundLocalError` su ogni upload CSV
- Import CSV estratto conto: da ~3.400 query singole MongoDB (~60s) a 1 query bulk + `insert_many` (~2.5s)

### Scheduler riabilitato
- PEC ogni ora (`pec_hourly_download_task`)
- Gmail ogni 50 minuti
- Verbali noleggio ogni ora
- F24 alle 8:00 e 14:00

### Pulizia navigazione
- Eliminato `/archivio-fatture-ricevute` (duplicato) → redirect a `/fatture`
- Eliminato `CucinaHub` ovunque (non pertinente per software contabile)
- Rinominato "Noleggio" → "Noleggio Auto"
- Rimosso tab "Archivio" secondario

---

## CHAT 6 — OpenAPI + Fornitori + Gmail (Aprile 2026)

### Fix OpenAPI Camera di Commercio
- Token aggiornato: `69d86ebe314b08523b0dceda` → ora funzionante (era 401)
- `openapi_imprese.py`: corretto `db.fornitori` → `db["suppliers"]`
- Endpoint `fornitori-da-aggiornare`: ora filtra P.IVA 11 cifre, deduplicazione corretta
- Risultato: 45 fornitori visibili (vs 21 prima), bulk aggiornamento funzionante

### Fix collection fornitori (bug critico)
- Scoperto: `Collections.SUPPLIERS = "fornitori"` ma il modulo usava `db["suppliers"]`
- Corretti: `openapi_imprese.py`, `schede_tecniche.py`, `manutenzione.py`
- 44/45 fornitori ora hanno comune/indirizzo/provincia/CAP/PEC da Camera di Commercio

### Gmail IMAP sbloccato
- App Password Google: `nugg fttp swvx djqd` — funzionante
- 2.955 messaggi accessibili
- Job schede tecniche ora cerca in allegati Gmail (Prova 3 del processo di ricerca)

### Auto-populate fornitore da XML
- Nuovo endpoint `POST /api/schede-tecniche/popola-fornitore/{id}`
- Estrae CedentePrestatore (telefono, email, indirizzo) dagli XML fatture
- Alert giallo in modal fornitore quando mancano dati, con bottone "Cerca in fatture"

---

## CHAT 5 — Drawer Piano dei Conti + Hub Pattern (Aprile 2026)

### Drawer Piano dei Conti (completato)
- Logica semantica per conto:
  - Cassa → `prima_nota_cassa`
  - Banca → `prima_nota_banca`
  - Debiti/Costi → `fatture_passive`
  - Ricavi → `corrispettivi`
- Endpoint: `GET /api/piano-conti/conto/{codice}/movimenti?limit=40&anno=2026`

### Hub Pattern introdotto
- Problema: ogni cambio tab rimontava il componente → reload dati inutili
- Soluzione: `visitedTabs` (Set) + `display:none` per tab non attivi
- Applicato a: ContabilitaHub, CucinaHub, DocumentiHub, StrumentiHub, MagazzinoHub, FattureHub, PrimaNotaHub, AdminHub

### Deep Linking
- `useHashState.js` hook: sincronizza tab attivo con hash URL
- `CopyLinkButton` componente: copia link diretto al tab corrente
- Aggiunto in: PrimaNota, F24, Fornitori

---

## CHAT 1-4 — Sprint iniziali (sessioni precedenti)

### Completato nelle prime sessioni
- Pulizia 34 file stub dal backend
- Router cucina: `ricette.py`, `food_cost.py`, `prodotti_vendita.py`, `ordini_fornitori.py` *(poi rimossi)*
- Fix bug lettura PEC (INBOX.lette)
- Scheduler PEC ogni ora
- Rimozione duplicati UI (FiscoHub, MotoreContabile, tab secondari)
- Fix timezone in `centri_costo.py` e `documenti.py`
- Fix errore 409 duplicati corrispettivi
- Verifica credenziali IMAP Gmail e PEC
- Import CSV estratto conto ottimizzato (~2.5s)
- FiscoHub, MotoreContabile, LiquidazioneIVA, RiconciliazioneF24 → eliminati (6 file)

---

## TODO — Chat 9 (prossima sessione)

- Testare pagine su mobile (verifica responsive completo)
- PIN dipendenti per Tablet Cucina → ceraldiapp.it
- Verificare riconciliazione cedolini con estratto conto
- Schede tecniche: completare scan Gmail automatico
- Considerare consolidamento `suppliers` + `fornitori`

---

*Aggiornato: Aprile 2026*
