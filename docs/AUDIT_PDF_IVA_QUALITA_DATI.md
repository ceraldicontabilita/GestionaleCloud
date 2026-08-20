# Audit PDF, IVA e qualità dei dati

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Scopo

Questa guida descrive il collaudo end-to-end dei documenti contabili, i controlli introdotti e il flusso operativo da usare per nuove importazioni. Non contiene nomi, importi di dettaglio, credenziali o copie dei documenti aziendali.

## Perimetro verificato

- 26 radici Google Drive indicate dall'utente.
- 13.702 file censiti, di cui 10.326 PDF per circa 1,60 GB.
- 4.330 contenuti PDF unici per hash, su 9.874 pagine.
- 4.276 PDF con testo nativo e 48 documenti sottoposti a OCR.
- 47 OCR riusciti, un OCR da revisione e sei file tecnicamente non leggibili.
- Fatture passive, estratti conto, assegni, cedolini, bonifici, F24, quietanze, corrispettivi e liquidazioni IVA.

I file originali restano la fonte probatoria. Le copie presenti in cartelle diverse possono rappresentare fasi di lavorazione e non vengono cancellate solo perché hanno lo stesso hash.

## Risultati principali

### Duplicati documentali

Sono stati individuati 1.903 gruppi di copie identiche nella stessa cartella, equivalenti a 2.530 copie eccedenti. La rimozione non è stata eseguita perché l'identità Drive utilizzata per l'audit ha accesso in lettura ma non può spostare nel cestino. Il piano di pulizia resta disponibile nell'area audit locale e dovrà essere applicato soltanto dopo una nuova autorizzazione Drive con permessi di scrittura.

### IVA

È stato eliminato il fallback che trasformava automaticamente l'IVA esposta in fattura in IVA interamente detraibile. Ora:

1. `iva_documento` conserva l'imposta indicata nel documento;
2. `iva_detraibile` contiene solo un valore classificato esplicitamente;
3. una fattura priva di classificazione resta `DA_VERIFICARE`;
4. soltanto gli stati ammessi e con IVA detraibile positiva entrano nella liquidazione;
5. dashboard, bilancio, finanziaria, scadenze, piano dei conti, report, export del commercialista e liquidazioni usano soltanto l'IVA detraibile classificata;
6. la registrazione in partita doppia si ferma in `da_verificare` se una fattura con IVA non ha ancora una classificazione esplicita.

Il ricalcolo controllato ha aggiornato 1.567 fatture: 180 risultano pronte per l'inserimento e 1.387 restano da verificare. L'IVA detraibile complessiva classificata non è stata aumentata dal ricalcolo.

Al collaudo finale del 5 agosto 2026 restano 1.358 fatture `DA_VERIFICARE`. Non risultano IVA detraibili negative, superiori all'IVA del documento o stati operativi privi dell'importo esplicito. Le 1.358 posizioni non sono errori di calcolo: sono decisioni di detraibilità che devono essere supportate dalla fattura e dalla relativa natura fiscale.

### F24 e quietanze

Su 788 PDF fiscali unici:

- 48 F24 e 130 quietanze hanno superato il parser con tributi o importi verificabili;
- 610 documenti sono rimasti fuori dall'import contabile e richiedono revisione;
- tutti i 178 documenti validi sono transitati da `documents_inbox`;
- 48 F24 sono stati salvati in `f24_unificato` con hash e chiave idempotente;
- 130 quietanze sono state salvate in `quietanze_f24`;
- due quietanze hanno trovato un collegamento certo con un F24; le altre sono conservate come prove non associate e generano un alert.

Il matching richiede corrispondenza di codici, periodo e importi entro la tolleranza prevista. Non viene creato un modello F24 a partire dalla sola quietanza.

### Cedolini e bonifici

La chiave canonica dei cedolini ora distingue documenti diversi dello stesso dipendente e mese usando tipo documento, datore di lavoro e hash o firma economico-lavorativa. Un secondo cedolino reale nello stesso periodo non viene più eliminato come duplicato.

La coda controllata ha elaborato 1.029 PDF senza errori. Lo stato finale contiene 1.316 cedolini e 1.316 righe di prima nota salari: non risultano chiavi duplicate, collegamenti a cedolini inesistenti o salari riconciliati senza prova bancaria. I 287 record storici non condividono periodo, dipendente o filename con i 1.029 nuovi documenti e sono stati conservati.

I bonifici sono importati per hash e associati a salari o altre entità solo quando il motore restituisce un match certo. Gli esiti incompleti restano da verificare.

