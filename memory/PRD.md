# Ceraldi ERP - Product Requirements Document

## Descrizione
Applicazione ERP full-stack italiana (React + FastAPI + MongoDB) per gestione aziendale: fatturazione, contabilità, gestione fiscale, cespiti, e reportistica finanziaria.

## Architettura
- **Frontend**: React (Vite), porta 3000
- **Backend**: FastAPI, porta 8001
- **Database**: MongoDB Atlas (azienda_erp_db)
- **Auth**: Disabilitata

## Moduli principali
1. Dashboard (fatture, bilancio, volume affari, imposte)
2. Fatture Ricevute (gestione fatture)
3. Cespiti (gestione beni ammortizzabili con scan XML automatico)
4. Piano dei Conti (con saldi calcolati in tempo reale)
5. Bilancio (stato patrimoniale)
6. Prima Nota (cassa e banca)
7. F24 (pagamenti fiscali)
8. Corrispettivi (incassi giornalieri)
9. Magazzino (inventario)
10. Dipendenti/Presenze (HR, presenze, cedolini, ferie)
11. Fisco/IVA (calcoli fiscali)

## Logica aziendale chiave
- **Volume Affari** = SOLO corrispettivi (le fatture emesse sono GIA incluse nei corrispettivi come scontrini)
- **Fatture ricevute** (collezione invoices) = COSTI/ACQUISTI, NON ricavi
- **Cespiti** estratti automaticamente da dettaglio_righe_fatture con classificazione keyword

## REGOLA FONDAMENTALE — Anno Globale (AnnoContext)
> **OGNI saldo, totale, lista o calcolo nell'app DEVE filtrare per l'anno (e opzionalmente il mese) impostato nel selettore globale `AnnoSelector`.**
>
> - Il valore dell'anno globale è fornito da `useAnnoGlobale()` (hook React) → variabile `anno`
> - Il backend riceve l'anno come query param `?anno=XXXX` (e `?mese=XX` quando applicabile)
> - **NESSUN endpoint deve restituire dati di tutti gli anni mischiati** a meno che non sia esplicitamente richiesto (es. export cumulativo)
> - Esempi corretti:
>   - `GET /api/prima-nota/cassa?anno=2025` → solo movimenti 2025
>   - `GET /api/finanziaria/summary?anno=2025` → saldo calcolato solo sui movimenti 2025
>   - `GET /api/cedolini?anno=2025&mese=3` → solo cedolini marzo 2025
> - **Quando si crea un nuovo endpoint** che restituisce saldi o liste, aggiungere SEMPRE il filtro `anno` (e `mese` se la granularità lo richiede)
> - **Quando si crea un nuovo componente React** che mostra dati finanziari, passare SEMPRE `anno` dall'AnnoContext all'API call
>
> **BUG NOTO FIXATO (Apr 2026):** Prima Nota Banca → il saldo progressivo nella tabella partiva sempre da 0 invece di usare il riporto dall'anno precedente. Fixato passando `saldoPrecedente={bancaData.saldo_precedente || 0}` al componente `MovementsTable`.

## Sessione 1 (Precedente)
- Fix contabilità critica (Bilancio, Veicoli)
- Correzione sorgente dati F24 (quietanze_f24)
- Arricchimento dati fatture (imponibile, IVA)
- Fix matricola corrispettivi
- Ristrutturazione modulo Magazzino + prodotti manutenzione
- Rimozione auto-refresh (Dashboard, Documenti)
- Miglioramenti vista fattura, pulsante "Segna come Pagata"
- Rimozione calendario POS, fix crash pagine

## Sessione 2 (25 Feb 2026)
- Fix intestazioni tabella fatture (testo scuro su sfondo chiaro)
- Auto-scan cespiti: POST /api/cespiti/scan-fatture (21 beni, €60.124,58)
- Volume Affari CORRETTO: fatturato = solo corrispettivi (€31.395,51)
- Bilancio Istantaneo: query fatture con campo anno, conteggio corrispettivi corretto
- Contabilità Hub: Piano dei Conti con saldi reali
- Prima Nota Cassa: fix mismatch tipo data (datetime vs string)
- Dipendenti/Presenze: 34 dipendenti reali dalla collezione dipendenti

