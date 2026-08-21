# Guida semplice: cosa fai tu, cosa fa Render e cosa mostra il Gestionale

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## La risposta più importante

Pensa al sistema come a un ufficio con quattro stanze:

1. **Google Drive è l'armadio degli originali.**
2. **Render è il fattorino che controlla e smista.**
3. **Il Gestionale è il registro che collega tutti i fatti.**
4. **Tu sei la persona che decide nei casi dubbi.**

Render non è un secondo Gestionale e non è un secondo archivio. Non deve
inventare dati, pagamenti o collegamenti. Esegue in modo programmato le stesse
regole del GestionaleCloud.

### Se non metto il file nel Calderone, cosa succede?

Render controlla soltanto `00 - CALDERONE/01 - IN ARRIVO`. Se non metti lì il
file, quel task Render non lo vede e non fa nulla. Restano però attivi gli altri
ingressi del Gestionale: monitor email, cartelle Drive specialistiche, API e
caricamenti manuali. Tutti devono convergere nello stesso ingresso canonico;
non devono importare due volte lo stesso originale.

### Quali documenti sono già instradabili?

| Documento riconosciuto | Destinazione esistente | Stato del collegamento |
|---|---|---|
| Fattura elettronica XML/P7M | `upload-auto` → fatture | pronto in anteprima |
| Corrispettivo telematico XML | `upload-auto` → corrispettivi | pronto in anteprima |
| F24 | `upload-auto` → registro F24 | pronto in anteprima |
| Quietanza F24 | `upload-auto` → quietanze F24 | pronto in anteprima |
| Cedolino/LUL | `upload-auto` → Libro Unico | pronto in anteprima |
| Estratto conto riconoscibile | `upload-auto` → movimenti bancari | pronto in anteprima |
| Dichiarazione fiscale | registro dichiarazioni | revisione richiesta |
| Bonifico generico/distinta | archivio bonifici/distinte | revisione richiesta |
| Cartella, avviso o verbale generico | atti amministrativi/PagoPA/AdeR | revisione richiesta |

“Pronto in anteprima” significa che Render sa indicare il parser canonico, ma
non trasmette ancora il documento: il task resta senza scritture, spostamenti o
cancellazioni fino al collaudo e alla conferma dell'ingestione autenticata.

### Come è protetto l'import reale

Il task `calderone_documenti_ingest` non parte automaticamente. Per funzionare
devono essere vere contemporaneamente tutte queste condizioni:

1. `ENABLE_RENDER_CANONICAL_INGEST=true` sul Workflow;
2. lo stesso `RENDER_INGEST_SHARED_SECRET` sul Workflow e sul Gestionale;
3. avvio esplicito del task con `confirm=true`;
4. hash assente dall'indice canonico;
5. famiglia documentale classificata con parser pronto;
6. anteprima del Gestionale riuscita e token breve valido.

Render invia prima il file all'anteprima dedicata e solo dopo, se non è un
duplicato e non ci sono errori bloccanti, all'import canonico. Trasmette anche
l'ID del file Drive, l'ID della cartella di provenienza e l'hash della sorgente.
Non sposta e non cancella l'originale.

### Legenda colori delle cartelle

| Colore | Significato operativo |
|---|---|
| Verde | flusso completo, collaudato e attivo |
| Giallo | riconoscimento/anteprima pronti, import automatico non ancora attivo |
| Rosso | errori da correggere |
| Grigio | cartella di archivio o flusso non ancora collegato |

Il colore è un indicatore umano, non attiva il software. Una cartella diventa
verde soltanto dopo un test completo: ingresso, deduplica, parser, registrazione
canonica, pagina del Gestionale e prova di reimportazione idempotente.

## L'albero completo

```text
FONTI
├── file messi manualmente nel Calderone
├── allegati provenienti da mittenti email attendibili
├── cartelle Drive già autorizzate
└── API autorizzate, per esempio SumUp
    │
    ▼
00 - CALDERONE
└── 01 - IN ARRIVO
    │
    ▼
RENDER
├── vede se il file è nuovo o invariato
├── calcola SHA-256
├── confronta l'indice documentale del Gestionale
├── duplicato esatto → non crea un altro documento
├── nuovo riconoscibile → propone la categoria corretta
├── dubbio → DA_VERIFICARE
└── errore tecnico → ERRORE
    │
    ▼
INGRESSO UNICO DEL GESTIONALE
└── documents_inbox / upload-auto
    │
    ▼
PARSER SPECIALISTA
├── cedolino
├── dichiarazione fiscale
├── F24 o quietanza
├── estratto conto PDF/CSV/Excel
├── bonifico
├── cartella esattoriale o avviso
├── fattura
├── verbale/PagoPA
└── documento non riconosciuto
    │
    ▼
FATTO CANONICO
├── crea le attese obbligatorie
├── aspetta le prove future
├── riconcilia solo se la prova è certa
└── aggiorna le pagine collegate del Gestionale
```

