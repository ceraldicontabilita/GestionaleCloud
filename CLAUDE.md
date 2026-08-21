# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Aggiornato il 20/08/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

Prima di ogni intervento leggere `PROMPT_MASTER.md`: è la specifica normativa
unica. Questo file è soltanto il punto di ingresso operativo per Claude.

Questo file contiene le regole operative per chi modifica il progetto. Il
codice corrente, i test e la configurazione effettiva di produzione hanno
precedenza sui report storici.

## Lingua e risultato atteso

- Rispondi e documenta in italiano.
- Porta a termine una funzione alla volta: analisi, modifica, test, verifica
  e pubblicazione richiesta dall'utente.
- Non dichiarare completato un flusso basandoti soltanto su HTTP 200, build o
  presenza della pagina. Verifica dati, relazioni, deduplica e risultato live.
- Esponi all'utente il risultato e gli eventuali blocchi, non una sequenza di
  pulsanti tecnici da premere.

## Autorità del repository

- Repository: `https://github.com/ceraldicontabilita/GestionaleCloud`.
- Checkout canonico Windows: `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`.
- Branch operativo: `main`.
- Non usare repository privati non canonici, ZIP o vecchi checkout come autorità.
- Prima di intervenire confronta sempre `HEAD` con `origin/main`.
- Il worktree può contenere modifiche dell'utente: non cancellarle, non
  ripristinarle e non includerle nei commit.
- Mai `git add -A`: aggiungere solo i file pertinenti e verificati.

## Fonti di verità

1. Originali Drive e identificatori delle fonti esterne.
2. Codice, test e configurazione live correnti.
3. `PROMPT_MASTER.md` per tutte le regole normative e i divieti.
4. `page_catalog.json` e mappe generate per la superficie tecnica.

I JSON in `memoria/pagine/` e `memoria/popup/` sono mappe tecniche generate:
si aggiornano con `scripts/refresh_json_docs.py`, non a mano.

## Archivio dati: stato reale e destinazione

### Stato attuale

- Google Sheets/Drive è l'unico archivio operativo.
- Il runtime non espone backend alternativi e non ha fallback legacy.
- Ogni modifica deve preservare sincronizzazione, conteggi, hash, lettura,
  scrittura e ricostruzione positiva di tutti i registri.

### Destinazione Drive-only

La radice operativa deve contenere:

```text
REGISTRO DATI/
  Ceraldi ERP - Registro dati
PARTENOPAY/
CODICI TRIBUTO/
QUIETANZE/
DICHIARAZIONI/
```

La mappa privata delle cartelle è il foglio `_INDICE_DRIVE` del registro.
Per ogni area operativa contiene cartella canonica, `Da elaborare`,
`Elaborate`, `Errori` e nome della variabile Render. Non duplicare gli ID nei
file pubblici del repository e non reintrodurre alias Render per la stessa
cartella.

Il registro usa un foglio per archivio logico. Ogni riga conserva almeno:

- progressivo stabile del foglio;
- `canonical_id` dell'entità;
- `operation_id` per collegare fattura, pagamento, banca e Prima Nota;
- payload completo e ricostruibile;
- hash del payload e provenienza;
- data di acquisizione e versione del parser.

Regole del cutover:

1. deduplicare la sorgente per identità canonica e hash;
2. bloccare ID uguali con payload differenti;
3. copiare il dataset completo nel registro Drive;
4. confrontare conteggi unici e digest sorgente/destinazione;
5. ricostruire il runtime dai fogli e provarne la scrittura;
6. configurare esplicitamente il registro e verificare la produzione;
7. confermare che non esistano variabili o percorsi di persistenza alternativi.

La memoria del processo è soltanto una cache ricostruibile: Drive/Sheets resta
sempre la sorgente persistente.

## Canali operativi e conoscenza

- Telegram è l'unico canale attivo per alert e notifiche operative.
- Non registrare router, webhook o fallback WhatsApp legacy.
- Obsidian è una proiezione consultiva della documentazione: non è un database,
  non riceve scritture contabili e non sostituisce Drive/Sheets.

## Identità, duplicati e relazioni

- Nessuna entità si associa per solo importo.
- Una relazione certa richiede identità/provenienza coerente e importo esatto
  al centesimo quando l'importo fa parte della prova.
- Nei casi ambigui mostra i candidati (`Scegli fattura`, `Scegli driver`,
  `Scegli verbale`) e non applicare il collegamento.
