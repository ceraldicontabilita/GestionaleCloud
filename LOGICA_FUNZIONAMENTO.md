# GestionaleCloud — Logica di funzionamento

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

Questo documento descrive le regole operative correnti di Ceraldi ERP. Il
repository canonico è `ceraldicontabilita/GestionaleCloud`; codice, test e
configurazione di produzione prevalgono sui report storici.

## 1. Principio generale

Questa è una guida di lettura. La specifica normativa unica e atomica è
`PROMPT_MASTER.md`; ogni modifica di logica deve aggiornare prima il master.

Il gestionale trasforma documenti e fonti esterne in un grafo di fatti
consultabile:

```text
originale Drive/email/import
        ↓
documento indicizzato e deduplicato
        ↓
fatto di dominio (fattura, F24, verbale, cedolino, movimento...)
        ↓
relazioni certe tramite operation_id
        ↓
Prima Nota, riconciliazione, stato e prove
```

L'automazione esegue solo operazioni deterministiche. Se più candidati sono
plausibili, conserva il documento, mostra l'elenco e richiede una scelta.

La regola trasversale obbligatoria è `docs/REGOLA_FISSA_ATTESE.md`: il fatto
owner crea subito obblighi e attese; le evidenze future possono soltanto
soddisfarle o lasciarle aperte. Nessun processo è chiuso se una sua attesa
obbligatoria è ancora `ATTESO`, `DA_VERIFICARE`, `IN_ELABORAZIONE` o `ERRORE`.

## 2. Archivio Drive-only

Drive/Sheets è l'unico archivio operativo. La destinazione operativa è:

- Google Drive per documenti originali e allegati;
- Google Sheets/Excel collegato a Drive per registri strutturati;
- un foglio per entità, con progressivo stabile e identificativo canonico;
- relazioni tra entità tramite `operation_id` e ID specifici.

Il registro implementato in `app/services/google_sheets_ledger.py` usa almeno
questi fogli:

```text
Documenti                 Fatture ricevute       Fatture emesse
Fornitori                 Dipendenti             Cedolini
Estratti conto            Movimenti bancari      Prima Nota Cassa
Prima Nota Banca          Bonifici               Assegni
Corrispettivi             F24                    Quietanze F24
PayPal                    Scadenze fornitori     Relazioni
Codici tributo            Import PartenoPay      Email PartenoPay
Verbali PartenoPay
```

Sotto la radice Drive il sistema riconosce la tassonomia:

```text
REGISTRO DATI/
PARTENOPAY/
CODICI TRIBUTO/
QUIETANZE/
DICHIARAZIONI/
```

I file originali non si spostano né si eliminano automaticamente. L'indice
conserva Drive ID, percorso, origine, hash e data di acquisizione.

### Stato dell'archivio

Il default corrente in `app/config.py` è `DATA_BACKEND=sheets`. Drive/Sheets è l'unico archivio operativo e il backend supportato in produzione. Il backend storico è stato rimosso come backend operativo e non deve essere utilizzato in ambienti produttivi. Qualsiasi riferimento a `DATA_BACKEND=legacy DB`, variabili legacy DB_* o script di provisioning è deprecato e deve essere trattato come artefatto storico o strumento di migrazione isolato e controllato.

La migrazione dei dati storici è conclusa solo quando:

1. tutti i fogli richiesti esistono e sono accessibili;
2. la copia iniziale è completa e senza collisioni irrisolte;
3. lettura, inserimento, aggiornamento e ricerca funzionano su Sheets;
4. un confronto end-to-end dimostra equivalenza dei risultati;
5. è provata la ricostruzione completa partendo da Drive e registro;
6. produzione ha un registro esplicitamente configurato e i controlli
   post-deploy passano.

Il runtime non accetta configurazioni o scritture verso archivi alternativi.

## 3. Identità, hash e duplicati

Ogni riga del registro contiene almeno:

- `progressivo` stabile del foglio;
- `canonical_id` del fatto;
- `operation_id` comune ai fatti collegati;
- data, anno, tipo, importo e stato;
- ID documento, fattura e movimento bancario quando presenti;
- origine, hash file, data aggiornamento e payload completo.

La chiave di deduplicazione dipende dal dominio:

- documenti: hash del contenuto più ID esterno/provenienza;
- fatture: identificativo SDI o chiave emittente-numero-data-tipo;
- movimenti bancari: ID estratto/CRO-TRN, conto, data, importo e descrizione
  normalizzata;
- PayPal/SumUp: ID transazione del gestore;
- F24/quietanze: identificativo documento, periodo, delega e hash;
- verbali: numero normalizzato, ente, targa, data/ora e hash.

Stesso importo non significa stessa operazione. Le ricorrenze legittime
(canoni, assegni, rate, bonifici periodici) restano record distinti.

L'import calcola prima la chiave. Se esiste, aggiorna provenienza o metadati;
non inserisce una seconda scrittura. Eventuali duplicati storici certi vengono
nascosti/accorpati automaticamente con audit, mentre i casi dubbi restano in
una lista visibile.

## 4. Import documenti

Le fonti ammesse sono upload manuale, cartelle Drive configurate, email e API
dei gestori. Ogni ingest segue lo stesso contratto:

1. conserva l'originale;
2. calcola hash e identità;
3. verifica se il documento è già indicizzato;
4. estrae dati e registra la provenienza;
5. crea o aggiorna il fatto di dominio;
6. collega automaticamente solo le corrispondenze certe;
7. espone gli ambigui come candidati selezionabili;
8. restituisce un riepilogo con inseriti, aggiornati, duplicati e scartati.

Il comando di import deve sempre salvare; una modalità di sola anteprima deve
essere esplicitamente etichettata come simulazione.

## 5. Fatture e fornitori

- Le fatture ricevute derivano dagli XML e conservano documento, fornitore,
  imponibile, IVA, totale, scadenza e metodo previsto.
- Il fornitore canonico è identificato prima dalla P.IVA/codice fiscale e poi
  da alias normalizzati; il nome da solo non crea duplicati.
- Una fattura risulta pagata solo quando esiste una prova collegata.
- Dalla pagina fatture è possibile correggere l'imputazione tra Cassa e Banca
  senza cercare manualmente la scrittura nella Prima Nota.
- Se la banca contiene un riferimento stabile (SDD, PayPal, CRO/TRN), la regola
  del fornitore può usarlo nei successivi abbinamenti.
- Un'associazione incerta presenta `Scegli fattura`; non viene salvata come
  definitiva.

## 6. Prima Nota Cassa e Banca

Le due sezioni mostrano movimenti raggruppati per giorno, con totale della
giornata e link alle prove.

### Versamento contanti

Un versamento genera una sola operazione logica con due lati:

```text
Prima Nota Cassa: uscita "Versamento in banca"
Prima Nota Banca: entrata attesa "Versamento da Cassa"
```

Le due righe condividono `operation_id`. Quando il movimento compare
nell'estratto conto, l'entrata attesa viene riconciliata: non viene creata una
terza registrazione. Il fatto owner è il versamento registrato in Cassa; se la
banca arriva senza quell'attesa resta `DA_VERIFICARE` e non inventa il
versamento mancante.

### POS e SumUp

- Le vendite POS appartengono al giorno delle transazioni.
- SumUp corrente arriva automaticamente dall'API ufficiale: le transazioni
  sono deduplicate per ID, aggregate per giorno e creano il credito bancario
  atteso verso SumUp.
- Numia corrente non arriva da API: l'operatore inserisce la chiusura dei
  terminali ogni sera e quel totale crea il credito bancario atteso Numia.
- Per il pregresso Numia, gli export operativi CSV/XLSX nella cartella Drive
  dedicata sono deduplicati per ID transazione e accorpati per giorno vendita;
  il totale di ogni giorno diventa l'attesa bancaria Numia. Non sono estratti
  conto bancari.
- L'accredito bancario è un fatto successivo e separato.
- In Banca si mostra l'importo atteso finché non arriva il movimento effettivo.
- Commissioni e scostamenti restano componenti identificabili.
- L'accredito riconcilia gli attesi tramite ID del gestore e composizione del
  lotto; non sostituisce o duplica i corrispettivi.
- Numia accorpa per giorno vendita letto da `DEL gg/mm/aa` le componenti
  `AMEX`, `INTER`, `BNCMT` e `PGBNT`; commissioni, fatture gestore e spese carta
  restano escluse. Senza una sola attesa terminale la banca non crea il POS.