## Sessione 3 (25 Feb 2026 - Corrente)
- **Route /attendance → /presenze**: Rinominata URL, aggiornati tutti i link
- **Dipendente duplicato unificato**: Orosco/Orozco Posligua → unico record con CF
- **Toggle "In carico"**: Aggiunto pulsante cliccabile nella tabella Anagrafica
- **Cedolini con dati reali**: PagheHub ora carica da /api/cedolini (14 buste per 2026)
- **Ferie - Elimina e Modifica**: Aggiunti pulsanti "Elimina richiesta" e "Modifica periodo"
- **Auto-refresh eliminato completamente**: useData.js refetchInterval, NotificheScadenze
- **Pulizia componenti**: Rimossi 20 file inutilizzati
- **Fix db["employees"] → db["dipendenti"]**: Corretto in tutti i router

## Endpoint API chiave
- GET /api/gestione-riservata/volume-affari-reale?anno=2026
- GET /api/dashboard/bilancio-istantaneo?anno=2026
- GET /api/prima-nota/cassa?anno=2026 → 5 movimenti
- GET /api/employees?limit=200 → 34 dipendenti reali
- GET /api/cedolini?anno=2026 → 14 cedolini
- GET /api/cespiti/?attivi=true → 21 cespiti
- POST /api/cespiti/scan-fatture → scan fatture XML
- DELETE /api/giustificativi/saldi-finali/{id}?anno=2026
- PUT /api/giustificativi/saldi-finali/{id}/periodo

## Collezioni DB chiave
- invoices: 74 (fatture RICEVUTE = COSTI)
- corrispettivi: 1051 (RICAVI)
- cespiti: 21 (auto-popolati)
- prima_nota_cassa: 5 (data: datetime, anno: int)
- dipendenti: 34 (dipendenti reali)
- presenze: 20957 (registri presenze)
- cedolini: 841 (buste paga, 14 per 2026)

## Sessione 4 (25 Feb 2026 - Corrente)
- **Nuovi mittenti email aggiunti** (7 nuovi):
  - solleciti.pl.napoli@pec.it (sollecito)
  - pagamenti.online@autostrade.it (autostrade)
  - dimissionitelematiche@pec.lavoro.gov.it (lavoro)
  - preavvisodiaccertamento.napoli@inps.it (KEYWORD search - INPS può usare mittenti diversi)
  - (già presenti: INPSComunica, no_reply@agenziariscossione, inpscomunica)
- **Dizionario email (Message-ID Index)**: Collezione `email_message_index` - traccia i Message-ID già scaricati per evitare ri-download. Indici MongoDB creati per performance.
- **Ordinamento per data**: Email ordinate per INTERNALDATE (più recente prima) via `sort_email_ids_by_date()`
- **Ricerca per keyword**: Mittenti con `cerca_per_oggetto=True` vengono cercati per parole chiave nel soggetto/corpo anziché per FROM (gestisce mittenti che cambiano indirizzo)
- **Nuovi endpoint**: GET /api/email-download/dizionario-email, DELETE /api/email-download/dizionario-email/reset
- **PUT /api/email-download/mittenti/{email}**: Ora supporta anche `cerca_per_oggetto` e `parole_chiave_ricerca`

## Sessione 6 (17 Marzo 2026 - Corrente)
- **Force Reimport**: Nuovo endpoint POST `/api/estratto-conto-movimenti/force-reimport` - cancella tutti i record degli anni del CSV e reinserisce tutto senza deduplicazione (corregge commissioni €1 ripetute)
- **Fix frontend import**: Button "Forza Aggiornamento" (rosso) nella sezione Banca di Prima Nota usa il nuovo endpoint. Button "Importa CSV" (blu) usa endpoint incrementale
- **Correzione import vecchio**: Import precedente bloccava commissioni €1 duplicate (stesso giorno/importo/descrizione). Ora risolto con force-reimport
- **Saldo progressivo corretto**: Calcolo saldo progressivo nella tabella cambiato da backward (total→first) a forward (first→total). Ora parte da 0 e accumula correttamente
- **Saldo cumulativo nascosto**: "Saldo Cumulativo" e "Riporto Anni Prec." ora mostrati solo se saldo_precedente > 0 (nasconde valori negativi da dati storici)
- **Dati 2025**: 2923 records, saldo=€2.839,08, 127 commissioni €1 ✓
- **Dati 2026 (fino 16/03)**: 477 records, saldo=€3.899,37, 52 commissioni €1 ✓

