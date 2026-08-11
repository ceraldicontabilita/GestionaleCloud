# Audit consolidamento ERP — 2026-08-11

Branch di lavoro: `audit/consolidamento-erp-2026-08-11`
PR draft: `#175`

## Obiettivi vincolanti

1. Un solo punto di importazione utente: `ImportDocumenti`.
2. Rimuovere dalle altre pagine i controlli UI di import; mantenere parser, endpoint e servizi riutilizzati dalla pipeline centrale.
3. Rimuovere i normali pulsanti manuali `Sincronizza/Aggiorna` quando l'operazione può avvenire automaticamente all'apertura pagina o tramite scheduler/backend.
4. Distinguere sempre documento, disposizione, pagamento, movimento bancario e riconciliazione.
5. Nessuna associazione ambigua diventa definitiva: usare `Da verificare`/dati provvisori.
6. Un evento economico non deve essere duplicato perché esistono più documenti collegati.
7. Audit pagina-per-pagina di tutti i controlli UI e riduzione dell'architettura da circa 63 pagine/componenti operativi a circa 40 superfici funzionali reali.

## Classificazione di ogni controllo UI

Ogni bottone/azione deve ricevere una decisione:

- **TENERE** — azione utente necessaria.
- **AUTOMATIZZARE** — azione tecnica ordinaria che non deve dipendere da un click.
- **SPOSTARE** — funzione valida nella pagina sbagliata.
- **ACCORPARE** — duplicata da un'altra funzione canonica.
- **ELIMINARE** — inutile, ridondante, decorativa o puramente tecnica.

Ogni pagina deve ricevere una classificazione:

- **MANTENERE**
- **ACCORPARE**
- **TRASFORMARE IN TAB**
- **DETTAGLIO/DRAWER**
- **DIAGNOSTICA/ADMIN**
- **ELIMINARE**

## Regola di verifica

Per ogni azione: `Pagina -> controllo -> handler -> endpoint -> servizio -> database -> effetti secondari -> duplicazioni -> decisione -> test`.

## Baseline architetturale verificata

### Router reale

`frontend/src/main.jsx` mostra che il progetto ha già iniziato una strategia di consolidamento tramite HUB. Le route canoniche principali sono gestite da:

- DashboardHub
- FattureHub
- FornitoriHub
- PrimaNotaHub
- VeicoliHub
- ContabilitaHub
- DocumentiHub
- StrumentiHub
- IntegrazioniHub
- AdminHub
- RiconciliazioneHub

A queste si aggiungono pagine standalone ancora esposte direttamente, tra cui Inserimento Rapido, Scadenze, Ritenute, Gestione Riservata, Dettaglio Verbale, Impostazioni F24 Email, Impostazioni AI, Assistente Ceraldi, Mappa Gestionale, Agenti, Learning Machine, Gestione IVA, Fatture Estere Verifica, Cedolini e Situazione Fiscale.

**Conclusione:** il numero "63 pagine" non coincide con 63 route top-level. Una parte rilevante sono componenti/pagine legacy caricati dentro gli HUB. La riduzione corretta deve quindi misurare le **superfici funzionali realmente visibili all'utente**, non soltanto il numero di file `.jsx`.

### Navigazione

`frontend/src/navigation.config.js` è la fonte unica per desktop e mobile. La riduzione delle pagine va eseguita partendo da questa configurazione, senza creare menu paralleli.

### Documenti / Drive

`frontend/src/pages/hub/DocumentiHub.jsx` esponeva il bottone `Sincronizza Drive`, collegato a `POST /api/documenti/drive/sync`.

**Correzione applicata:** rimosso il bottone e lo stato UI di sincronizzazione; all'apertura dell'hub viene caricato il catalogo Drive e, se sono presenti cartelle con parser automatico, viene avviata la sincronizzazione senza intervento utente.

### F24 Email Sync