### Estratto conto

Al caricamento il sistema:

1. deduplica le righe prima di scriverle;
2. importa i nuovi movimenti mantenendo la provenienza;
3. riconcilia versamenti, POS, bonifici, assegni, SDD e pagamenti certi;
4. marca pagate le fatture solo con prova coerente;
5. lascia in elenco gli abbinamenti ambigui;
6. produce un resoconto navigabile dei risultati.

La coerenza tra corrispettivi RT, chiusure POS, accrediti dei gestori e
movimenti bancari è esposta nella pagina dedicata alla Coerenza POS del
catalogo, mentre Prima Nota Cassa/Banca conserva le scritture contabili
distinte e collegate.

## 7. PayPal, bonifici e assegni

- Una transazione PayPal mantiene il proprio ID e può collegarsi sia alla
  fattura sia al movimento bancario SDD; le tre viste condividono
  `operation_id`.
- Le regole note del beneficiario o del riferimento bancario valgono per tutti
  i movimenti futuri, ma non superano un conflitto di identità.
- I bonifici ai dipendenti prima del giorno 25 sono normalmente riferiti al
  cedolino del mese precedente; dal giorno 25 possono riferirsi al mese
  corrente. La regola propone il periodo e salva la scelta, senza inventare un
  cedolino non ancora disponibile.
- Gli assegni ricorrenti con importo uguale ma numero/data differenti non sono
  duplicati.

## 8. Corrispettivi

ZIP e singoli file importati vengono indicizzati, deduplicati e caricati nella
Prima Nota Cassa. La data del corrispettivo determina la giornata; totale
giornaliero, contanti, elettronico e scostamenti devono essere verificabili
contro POS e accrediti.

## 9. F24, quietanze e codici tributo

F24, quietanza e movimento bancario sono tre prove distinte:

```text
modello F24 → righe/codici tributo
quietanza   → prova documentale dell'esecuzione
banca       → prova finanziaria dell'addebito
```

La pagina F24 mostra tutti i modelli presenti in Drive/import/email, i codici
tributo, il periodo, i PDF collegati e lo stato di riconciliazione. La ricerca
per codice tributo risale all'F24 e al PDF. Un F24 non deve risultare pagato
solo perché esiste una quietanza scollegata o un movimento dello stesso
importo.

## 10. Cedolini e personale

- Cedolini e bonifici restano archivi distinti e collegabili.
- Il periodo associato è persistente e visibile dopo il refresh.
- Descrizioni e note operative spiegano pagamenti effettuati con carta o da un
  socio quando la sola causale non basta.
- Le associazioni automatiche richiedono dipendente, periodo e importo
  compatibili; i conflitti restano manuali.

## 11. PartenoPay, verbali, veicoli e driver

- La ricerca email usa l'intera casella (`in:anywhere`) e conserva Gmail ID,
  hash, allegati e provenienza.
- I documenti PartenoPay sono archiviati in Drive e indicizzati nei fogli
  dedicati.
- Il PDF del verbale è la fonte per numero, importo, targa, data/ora, ente,
  trasgressore e stato; l'importo non si deduce dal nome file.
- Lo stato documentale dopo il pagamento è `Attesa quietanza` finché la prova
  non è collegata.
- Targa e driver si associano automaticamente solo quando fattura/contratto e
  storico assegnazioni determinano un unico conducente alla data del verbale.
- Se il trasgressore è Ceraldi Group S.r.l. viene mostrato come tale, senza
  inventare un driver.
- Le schede veicolo vengono compilate dai dati di fatture e contratti; una
  scheda incompleta non va mostrata come veicolo operativo.
- L'assenza apparente di fatture recenti è un alert solo dopo la scansione di
  tutte le fonti configurate.

## 12. Relazioni e navigazione

Il registro `Relazioni` descrive i collegamenti tra entità. Ogni vista deve
consentire di passare, quando disponibili, tra:

```text
documento ↔ fattura ↔ pagamento gestore ↔ movimento bancario
          ↔ Prima Nota ↔ quietanza/prova
```

Un link mostra sempre tipo, ID, data, importo e origine della destinazione.

## 13. Fonti dati per area

