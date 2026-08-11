# Audit consolidamento ERP — 2026-08-11

Branch di lavoro: `audit/consolidamento-erp-2026-08-11`

## Obiettivi vincolanti

1. Un solo punto di importazione utente: `ImportDocumenti`.
2. Rimuovere dalle altre pagine i controlli UI di import; mantenere parser, endpoint e servizi riutilizzati dalla pipeline centrale.
3. Rimuovere i normali pulsanti manuali `Sincronizza/Aggiorna` quando l'operazione può avvenire automaticamente all'apertura pagina o tramite scheduler/backend.
4. Distinguere sempre documento, disposizione, pagamento, movimento bancario e riconciliazione.
5. Nessuna associazione ambigua diventa definitiva: usare `Da verificare`/dati provvisori.
6. Un evento economico non deve essere duplicato perché esistono più documenti collegati.
7. Audit pagina-per-pagina di tutti i controlli UI e riduzione dell'architettura da circa 63 pagine a circa 40 pagine operative reali.

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

## Evidenze iniziali verificate

### Navigazione

`frontend/src/navigation.config.js` è la fonte unica per desktop e mobile. La riduzione delle pagine va eseguita partendo da questa configurazione, senza creare menu paralleli.

### F24 Email Sync

`frontend/src/App.jsx` importa `F24EmailSync`, mantiene `showF24Sync` e renderizza un popup. La ricerca di `setShowF24Sync` mostra al momento riferimenti solo nello stesso file; va verificato come infrastruttura potenzialmente morta e comunque incompatibile con la regola "sincronizzazione ordinaria senza bottone/popup".

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
| A-002 | Sync | Sincronizzazioni manuali sparse | Automatizzare carico/scheduler | IN ANALISI |
| A-003 | App | `F24EmailSync` popup/stato apparentemente non attivato | Verificare e rimuovere UI morta/manuale | CONFERMATO DA RICERCA |
| A-004 | Navigazione | Troppe pagine operative | Consolidare a ~40 | IN ANALISI |
| A-005 | Documenti | Rischio duplicazione evento economico tra documenti collegati | Audit end-to-end | IN ANALISI |

## Criterio di chiusura

Una modifica è `CHIUSA` solo quando:

1. il codice duplicato/manuale è rimosso o spostato;
2. il flusso canonico resta funzionante;
3. frontend, API, backend e database sono coerenti;
4. esiste un test o una verifica ripetibile;
5. non sono introdotte regressioni sugli altri documenti/moduli.