## Il flusso atomico, spiegato passo per passo

### 1. Arriva una fonte

Una fonte è il posto dal quale arriva il documento: Drive, email, caricamento
manuale o API. La fonte viene sempre conservata.

Esempio: metti un PDF nella cartella `01 - IN ARRIVO`.

### 2. Il documento riceve un'impronta

Render calcola lo SHA-256. È come l'impronta digitale del file.

- stessa impronta: è lo stesso identico file;
- impronta diversa: è un altro file, anche se nome e importo sembrano uguali.

Il nome del dipendente, il mese o l'importo non bastano per cancellare un file.

### 3. Render consulta l'indice prima di leggere

Render confronta l'impronta con `INDICE_DOCUMENTALE_DRIVE.xlsx`.

- Se esiste già, registra una nuova **occorrenza/provenienza**, ma non crea un
  secondo documento contabile.
- Se non esiste, il documento passa alla classificazione.
- Se l'indice manca o non è leggibile, Render si ferma: non presume che il
  documento sia nuovo.

### 4. Il documento viene classificato

Il sistema prova a capire che cosa è: cedolino, estratto conto, dichiarazione,
F24, cartella esattoriale, bonifico, fattura, verbale o altro.

- una sola risposta certa: `CLASSIFICATO`;
- più risposte possibili: `DA_VERIFICARE`;
- problema tecnico: `ERRORE`.

### 5. Il parser specialista legge i campi

Ogni tipo ha il proprio lettore. Non esiste una regola generica che prende un
numero qualsiasi dal PDF.

Esempi:

- cedolino: dipendente, periodo, competenze, trattenute e netto verificato;
- estratto conto: conto, data, valuta, movimenti, saldo e CRO/TRN;
- dichiarazione: contribuente, tipo, anno e protocollo;
- cartella: ente, numero, tributi, importi e scadenze;
- bonifico: ordinante, beneficiario, data, importo e CRO/TRN.

### 6. Nasce il fatto canonico

Un fatto canonico è la sola registrazione autorevole di ciò che il documento
dimostra.

Esempio: un cedolino dimostra che esiste un netto dovuto. Non dimostra che il
bonifico sia stato eseguito.

### 7. Il fatto crea subito le attese

Questa è la regola fissa dell'albero importato:

```text
FONTE → DOCUMENTO → CLASSIFICAZIONE → FATTO
      → OBBLIGHI → ATTESE → PROVE → RICONCILIAZIONE
      → PRIMA NOTA → CONTABILITÀ → CONTROLLO → CHIUSURA
```

Esempi:

- cedolino → bonifico e prova bancaria attesi;
- F24 → quietanza e addebito bancario attesi;
- fattura fornitore → debito, scadenza e pagamento attesi;
- corrispettivo POS → accredito del gestore atteso;
- cartella/avviso → pagamento e quietanza attesi, se dovuti.

Una prova arrivata dopo non inventa il fatto iniziale: può soltanto soddisfare
un'attesa esistente o restare da verificare.

### 8. Le prove vengono collegate

F24, quietanza e movimento bancario sono tre oggetti diversi. Cedolino e
bonifico sono due oggetti diversi. Fattura e pagamento sono due oggetti diversi.

Il collegamento automatico avviene soltanto quando identità, periodo,
riferimenti, valuta e importo sono compatibili in modo deterministico.

### 9. Il Gestionale aggiorna le pagine

Il dato appare nella pagina del proprio dominio e nelle pagine collegate:

- cedolini e pagamenti → `/salari` e riconciliazione stipendi;
- estratti conto e bonifici → movimenti banca e riconciliazione;
- F24 e dichiarazioni → situazione fiscale;
- cartelle, avvisi e verbali → atti amministrativi/PagoPA;
- tutti gli originali → archivio documenti e indice Drive.

Ogni collegamento deve poter essere percorso in entrambe le direzioni.

## Cosa devi fare tu nella vita quotidiana

### Quando ricevi un nuovo documento

1. Mettilo in `00 - CALDERONE/01 - IN ARRIVO`.
2. Non rinominarlo per far capire al sistema l'importo.
3. Non preoccuparti se forse esiste già: decide lo SHA-256.
4. Attendi il ciclo Render.
5. Apri il Gestionale e controlla la coda `DA_VERIFICARE`.
6. Intervieni soltanto sui casi realmente dubbi.