Questa sezione riassume da dove il sistema prende i dati per ogni area
funzionale. Le sorgenti sono sempre le stesse: Drive, email autorizzate,
upload manuali e API dei gestori. Registri e relazioni risiedono in Sheets;
gli originali risiedono in Drive.

| Area | Fonti | Dato operativo risultante |
|---|---|---|
| Documenti | cartelle Drive configurate, email autorizzate, upload manuale, API dei gestori | documento indicizzato con hash, origine e classe dominio |
| Fatture ricevute | XML/P7M da Drive/SDI, anagrafiche fornitore, mapping alias | fattura con fornitore canonico, importo, scadenza e stato |
| Fornitori | fatture, documenti ricevuti, alias normalizzati e anagrafiche già presenti | fornitore univoco per P.IVA/codice fiscale |
| Prima Nota Cassa/Banca | fatture, corrispettivi RT, movimenti bancari, versamenti contanti, POS, cedolini, F24 | scritture distinte collegate da `operation_id` |
| Estratti conto | file banca importati, movimenti con CRO/TRN o descrizioni normalizzate | movimenti bancari deduplicati e riconciliati |
| F24 e quietanze | modelli F24, codici tributo, quietanze PDF e movimenti bancari | delega, riga tributo, quietanza e addebito restano entità separate |
| Corrispettivi e POS | XML RT, chiusure terminale, accrediti gestore, commissioni | ricavo RT e accredito POS separati, con riconciliazione finale |
| Cedolini | file paga, anagrafiche dipendenti, bonifici salario | cedolino collegato al dipendente e al periodo corretto |
| PartenoPay e verbali | email autorizzate, ZIP, verbali PDF, ricevute e storico assegnazioni veicolo | verbale collegato a targa, driver e pagamento quando univoci |
| Amministrazione e audit | configurazione, inventory, log, report storici e test | tracciabilità e verifica, non scrittura dei fatti di dominio |

La logica resta idempotente: lo stesso hash o la stessa identità canonica non
deve generare una seconda operazione. Quando l'oggetto non è certo, il sistema
espone i candidati e chiede una scelta manuale.
Modificare una relazione aggiorna tutte le viste che la leggono; non crea copie
locali scollegate.

## 14. Alert e azioni utente

- Ogni numero di anomalie è cliccabile e apre la lista completa.
- Gli errori certi e recuperabili vengono corretti dal sistema durante
  l'import o da una migrazione controllata.
- La manutenzione tecnica non deve diventare una sequenza quotidiana di
  pulsanti.
- Gli ambigui restano visibili con motivazione e candidati.
- Nessuna associazione ambigua, pagamento, eliminazione o spostamento di
  originale avviene automaticamente.

## 15. Accesso, audit e sicurezza

- Autenticazione e autorizzazione proteggono tutti gli endpoint riservati.
- La sessione è scorrevole e scade dopo il periodo d'inattività configurato.
- Segreti e ID privati vivono nelle variabili Render, mai nei documenti o nel
  codice.
- Import, associazioni, correzioni e migrazioni registrano autore, momento,
  origine e risultato.
- Le automazioni periodiche usano lock/lease per evitare esecuzioni concorrenti.

## 16. Verifica end-to-end

Un flusso è completato soltanto se sono provati:

1. acquisizione dell'originale;
2. persistenza dopo refresh e riavvio;
3. deduplicazione al secondo import;
4. correttezza degli importi al centesimo;
5. visibilità in tutte le sezioni collegate;
6. link bidirezionali e stesso `operation_id`;
7. comportamento sicuro sui casi ambigui;
8. test backend, test/build frontend, CI e verifica live post-deploy.

Un HTTP 200 o una pagina che si apre non dimostrano la correttezza dei dati.

## 17. Documenti di riferimento

- `README.md`: avvio, architettura e deploy.
- `PRODUCT.md`: obiettivi e albero funzionale.
- `CLAUDE.md`: regole vincolanti per le modifiche.
- `DESIGN.md`: sistema visivo e comportamento UI.
- `docs/MARKDOWN_INVENTORY.md`: stato di tutti i documenti Markdown.
- `memoria/INDEX.md`: indice tecnico rapido.
- `memoria/DISASTER_RECOVERY_DRIVE.md`: ripristino dell'archivio Drive-only.