## Sessione 7 (17 Marzo 2026 - Corrente)
- **Prima Nota Cassa — Nuova Logica Definitiva**:
  - DARE = `totale` corrispettivo (PagatoContanti + PagatoElettronico, **IVA inclusa**)
  - AVERE = `pagato_elettronico` (POS → transita in Banca)
  - SALDO CASSA = totale - pagato_elettronico = pagato_contanti ✓
- **Endpoint rebuild**: POST `/api/prima-nota/cassa/rebuild-da-corrispettivi?anno=XXXX`
- **Dati verificati**: 2024=€367.258,60 | 2025=€359.056,59 | 2026=€14.361,17 (tutti corrispondono a pagato_contanti)
- **Bottoni UI**: "Ricostruisci ANNO" (verde) e "Ricostruisci Tutti gli Anni" (rosso) in Prima Nota Cassa
- **Documentazione**: `/app/backend/docs/prima_nota_cassa_logica.md` + ZIP scaricabile

## Sessione 9 (24 Marzo 2026 - Performance & Fix)
- **Performance P0 RISOLTO**: Dashboard carica in 1.88s (era 30-45s)
  - `alert-limiti`: 10.9s → 0.71s (N+1 queries → bulk aggregation, 102 query → 3 query)
  - `saldo-ferie`: 3.0s → 0.73s (12+ sequential → 2 bulk aggregations)
  - Dashboard.jsx: `alert-limiti` caricato separatamente dal Promise.all (non blocca altri widget)
- **CSV Import P1 RISOLTO**: Commissioni ≤€2 ora importate anche se "duplicate" (fix dedup in estratto_conto.py)
- **Saldo progressivo P2 CORRETTO**: PrimaNota.jsx calcola forward (ASC cronologico) e mostra DESC
- **Cedolini P2**: Aggiunto controllo dedup CF+mese+anno in employees_payroll.py
- **Dipendenti P2**: Deduplicazione per CF in list_dipendenti e report ferie-permessi
- **Fix routing**: Dashboard widget link /dipendenti/giustificativi → /presenze?tab=giustificativi

## Sessione 14 (1 Aprile 2026 - Fix Gmail IMAP + Email Integration)

### Fix Integrazione Gmail
- **Bug P0 risolto**: Email `ceraldigroupsr@gmail.com` (mancava "l") → corretta in `ceraldigroupsrl@gmail.com` in tutti i punti:
  - Collezione MongoDB `email_accounts`
  - Collezione MongoDB `settings` (chiave=gmail)
  - File `.env` (IMAP_USER, EMAIL_USER, EMAIL_ADDRESS)
- **Fix email_f24.py**: Le credenziali ora lette da `settings` Pydantic invece di `os.environ.get()` (che non leggeva .env)
- **Tutti e 3 i servizi IMAP ora funzionanti**: `email_document_downloader`, `email_downloader`, `aruba_invoice_parser`
- **Download PDF confermato**: F24 ravv 1040 2025.pdf e CU 2026 avv Carini.pdf scaricati
- **Fix UI mittenti**: `ImpostazioniF24Email.jsx` normalizza ora i mittenti stringa in oggetti con `{email, nome, tipo, parole_chiave}`
- **XML processor già implementato**: `xml_invoice_processor.py` - parsing FatturaPA, inserimento automatico in Prima Nota Banca per pagamenti SEPA/bancari
- **Admin page**: Confermata stabile, nessun loop di refresh

## Sessione 13 (1 Aprile 2026 - Widget Dashboard + Portale + Gmail Settings)

#### Widget Agenti in Dashboard
- `WidgetAgenti.jsx` con 4 contatori colorati (Urgenti/Avvisi/Info/Suggerimenti)
- Auto-refresh ogni 5 minuti, si nasconde se 0 segnalazioni attive
- Click su ogni contatore → naviga a `/agenti`
- Nuovo endpoint `GET /api/agenti/segnalazioni/summary` con aggregazione per tipo

#### Portale Dipendenti (/portale)
- Login Google con Emergent Auth (fuori dal layout principale)
- Dashboard benvenuto con nome e mansione
- Lista cedolini con download PDF
- Lista contratti con pulsante Firma (FES: hash SHA256 + IP + timestamp)
- Nota: la pagina funziona solo se il dipendente ha `google_email` associata nel profilo