### Quando ricevi molti documenti

Puoi caricare uno ZIP. Render deve controllare separatamente ogni documento
interno. Un duplicato nello ZIP non genera una seconda registrazione.

### Quando arriva un'email

Il monitor controlla soltanto i mittenti configurati come attendibili. Conserva
la provenienza email e manda gli allegati nella stessa pipeline documentale.
Non risponde, non cancella e non sposta automaticamente l'email.

### Quando il Gestionale chiede una scelta

Scegli solo se puoi riconoscere con certezza il collegamento. Se non sei sicuro,
lascia `DA_VERIFICARE`: è uno stato corretto, non un errore da nascondere.

## Cosa non devi fare

- Non caricare lo stesso archivio in più cartelle per “essere sicuro”.
- Non cancellare manualmente originali prima della verifica.
- Non considerare “pagato” ciò che ha soltanto una ricevuta o una quietanza.
- Non collegare due movimenti perché hanno soltanto lo stesso importo.
- Non correggere i dati direttamente nei fogli senza passare dalle funzioni del
  Gestionale e dall'audit.

## Come reintegrare o ricostruire dati dell'app

Se una pagina è vuota o mancano dati:

1. Non ricaricare subito tutti i documenti.
2. Controllare che gli originali esistano ancora in Drive.
3. Controllare `INDICE_DOCUMENTALE_DRIVE.xlsx` e il registro dati Sheets.
4. Confrontare SHA-256, ID Drive, conteggi e stato parser.
5. Reintegrare soltanto le righe mancanti usando la pipeline canonica.
6. Ripetere l'import dello stesso documento: il risultato corretto è
   `nuovi=0`, senza nuove scritture contabili.
7. Verificare la pagina interessata dopo refresh e riavvio.
8. Verificare anche le relazioni inverse e le attese aperte.

Gli originali Drive più gli indici Sheets devono permettere di ricostruire il
Gestionale senza inventare dati.

## Perché oggi non vedi ancora risultati Render nell'app

La situazione attuale è questa:

1. il Workflow Render esiste;
2. il nuovo task generale è nel codice;
3. l'ID dell'indice Drive è configurato;
4. nessuna nuova scansione è stata avviata;
5. il task è ancora in modalità `preview`, quindi non scrive nel Gestionale;
6. manifest/watermark e invio autenticato dei soli documenti nuovi devono essere
   completati e collaudati.

Per questo non compare ancora una pagina con “risultati Render”. È intenzionale:
prima rendiamo sicuro il confronto, poi abilitiamo la scrittura.

## Cosa vedrai quando il processo sarà completo

Nel Gestionale vedrai un riepilogo semplice:

```text
Ultimo controllo Render: data e ora
File sorgente invariati: 120
Duplicati esatti: 8
Documenti nuovi registrati: 3
Da verificare: 1
Errori tecnici: 0
```

Ogni numero dovrà essere cliccabile e mostrare l'elenco preciso. Non dovrai
entrare normalmente nel pannello Render: Render sarà il motore; il Gestionale
sarà il posto nel quale controlli il lavoro.

## Stati spiegati in parole semplici

| Stato | Significato |
|---|---|
| `CLASSIFICATO` | Il sistema ha capito il tipo di documento |
| `ATTESO` | Il fatto esiste e aspettiamo una prova futura |
| `DA_VERIFICARE` | Serve una scelta umana |
| `IN_ELABORAZIONE` | Il lavoro è in corso |
| `ERRORE` | Problema tecnico; l'originale resta conservato |
| `SODDISFATTO` | La prova corretta ha chiuso l'attesa |
| `NON_APPLICABILE` | Quell'attesa non serve per questo caso |
| `SUPERATO` | Un fatto più recente ha sostituito quello precedente |

Il processo è chiuso soltanto quando tutte le attese obbligatorie sono in uno
stato terminale positivo.

## Regola finale da ricordare

```text
Tu metti il documento nel Calderone.
Render controlla, confronta e smista.
Il Gestionale registra fatti e attese.
Le prove chiudono le attese.
Tu decidi soltanto quando il sistema non può essere certo.
```

Documenti normativi collegati:

- `docs/REGOLA_FISSA_ATTESE.md`;
- `PROMPT_MASTER.md`;
- `docs/ADR-005-INGESTIONE-DOCUMENTALE-UNIVERSALE-RENDER.md`.