- Gli import sono idempotenti: stesso hash o stessa identità canonica non crea
  una seconda operazione.
- Fattura, disposizione, ricevuta, quietanza e movimento bancario sono prove
  distinte, collegate da `operation_id`, mai fuse in un solo record.
- I documenti originali restano immutabili. Conservare hash, fonte, versione,
  timestamp e log. I duplicati documentali si marcano; non si eliminano in
  modo permanente.

## Ingresso documenti e Drive

- `Documenti > Import` è l'unico ingresso manuale operativo.
- Le fatture elettroniche arrivano dal canale Drive/SDI configurato. Una
  fattura italiana trovata per email è un'anomalia, non una seconda fonte.
- Gmail/IMAP può acquisire F24, quietanze, cedolini e verbali soltanto dai
  mittenti/canali autorizzati.
- Le ricerche email complete usano `in:anywhere`, preservano message ID,
  thread ID e SHA-256 e non spostano né cancellano gli originali.
- Gli estratti conto confluiscono nell'area unica configurata; la fonte si
  determina da nome e contenuto. Se non è riconoscibile, il file va in errore
  con motivazione, mai classificato per supposizione.
- Gli ZIP vengono prima validati, deduplicati e inventariati; poi i documenti
  riconosciuti entrano nei rispettivi flussi.

## Regole contabili vincolanti

- Piano dei conti: solo CEE ufficiale in
  `app/services/piano_conti_ufficiale.py`; conversioni tramite
  `app/services/mapping_piano_conti.py`.
- Motore unico Prima Nota: `app/services/scritture_contabili.py`. Non creare
  nuovi `insert_one` diretti per scritture contabili.
- Ricavi: solo corrispettivi RT. Le fatture ricevute sono costi; gli accrediti
  POS e i payout non sono nuovi ricavi.
- POS: corrispettivo XML, chiusura terminale e accredito bancario sono tre
  fatti distinti. Numia e SumUp restano circuiti separati.
- Un versamento contanti genera uscita Cassa e corrispondente entrata Banca con
  lo stesso `operation_id`; l'estratto conto riconcilia il trasferimento.
- Prima Nota Banca non è la copia dell'estratto conto: una riga entra quando è
  nota la causale contabile oppure appartiene alle categorie bancarie senza
  documento ammesse dal codice.
- F24, singole righe tributo, quietanza e movimento bancario sono entità
  distinte. La quietanza documenta il pagamento ma non sostituisce la prova
  bancaria.
- Cedolini e bonifici salario si associano per dipendente, periodo e regole
  temporali; non si richiedono importi identici quando esistono acconti o
  trattenute.
- Date mostrate all'utente: `gg/mm/aaaa`.

## PartenoPay, verbali e flotta

- Conservare email, verbale, avviso, ricevuta PagoPA/PayPal e movimento banca
  come prove separate.
- Associazione automatica driver: targa normalizzata + data/ora infrazione +
  storico assegnazioni del veicolo.
- Se targa, driver, verbale o pagamento non sono univoci, conservare il
  documento e chiedere una scelta manuale.
- Lo stato corretto dopo un pagamento privo di ricevuta ufficiale è
  `attesa quietanza`, non `attesa fattura`.
- Nessun pagamento automatico è autorizzato.

## Sicurezza

- Segreti solo nelle variabili d'ambiente/secret store di Render.
- Non stampare, committare o trasferire credenziali nei documenti.
- Non spostare né cancellare email e documenti originali.
- Eliminazioni reali, pagamenti e associazioni definitive ambigue richiedono
  conferma esplicita al momento dell'azione.

## Verifica e pubblicazione

Per ogni modifica pertinente:

1. test mirati;
2. `python -m pytest -q` quando il cambiamento backend lo richiede;
3. `yarn test` e `yarn build` in `frontend/` quando coinvolge il frontend;
4. `git diff --check`;
5. commit dei soli file pertinenti;
6. push su `main` solo quando richiesto;
7. CI verde e verifica `/api/health` sul commit pubblicato;
8. controllo live del flusso interessato senza mutare dati non autorizzati.

Un alert deve sempre mostrare l'elenco dei record coinvolti. Un comando di
manutenzione che l'utente deve ripetere per correggere duplicati prevedibili è
un difetto: la prevenzione per ID/hash deve stare nel flusso di importazione.