#### Impostazioni Gmail IMAP
- Form in `/impostazioni-f24-email` con campi: email, app password (con mostra/nascondi), server IMAP
- Salva in MongoDB `settings` collection (non nel codice/env)
- Test connessione immediato al salvataggio e pulsante "Testa connessione" separato
- `email_monitor_service.py` legge prima da MongoDB, fallback a .env
- Nuovo router `settings_router.py` con `GET/POST /api/settings/gmail` e `POST /api/settings/gmail/test`

#### Endpoint dipendenti
- `GET /api/dipendenti/by-google-email?email=` per il portale



#### Fix Prima Nota Banca — saldoPrecedente
- **Bug fixato**: `PrimaNota.jsx` — Il saldo progressivo in tabella Banca partiva da 0 invece del riporto anni precedenti. Fixato: `saldoPrecedente={bancaData.saldo_precedente || 0}`
- Regola documentata nel PRD: ogni saldo/calcolo rispetta l'anno globale (AnnoContext)

#### Pagina /agenti
- Nuova pagina `Agenti.jsx` con 6 tab: Agenti, Urgenti, Avvisi, Info, Suggerimenti, Pattern appresi
- Ogni agente mostra: nome, stato (attivo/errore), ultima esecuzione, pulsante "Esegui ora"
- Segnalazioni raggruppate per tipo con colori (rosso/arancio/blu/verde), pulsante "Risolto"
- Tab "Pattern appresi" con confidenza e occorrenze per categoria
- Pulsante "Esegui tutti ora" globale in alto a destra

#### OCR PDF in FiscaleSentinella
- Aggiunta funzione `_estrai_testo_pdf()` con `pdfplumber`
- Testo estratto salvato in `documents_inbox.testo_estratto_ocr`

## Sessione 11 (1 Aprile 2026 - Blocchi J+G4)

### Blocco J — Pulizia Codebase
- **Blocco J1 — Backend**: Eliminati 10 file legacy (`lotti.py`, `tracciabilita.py`, `magazzino_doppia_verita.py`, `auto_repair.py`, `force_sync.py`, `sync_router.py`, `missing_endpoints.py`, `missing_endpoints_fix.py`, `batch_reprocessing.py`, `odoo_integration.py`). Rimossi tutti i `include_router` corrispondenti da `main.py`.
- **Blocco J2 — Frontend**: Eliminati 4 file legacy (`HRGestionale.jsx`, `MagazzinoDoppiaVerita.jsx`, `PrimaNotaSalari.jsx`, `RegoleContabili.jsx`). Route `/dipendenti` ora punta a `GestioneDipendentiUnificata.jsx`.

### Blocco G4 — Corrispettivi POS
- `propagate_corrispettivo_to_prima_nota()` in `data_propagation.py` ora separa:
  - Porzione contanti → `prima_nota_cassa` (DARE = pagato_contanti)
  - Porzione elettronica → `prima_nota_banca` (DARE = pagato_elettronico, source=corrispettivo_pos)

### Parte 1 — Sistema Agenti AI
- Creata directory `/app/app/agents/` con: `models.py`, `notifier.py`, `fiscale_sentinella.py`, `hr_guardiano.py`, `learning_brain.py`, `orchestrator.py`
- **FiscaleSentinella**: analizza email ADE, controlla scadenze F24, genera segnalazioni urgenti
- **HRGuardiano**: controlla dimissioni telematiche, scadenze contratti, libretti sanitari, riconcilia cedolini
- **LearningCervello**: genera suggerimenti automatici (es. fatture non pagate >60 giorni)
- Agenti eseguiti ad ogni ciclo di sync email (via `email_monitor_service.py`)
- Nuovo router `/api/agenti/*` con endpoint: segnalazioni, stato, count, run
- Collezioni MongoDB: `agenti_segnalazioni`, `agenti_stato`, `agenti_apprendimenti`

