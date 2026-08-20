# Obsidian Knowledge Architecture — GestionaleCloud

<!-- gestionalecloud-doc
status: draft
reviewed_at: 2026-08-20
storage_architecture: drive-only
source: attachment Pasted text #1
-->

## Obiettivo

Obsidian non deve essere un semplice archivio di verbali. Deve diventare il livello di conoscenza aziendale del GestionaleCloud: un grafico di entità, relazioni, cronologie, procedure e decisioni, collegato ai dati operativi del gestionale senza sostituire il registro contabile o i documenti originali.

La logica corretta è:

- Google Drive / Sheets: archivio canonico operativo e registro strutturato
- GestionaleCloud: motore applicativo, workflow, import, validazione, contabilità, riconciliazione
- Obsidian: conoscenza collegata, procedure, cronologie, relazioni semantiche, ricerca aziendale e spiegazione dei contesti
- Codex / agenti: leggono GestionaleCloud + Obsidian e propongono azioni controllate

## Architettura di riferimento

```text
GestionaleCloud
  dati operativi, stati, importi, pagamenti, autorizzazioni

Google Drive / Sheets
  archivio canonico, documenti originali, registri strutturati

Obsidian
  conoscenza collegata, cronologie, procedure, ricerca e spiegazione

Codex / agenti
  consultano Gestionale + Obsidian e propongono attività controllate
```

## Principi

1. Obsidian non sostituisce il sistema contabile.
2. Obsidian non modifica importi, pagamenti o riconciliazioni.
3. Obsidian conserva la conoscenza, non la prova normativa o finanziaria.
4. Il dato operativo resta nel Gestionale e nel registro Drive/Sheets, mentre Obsidian espone il contesto.
5. La relazione tra entità è fondamentale: soggetto, pratica, scadenza, documento, pagamento, movimento bancario, dichiarazione.
6. Le eccezioni devono essere generate automaticamente, non lasciate in un archivio manuale.
7. La ricerca deve essere unificata: nome, targa, codice fiscale, numero fattura, codice avviso, soggetto, pratica.

## Aree da portare in Obsidian

### Contabilità
- fatture
- fornitori
- movimenti
- riconciliazioni
- F24
- quietanze
- IVA
- cronologia dei documenti e dei pagamenti

### Documenti
- PDF
- XML
- PEC
- email
- provenienza
- collegamento tra documento e pratica

### Fiscalità
- dichiarazioni
- codici tributo
- scadenze
- crediti
- versamenti
- dossier fiscale per anno e imposta

### Personale
- dipendenti
- contratti
- cedolini
- corsi
- assegnazioni

### Veicoli
- targa
- driver
- assicurazione
- manutenzione
- verbali
- storico del veicolo

### Banche
- conti
- movimenti
- pagamenti
- prove
- spiegazione di riconciliazione

### Fornitori
- anagrafica
- contratti
- fatture
- bonifici
- PEC
- anomalie

### Clienti
- rapporti
- documenti
- comunicazioni
- memoria aziendale del rapporto

### Immobili
- struttura
- utenze
- manutenzioni
- autorizzazioni

### Atti amministrativi
- TARI
- AdeR
- verbali
- autorizzazioni
- contestazioni
- timeline di ogni pratica

### Procedure
- importazioni
- pagamenti
- controlli
- emergenze
- manuale operativo

### Decisioni
- perché è stata fatta una modifica o scelta
- storico del ragionamento e del contesto
- decisioni critiche non persi in un flusso casuale

### Controlli automatici
- Gmail / Drive / backup / job / anomalie
- diario tecnico e audit

### Normativa
- pagine ufficiali
- circolari
- istruzioni
- bibliografia applicabile alle pratiche

## Modello di soggetti e relazioni

Ogni entità del Gestionale avrebbe una nota dedicata:

```text
Azienda
├── Dipendenti
├── Driver
├── Veicoli
├── Fornitori
├── Clienti
├── Banche
├── Enti pubblici
├── Immobili
└── Pratiche
```

Esempio di nota soggetto:

```markdown
# Ceraldi Group SRL

- Dipendenti: [[Dipendenti]]
- Veicoli: [[Veicoli]]
- F24: [[Fiscalità/F24]]
- Dichiarazioni: [[Fiscalità/Dichiarazioni]]
- Conti correnti: [[Banche]]
- Atti amministrativi: [[Atti amministrativi]]
- Scadenze aperte: [[Scadenze]]
```

## Fascicolo intelligente per ogni soggetto

Per ogni entità, Obsidian può raccogliere automaticamente:

- anagrafica
- fatture
- pagamenti
- bonifici
- contratti
- email e PEC
- documenti mancanti
- note
- anomalie
- attività aperte

Questo vale per:

- fornitori
- dipendenti
- veicoli
- clienti
- immobili
- enti pubblici
- pratiche

## Timeline automatica

Ogni evento rilevante deve diventare una riga cronologica:

```markdown
2026-03-10 — Ricevuta fattura
2026-03-12 — Fattura contabilizzata
2026-03-18 — Bonifico disposto
2026-03-19 — Movimento bancario trovato
2026-03-20 — Riconciliazione confermata
```

Questa timeline è un vantaggio chiave perché permette di capire rapidamente cosa è successo senza aprire molte sezioni diverse.

## Pagine delle eccezioni

Obsidian dovrebbe generare automaticamente pagine di controllo come:

- Documenti da verificare
- Fatture senza pagamento
- Pagamenti senza fattura
- F24 senza quietanza
- Quietanze senza F24
- Movimenti bancari non riconciliati
- Verbali senza driver
- Veicoli con documenti in scadenza
- Dipendenti con documenti mancanti
- PEC senza pratica associata
- Errori del controllo giornaliero
- Scadenze dei prossimi 7/30/90 giorni

Queste pagine non devono essere copie manuali: devono essere generate dai dati correnti.

## Canvas aziendali

Canvas consente una rappresentazione visiva delle relazioni tra entità e flussi.

### Esempi di canvas utili
- ciclo fattura → pagamento → banca
- F24 → quietanza → movimento bancario
- verbale → veicolo → driver → pagamento
- dipendente → contratto → cedolino → bonifico
- PEC → pratica → documento → scadenza
- organizzazione aziendale
- immobili, utenze e manutenzioni
- mappa delle automazioni del Gestionale

## Procedure operative e formazione

Obsidian è ideale per documentare:

- come registrare una fattura
- come verificare un bonifico
- come trattare un F24
- come gestire una PEC
- come associare un verbale
- come correggere un errore
- checklist mensili e annuali
- procedure di backup
- procedure di emergenza
- manuale del GestionaleCloud

Il Gestionale potrebbe mostrare, in ogni pagina, un collegamento diretto a una procedura di supporto.

## Normativa e fonti ufficiali

Obsidian può integrare fonti normative e istruzioni tramite Web Clipper e note collegate:

- circolari dell’Agenzia delle Entrate
- istruzioni F24
- pagine INPS e INAIL
- regolamenti comunali
- norme sulle sanzioni
- guide pagoPA
- documentazione tecnica
- sentenze o interpretazioni rilevanti

Ogni fonte viene collegata alle pratiche a cui si applica.

## Automazione tecnica consigliata

Il Gestionale dovrebbe avere un servizio `Obsidian Knowledge Export` che:

1. legge i registri canonici;
2. genera Markdown con proprietà strutturate;
3. crea collegamenti tra entità;
4. aggiorna note e indici;
5. conserva le annotazioni personali;
6. genera Canvas e pagine delle eccezioni;
7. registra l’esito della sincronizzazione;
8. usa Obsidian CLI / Headless Sync per sincronizzare il vault.

Obsidian CLI permette di creare, leggere, cercare ed esportare note, usare scheduler e script e sincronizzare un vault anche da server.

## Struttura vault consigliata

### Vault 1: GestionaleCloud-Privato

Contiene dati sensibili come:

- contabilità
- banche
- fiscalità
- dipendenti
- documenti sensibili
- PEC
- verbali

### Vault 2: GestionaleCloud-Procedure

Contiene:

- manuali
- checklist
- procedure
- formazione
- documentazione tecnica
- decisioni architetturali

### Vault 3: GestionaleCloud-Condivisibile

Contiene informazioni autorizzate e condivisibili:

- procedure per collaboratori
- documentazione eventualmente pubblicabile
- nulla di sensibile per fiscalità, banche o personale

Questa separazione consente autorizzazioni, sincronizzazione e sicurezza senza esporre tutto a tutti.

## Cosa non fare

- Obsidian non deve diventare il registro contabile.
- Non deve modificare direttamente importi, pagamenti o riconciliazioni.
- Non deve contenere password, token o credenziali.
- Non deve duplicare indiscriminatamente migliaia di PDF.
- Non deve essere l’unico archivio dei documenti.
- I plugin comunitari non devono ricevere automaticamente accesso a dati sensibili.
- Obsidian Publish non deve essere usato sul vault privato.
- Le annotazioni libere non devono cambiare stati operativi.

## Direzione architetturale corretta

La vera integrazione non è esportare verbali in Markdown. La vera integrazione è costruire un grafo aziendale:

```text
Documento
   ↓
Soggetto ── Pratica ── Scadenza
   ↓          ↓
Fattura ── Pagamento ── Movimento bancario
   ↓
F24 / Quietanza / Dichiarazione

Veicolo ── Driver ── Verbale
Immobili ── Utenze ── Manutenzioni
Dipendente ── Contratto ── Cedolino
```

## Fasi realizzabili

1. struttura dei vault e definizione degli identificatori
2. soggetti, documenti e pratiche
3. contabilità, fiscalità e banche
4. personale, veicoli e immobili
5. procedure, decisioni e normativa
6. Canvas, dashboard ed eccezioni
7. accesso controllato per agenti e automazioni

## Valore operativo finale

La funzione più importante è una ricerca unica: inserire un nome, una targa, un codice fiscale, un numero di fattura o un codice avviso e ottenere immediatamente tutte le relazioni pertinenti.

In altre parole, Obsidian non deve essere un “contenitore di documenti”. Deve essere la memoria relazionale dell’azienda.

## Integrazione con il repo corrente

L’idea va integrata come livello di conoscenza secondario rispetto alle fonti operative canoniche del repo:

- il sistema di record e i registri restano in Drive / Sheets e nel backend
- il modello operativo di contabilità, flotta, fiscalità e documenti resta nel GestionaleCloud
- Obsidian serve a rendere navigabile, collegabile e spiegabile il contesto aziendale sulle entità e sulle relazioni

La corretta configurazione prevede quindi un’integrazione controllata, non una duplicazione del sistema di prova o della contabilità.