`frontend/src/App.jsx` importava `F24EmailSync`, manteneva lo stato `showF24Sync` e renderizzava un popup. La ricerca di `setShowF24Sync` trovava riferimenti soltanto nello stesso file e nessun punto che impostasse lo stato a `true`.

**Correzione applicata:** rimossi import, stato e render del popup morto/manuale da `App.jsx`. Il servizio/componente non viene cancellato in questa fase perché va prima verificato se è richiamato da altri flussi amministrativi o scheduler.

### Import distribuiti

Sono già stati individuati ingressi o riferimenti di import in pagine diverse da `ImportDocumenti`, tra cui: `CedoliniSalari`, `Corrispettivi`, `GestionePagoPA`, `RiconciliazionePaypal`, `VerificaMovimentiBanca`, `GestioneCespiti`, `ArchivioBonifici`, `LibroGiornale`, `CoerenzaPOSCorrispettivi`.

### Sincronizzazioni distribuite

Sono già stati individuati riferimenti di sincronizzazione in: `DocumentiHub`, `Documenti`, `Admin`, `ArchivioBonifici`, `RiconciliazionePaypal`, `RiconciliazioneUnificata`, `PuliziaPrimaNota`, `BatchProcessor`, `Pianificazione`, `Corrispettivi`, `Fornitori`, `ArchivioFattureRicevute` e nel componente `F24EmailSync`.

## Accorpamenti candidati da validare sul codice

- Dashboard Relazionale -> Dashboard (tab tecnico)
- Pulizia Prima Nota -> Prima Nota (tab Controlli)
- Verifica Movimenti Banca -> area Banca/Riconciliazione
- Coerenza POS/Corrispettivi -> Corrispettivi (tab Controlli)
- Archivio Bonifici -> Banca/Riconciliazione (tab Bonifici)
- Riconciliazione PayPal -> Riconciliazione (sorgente PayPal)
- PagoPA -> Pagamenti/Riconciliazione
- Verifica Bilancio -> Bilancio (tab Verifica)
- Controllo Contabilità -> Bilancio (tab Controlli)
- Utile Obiettivo -> Budget/Previsionale
- Costi Noleggio -> Flotta/Noleggi (tab Costi)
- Dettaglio Verbale -> drawer/scheda della pagina Verbali
- Batch Reprocessing -> Batch Processor
- Impostazioni F24 Email -> Admin/Automazioni
- Learning Machine -> Agenti/Automazioni
- Mappa Gestionale -> Diagnostica, fuori dal menu operativo
- Inserimento Rapido -> modalità/pannello, non pagina primaria

## Registro problemi e modifiche

| ID | Area | Problema | Decisione | Stato |
|---|---|---|---|---|
| A-001 | Import | Più punti UI di importazione | Centralizzare in `ImportDocumenti` | IN ANALISI |
| A-002 | Sync / Documenti | `Sincronizza Drive` manuale | Auto-sync all'apertura di `DocumentiHub` | APPLICATO, DA TESTARE |
| A-003 | App / F24 | Popup `F24EmailSync` morto/manuale | Rimuovere infrastruttura UI non attivabile | APPLICATO, DA TESTARE |
| A-004 | Navigazione | Troppe superfici operative/componenti legacy | Consolidare a ~40 superfici funzionali | IN ANALISI |
| A-005 | Documenti | Rischio duplicazione evento economico tra documenti collegati | Audit end-to-end | IN ANALISI |
| A-006 | Router | Molte pagine sono già componenti interni a HUB, non route autonome | Misurare pagine per funzione visibile | CONFERMATO |

## Criterio di chiusura

Una modifica è `CHIUSA` solo quando:

1. il codice duplicato/manuale è rimosso o spostato;
2. il flusso canonico resta funzionante;
3. frontend, API, backend e database sono coerenti;
4. esiste un test o una verifica ripetibile;
5. non sono introdotte regressioni sugli altri documenti/moduli.
