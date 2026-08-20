# Audit ingegneristico estremo — GestionaleCloud

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data: 8 agosto 2026
Repository canonico: `ceraldicontabilita/GestionaleCloud`
Base verificata: `main` commit `656e08c5705d220891d47b77853eaee94291055c`

## Verdetto

**REQUEST CHANGES.** La codebase e' ampia e dispone di molti test, ma prima
dell'audit non rispettava ancora un livello enterprise per scritture contabili
atomiche, bootstrap senza effetti collaterali, osservabilita' e scalabilita'
orizzontale. I P0 individuati nel perimetro toccato sono stati corretti e
coperti da test; il debito storico quantificato sotto non va nascosto e richiede
una bonifica progressiva per dominio.

Un HTTP 200 o una pagina che si apre **non** costituiscono collaudo. Una funzione
e' approvata soltanto quando route, schema, autorizzazione, servizio, query,
indice, idempotenza, audit, test e comportamento live concordano.

## Evidenza quantitativa riproducibile

Comando: `python scripts/audit_architettura.py`

| Metrica | Valore | Valutazione |
|---|---:|---|
| File Python | 489 | codebase molto ampia |
| File router | 159 | frammentazione elevata |
| Route rilevate staticamente | 970 | superficie API eccessiva |
| Mutazioni | 505 | perimetro di rischio alto |
| Route senza `response_model` esplicito | 965 | P1 |
| Mutazioni senza status code esplicito | 494 | P1 |
| Hard delete rilevati | 132 | P0/P1 secondo il dominio |
| Letture `.to_list(10000+)` | 189 | P1 performance/memoria |
| Handler che silenziano eccezioni | 110 | P1 osservabilita' |
| Registrazioni runtime FastAPI | 1.076 | inventario reale |
| Duplicati esatti metodo+path | 0 | conforme |

I moduli piu' critici per dimensione sono `prima_nota_module/sync.py` (3.668
righe), `bank/assegni.py` (3.218), `invoices/fatture_upload.py` (2.646),
`documenti.py` (2.637), `prima_nota_module/manutenzione.py` (2.540) ed
`bank/estratto_conto.py` (2.289). Sono controller monolitici: rendono troppo
facile modificare un flusso senza aggiornare gli altri.

## P0 corretti in questo intervento

### 1. Bootstrap con mutazioni contabili

Problema: riavviare una replica poteva eseguire riparazioni dati, seed e
creazione sequenziale di indici. Con due worker la stessa attivita' poteva
partire due volte.

Correzione:

- `RUN_STARTUP_DATA_REPAIRS=false` per default;
- `RUN_STARTUP_INDEX_MIGRATIONS=false` per default;
- `RUN_STARTUP_SEED_DATA=false` per default;
- indici provisionati solo con `scripts/provision_mongodb.py`;
- scheduler protetto da lease Mongo distribuito e heartbeat.

Motivo: il lifecycle web deve inizializzare il processo, non migrare dati
contabili. Deploy e migrazioni hanno autorizzazioni, rollback e audit diversi.

### 2. Health check falso positivo

Problema: la connessione Mongo poteva fallire senza interrompere il processo e
`/api/health` continuava a dichiarare il servizio sano.

Correzione: connessione fail-closed, ping reale e HTTP 503 se Mongo e'
disconnesso o irraggiungibile.

### 3. CORS pericoloso

Problema: wildcard con credenziali permetteva una configurazione cross-site non
controllata.

Correzione: senza origin espliciti, con cookie/credenziali, la lista cross-site
e' vuota. Same-origin continua a funzionare.

### 4. Segreto JWT con I/O sincrono all'import

Problema: `Settings.__init__` apriva un client PyMongo sincrono, poteva bloccare
quattro secondi ogni import/worker, scriveva su Mongo e sovrascriveva perfino un
`SECRET_KEY` esplicito.

Correzione: `app/services/auth_secret.py` inizializza la chiave in modo async
dopo il pool Mongo. Una chiave esplicita e' autoritativa; in sua assenza le
repliche convergono sul documento Mongo `_id=auth_secret`. Render usa
`FAIL_FAST_SECRETS=true`.