### Banca e assegni

Il collaudo controlla:

- movimenti di estratto conto mancanti, riutilizzati o duplicati;
- fatture segnate pagate senza prova bancaria;
- assegni incassati senza beneficiario, fattura o movimento bancario valido;
- stipendi riconciliati senza bonifico;
- coerenza POS tra chiusura manuale, corrispettivi XML e accredito banca.

Gli importi simili, da soli, non autorizzano alcun collegamento.

Il controllo di produzione ha inoltre separato due casi prima confusi dallo stesso contatore:

- 23 righe generiche di prima nota duplicavano altrettante righe già collegate alla fattura; sono state messe in stato cancellato logico, conservando la riga probatoria e quindi la possibilità di recupero;
- quattro movimenti erano pagamenti cumulativi validi su più fatture: ogni quota è collegata a una fattura diversa e la somma coincide al centesimo con l'unico movimento di estratto conto; sono stati correttamente conservati.

Dopo la pulizia risultano zero collegamenti a movimenti bancari inesistenti, zero duplicazioni bancarie attive e zero fatture pagate con movimento cancellato.

## Controlli automatici

Il job `collaudo_invarianti` è già pianificato ogni notte alle 04:30. Salva un report in `collaudo_report`, apre o aggiorna alert idempotenti e chiude l'alert quando la regola torna pulita. Il controllo è di sola lettura e non corregge dati in silenzio.

È stata aggiunta la regola `fatture_iva_classificazione`, che segnala:

- IVA detraibile negativa;
- IVA detraibile superiore all'IVA del documento;
- fatture operative senza valore detraibile esplicito;
- fatture ancora in stato `DA_VERIFICARE`.

## Flusso operativo obbligatorio

```text
Drive / email / upload
        ↓ hash e provenienza
documents_inbox
        ↓ parser specifico
entità canonica
        ↓ matching certo
relazioni e prima nota
        ↓
collaudo notturno + alert + report
```

Regole:

1. `Documenti` è l'unico punto d'ingresso.
2. Conservare hash, sorgente, identificativo Drive e data d'importazione.
3. Non creare relazioni basate soltanto sull'importo.
4. Non cancellare un originale senza certezza e possibilità di recupero.
5. Gli errori del parser restano visibili nello stato dedicato.
6. Ogni ricalcolo massivo richiede simulazione, manifest e verifica indipendente.

## Collaudo e comandi

Test backend mirati:

```powershell
python -m pytest tests/test_collaudo_invarianti.py tests/test_iva_fatture.py tests/test_liquidazione_iva_engine.py tests/test_p0_08_f24_parser_contract.py tests/test_p1_cedolini.py -q
```

Build frontend:

```powershell
cd frontend
npm.cmd run build
```

Il bundle locale `frontend/dist` non va pubblicato: Render compila il frontend dalla sorgente.

Esito dell'ultima suite completa: 990 test superati, due saltati e nessun errore. Gli avvisi residui riguardano principalmente API `datetime.utcnow()` deprecate e non modificano l'esito funzionale.

Esito del collaudo di produzione `collaudo-20260805-040824`: 15 controlli eseguiti, nessun controllo in errore, 12 controlli completamente puliti e tre aree aperte esclusivamente per verifica documentale o riconciliazione assistita.

## Limiti e rischi residui

- La pulizia delle copie Drive è bloccata finché non viene concessa l'autorizzazione in scrittura.
- I 610 PDF fiscali non riconosciuti richiedono un parser aggiuntivo o verifica manuale.
- Le 1.358 fatture con detraibilità non classificata non producono credito IVA finché non vengono confermate.
- Le quietanze senza F24 corrispondente provano il pagamento, ma non autorizzano la ricostruzione dei dettagli del modello.
- Le differenze fra totale fattura, imponibile e IVA possono includere ritenute, bollo, cassa previdenziale o arrotondamenti e non sono corrette automaticamente.
- I collegamenti banca risultano ora puliti. Restano 65 giornate con scostamento POS/XML/banca da verificare sulle chiusure e sugli accrediti effettivi.
- I 294 rilievi sugli assegni corrispondono a 147 assegni che presentano due dati mancanti ciascuno: beneficiario e fattura collegata. Non vengono completati per supposizione.

## Recovery

Manifest, inventari, database OCR e backup delle operazioni massive sono conservati nell'area audit privata locale, fuori dal repository. Non devono essere pubblicati perché possono contenere riferimenti a documenti aziendali.