### Parte 2 — Portale HR con Firma Elettronica
- `portal.py` aggiornato con:
  - `POST /portal/collega-google`: collega Google Account a dipendente via codice invito
  - `POST /portal/genera-invito/{id}`: genera codice invito 8 caratteri (valido 7 giorni)
  - `GET /portal/portale/cedolini`: cedolini del dipendente loggato (filtrati per google_email)
  - `GET /portal/portale/contratti`: contratti del dipendente
  - `POST /portal/portale/firma/{id}`: firma FES (timestamp + IP + SHA256 hash documento)
  - Notifica automatica in `agenti_segnalazioni` alla firma

### AgentiPanel.jsx
- Componente `AgentiPanel` in TopNav con badge rosso (count non lette)
- Sidebar destra con lista segnalazioni colorate per tipo (urgente=rosso, avviso=arancio, info=blu)
- Azioni: "Segna letta" e "Risolto"
- Polling badge ogni 60 secondi

### Test Finali Superati
- GET /api/fornitori ✅
- GET /api/prima-nota/banca?anno=2025 ✅
- GET /api/finanziaria/summary (saldo_cassa + saldo_banca) ✅
- GET /api/fatture-tracciabilita/status ✅
- GET /api/agenti/stato (tutti e 3 completati) ✅

- **Riattivazione verificata**: tutti i moduli P0/P1/P2 funzionanti con dati reali MongoDB Atlas
- **Fix Cedolini**: filtro `anno` ora usa `$or [int, string]` - prima restituiva 0 record per 2026
- **Fix Prima Nota Salari**: filtro `anno` ora usa campo `anno` (int) invece di `data` (regex) - prima restituiva 0 record
- **Stato dati reali verificato**:
  - Prima Nota Cassa 2025: 100 movimenti, saldo=€359k ✅
  - Prima Nota Banca 2026: 100 movimenti ✅
  - Prima Nota Salari 2025: 100 movimenti ✅
  - Fornitori: 323 record ✅
  - Invoices: 204 totali (199 del 2026) ✅
  - Dipendenti: 34, no duplicati CF ✅
  - Cedolini 2025: 253, Cedolini 2026: 15 ✅
  - Dashboard bilancio 2026: ricavi=€31k, costi=€171k ✅
- **Test**: 22/22 backend tests passed, 100% frontend modules working

- P2: Credenziali Gmail non valide (IMAP_PASSWORD nel .env) - blocca automazione email (NON priorità corrente)


## Sessione 5 (17 Marzo 2026)
- **Import CSV BPM**: Importati 3.370 nuovi movimenti bancari (da ElencoEntrateUsciteAndamento_17-03-2026), 30 duplicati saltati. Totale in DB: 7.868 record.
- **Totali Prima Nota Banca per anno + cumulativo**: L'API `/movimenti` ora restituisce `saldo_anno`, `saldo_precedente`, `saldo` (cumulativo). La UI mostra 5 card: Entrate Anno, Uscite Anno, Saldo Anno, Saldo Cumulativo, Riporto Anni Prec.
- **Filtri avanzati Prima Nota**: Aggiunti filtri Data Da/A e Importo Min/Max (client-side) alla tabella movimenti sia Cassa che Banca
- **Documentazione aggiornata**: logica_operativa.md aggiornato + ZIP scaricabile: `/api/download/documentazione_ceraldi_erp_17032026.zip`
- **Fix timezone**: Corretto import mancante `timezone` in estratto_conto.py che causava errore 500 sull'endpoint import

## Sessione 8 (20 Marzo 2026 - Corrente)
- **Pagina "Come Funziona il Gestionale"** (`/mappa-gestionale`): Creata e resa accessibile tramite menu "Altro"
- **Flusso dati per 16 moduli**: Ogni modulo ha 4 sezioni strutturate:
  - ENTRA DA: sorgenti dati con dettaglio
  - COSA FA: logica di elaborazione
  - ALIMENTA / POPOLA: destinazioni a valle
  - ASPETTA / RICONCILIA CON: controlli incrociati e riconciliazioni (con livello di urgenza)
- **Diagramma Mermaid interattivo**: Mostra l'intero flusso dati aziendale; editor modificabile dall'utente
- **Logica specifica documentata**:
  - Prima Nota Cassa: DARE=Ricavi Lordi, AVERE=POS→Banca, aspetta estratto conto + chiusura POS sera
  - Prima Nota Banca: aspetta POS cassa, bonifici fornitori, F24, cedolini stipendi
  - Prima Nota Salari: genera F24 contributi + bonifici attesi in banca