### 5. Pagamento fattura non atomico e non idempotente

Problema: movimento Prima Nota, scadenza e fattura erano aggiornati con write
separate. Un timeout intermedio lasciava una fattura pagata senza movimento o
un retry poteva sommare l'importo due volte.

Correzione: `app/services/invoice_payments.py` usa:

- schema Pydantic `extra=forbid`;
- importo finito e non zero;
- metodo ristretto a `cassa|banca`;
- data ISO;
- transazione Mongo multi-documento;
- chiave idempotente in `pagamenti_operazioni._id`;
- replay senza doppia scrittura;
- rifiuto del sovrapagamento rispetto al residuo corrente;
- rifiuto dei parziali senza `scadenza_id` o chiave idempotente stabile;
- conservazione dei riferimenti Cassa e Banca nei pagamenti parziali misti;
- HTTP 201 e response model esplicito.

### 6. Riconciliazione fattura-banca permissiva

Problema: il vecchio endpoint accettava qualunque `fattura_id` e
`movimento_id`, poi marcava tutto pagato senza verificare importo, numero o un
collegamento precedente.

Correzione: il percorso uno-a-uno ora richiede:

- importo identico al centesimo;
- numero fattura presente nella causale normalizzata;
- movimento non assegnato a un'altra fattura;
- transazione atomica su fattura, estratto, Prima Nota e audit;
- motivazione esplicita e registrata per un override manuale.

I bonifici cumulativi non devono forzare questo endpoint: passano dal motore
multi-fattura, dove la somma delle quote deve coincidere al centesimo.

### 7. POS Numia/SumUp

Invariante implementata:

```text
XML RT                  = prova fiscale del corrispettivo totale
POS Numia reale         = chiusura terminale/manuale o somma accrediti BPM
POS SumUp reale         = transazioni API PAYMENT+SUCCESSFUL
accredito/payout        = prova finanziaria, mai nuovo ricavo
commissione             = costo separato per circuito
```

La bonifica Numia e' idempotente e atomica. Le righe individuali BPM sono
componenti/evidenze del gruppo giornaliero, non ricavi o rimborsi autonomi. I
circuiti non vengono mai accorpati.

## Routing e controller

### Stato

- Nessun duplicato esatto metodo+path tra le 1.076 route montate.
- L'ordine statico/dinamico del modulo fatture e' corretto.
- La superficie e' comunque troppo grande e molte funzioni controller
  contengono query, regole contabili e serializzazione insieme.

### Architettura target obbligatoria

```text
Router FastAPI
  -> Request/Response Pydantic
  -> Application Service (caso d'uso)
  -> Unit of Work Mongo (transazione/idempotenza)
  -> Repository (query indicizzate, projection, cursor pagination)
  -> Domain events/outbox dopo commit
```

Il router deve solo tradurre HTTP. Non deve conoscere nomi di collection, fare
aggregazioni o coordinare tre write.

## Contratto REST

Regole per ogni nuovo endpoint e per ogni endpoint modificato:

- sostantivi plurali e URL stabili;
- `GET` senza side effect;
- `POST` create = 201, comandi sincroni = 200;
- `DELETE` riuscita = 204, oppure soft-delete con risorsa auditata;
- 400 sintassi/operazione, 401 identita', 403 ruolo, 404 assenza, 409
  conflitto/invariante, 422 schema, 429 limite, 503 dipendenza;
- `response_model` obbligatorio;
- `extra=forbid`, limiti di lunghezza, enum e validatori;
- niente eccezioni interne o stringhe Mongo restituite al client;
- `Idempotency-Key` obbligatoria per import, pagamenti e riconciliazioni.

## MongoDB

### Pool e resilienza

Il client ora usa un singleton Motor con pool elastico `minPoolSize=0`,
`maxPoolSize=50`, timeout di selezione/connessione/coda, max idle, retry read e
retry write. Questo evita 10 socket permanenti per ogni worker e limita il
backpressure quando Atlas e' saturo.

### Indici

Gli indici non vengono piu' creati durante il deploy web. Lo script di
provisioning e' strict: un errore non viene piu' chiamato “indice gia'
esistente”. Prima della promozione di una nuova query va eseguito `explain`
contro dati rappresentativi e verificato che non compaia `COLLSCAN`.

Indici minimi per i flussi critici:

```javascript
db.invoices.createIndex({ invoice_key: 1 }, { unique: true, sparse: true })
db.invoices.createIndex({ supplier_vat: 1, invoice_date: -1 })
db.estratto_conto_movimenti.createIndex({ id: 1 }, { unique: true })
db.estratto_conto_movimenti.createIndex({ data: -1, importo: 1, riconciliato: 1 })
db.prima_nota_banca.createIndex({ payment_operation_id: 1 }, { unique: true, sparse: true })
db.prima_nota_cassa.createIndex({ payment_operation_id: 1 }, { unique: true, sparse: true })
db.sumup_transactions.createIndex({ chiave: 1 }, { unique: true })
```

### Injection

Mai accettare operatori Mongo dal JSON client. Filtri ammessi vanno costruiti
da campi Pydantic/enum e valori scalari. Query di ricerca testuale devono usare
`re.escape`; sort e projection devono essere whitelist. Un payload contenente
chiavi che iniziano con `$` o includono `.` deve essere respinto.

## Resilienza e performance

Rischi storici ancora aperti e misurati:

1. **132 hard delete:** ogni delete operativo va classificato. Documenti,
   fatture, F24, cedolini, assegni, riconciliazioni e Prima Nota devono usare
   soft-delete + audit + eventuale purge separato.
2. **189 letture massive:** sostituire `to_list(10000+)` con cursor pagination,
   projection e aggregazioni server-side. Mai caricare un anno intero per poi
   filtrarlo in Python.
3. **110 eccezioni silenziate:** almeno log strutturato, correlation ID, stato
   degradato e contatore. Nei writer, l'errore deve fare rollback.
4. **Controller giganti:** estrazione progressiva per dominio, iniziando da
   assegni, import fatture, estratto conto e Prima Nota.
5. **Outbox:** eventi e notifiche oggi sono spesso best-effort dopo la write.
   Gli eventi contabili necessari vanno salvati nella stessa transazione e
   pubblicati da un worker idempotente.

## Gate di rilascio

Una modifica puo' arrivare su `main` solo se:

1. nessun file utente o artefatto `frontend/dist` entra per errore nel commit;
2. `git diff --check` e inventario route sono puliti;
3. test mirati delle invarianti contabili passano;
4. suite backend completa passa;
5. suite frontend completa passa;
6. build frontend passa;
7. health Render torna 200 con ping Mongo reale;
8. collaudo live e' solo lettura e verifica dati reali senza modificarli;
9. una migrazione dati richiede dry-run, conteggi pre/post, backup, audit e
   autorizzazione distinta dal deploy.

## Esito dei gate automatici

- Backend: `1.591 passed`, `0 failed`.
- Frontend: `26` file di test, `153 passed`, `0 failed`.
- Build Vite di produzione: completata, `3.077` moduli trasformati.
- Audit statico: `0` errori di parsing e `0` duplicati runtime metodo+path.
- Artefatti generati: `frontend/dist` ripristinato, nessun file di build nel diff.

Gli avvisi residui sono deprecazioni gia' censite (lxml, `datetime.utcnow`,
Pydantic/FastAPI e tooling Vite); non hanno reso rossa la suite, ma fanno parte
del debito P1 e non sono considerati risolti da questo rilascio.

## Priorita' successiva

1. Eliminare hard delete dai domini contabili.
2. Paginare le 20 query piu' costose e misurarle con profiler Atlas.
3. Portare response model/status espliciti sui 100 endpoint realmente usati,
   poi rimuovere gli endpoint senza consumer confermato.
4. Spezzare i sei controller maggiori in servizi e repository.
5. Aggiungere outbox e correlation ID end-to-end.

Questo documento non certifica che tutte le 970 route storiche siano corrette:
certifica quali difetti sono stati misurati, quali P0 sono stati corretti e quali
gate impediscono di dichiarare affidabile una funzione senza prova.
