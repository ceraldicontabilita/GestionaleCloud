# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-19
storage_architecture: supabase
-->

Aggiornato il 19/09/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

**Questo file e `README.md` sono gli unici due documenti del repository.**
Per decisione del titolare i 116 `.md` sparsi in `docs/`, `memoria/`,
`.github/` e nei frontend sono stati cancellati e le regole ancora valide
sono confluite qui: audit, mappe generate, changelog e diari raccontavano
com'erano le cose in una certa data e rendevano impossibile capire quali
logiche fossero davvero in vigore.

## Come si tiene questo file

- Qui stanno **regole, architettura e stato attuale**. La cronaca di una
  sessione (cosa si è trovato, i numeri del giorno, le PR) **non si scrive**:
  sta nella storia di git, dove nessuno la confonde con una regola.
- «Stato attuale» e «Aperto» **si riscrivono sul posto**: un fatto superato si
  sostituisce, non gli si affianca la correzione. Una voce chiusa si toglie.
- Una regola nuova nata da un incidente entra nella sezione giusta, in una o
  due righe, senza il racconto di come ci si è arrivati.
- Non creare altri `.md`, né cartelle di documentazione, né report generati da
  script. `tests/runtime/test_claude_md.py` fa rispettare tetto di righe, data
  dell'intestazione, divieto di capitoli datati e divieto di nuovi `.md`.
- Il codice, i test e la configurazione live vincono sempre su questo file.
  Se trovi una contraddizione, **correggi questo file** nello stesso commit.

## Il gruppo Ceraldi è un solo servizio

Un unico servizio Render (`gestionalecloud.onrender.com`, deploy automatico da
`main`, health check `/api/health`) e un unico progetto Supabase servono tutto:

| Cosa | Dove vive | Codice |
| --- | --- | --- |
| ERP / contabilità | `/` | `app/` + `frontend/` |
| HR, portale dipendenti | `/hr`, `/hr/portale` | `app/hr/` + `frontend_hr/` |
| Menu pubblico e admin | `/menu`, `/menu/admin` | `app/menu/` + `frontend_menu/` |
| Lotti (HACCP) | `/lotti` | `app/lotti/` + `frontend_lotti/` |

- Repository: `https://github.com/ceraldicontabilita/GestionaleCloud`.
  Checkout canonico Windows: `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`.
- **L'unico repository vivo è questo.** `AppDipendenti`, `Lotti` e `Menu`
  restano come archivio del sorgente originale e non vengono più deployati;
  `Gestionale` era una riscrittura parallela abbandonata.
- **Siti spenti, da non riaprire né citare**: `appdipendenti.onrender.com`,
  `lotti-frontend.onrender.com`, `lotti-backend-2wwb.onrender.com`,
  `www.ceraldiapp.it`, `impresasemplice.online`. Ogni riferimento residuo è una
  voce CORS o un refuso. Restano da chiudere a mano, quando il titolare vuole:
  il DNS di `ceraldiapp.it` presso il registrar e i servizi Render sospesi.
- Prima di intervenire confronta sempre `HEAD` con `origin/main`. Il worktree
  può contenere modifiche dell'utente: non cancellarle, non ripristinarle e
  non includerle nei commit. **Mai `git add -A`**: solo i file pertinenti.

## Direttive permanenti del titolare

Valgono su tutte e quattro le app, sempre, anche quando non sono ripetute nel
resto del file.

### Metodo
- Rispondere e ragionare **in italiano**, risultati prima delle spiegazioni.
- **Tutto va portato su `main`**: si sviluppa su un branch, ma il lavoro non è
  consegnato finché non è unito su `main` e deployato. Render pubblica solo da `main`.
- Le funzionalità **si collaudano davvero** (dati di prova reali sul backend
  live, poi ripuliti), non si dichiarano a posto leggendo il codice. Se il
  titolare mostra uno screenshot con il bug ancora presente dopo un fix, il fix
  non ha coperto quel caso: si indaga da zero sui dati reali.
- Non dichiarare completato un flusso basandoti su HTTP 200, build o presenza
  della pagina. Verifica dati, relazioni, deduplica e risultato live.
- Se un problema non si risolve subito, **cercare come lo risolvono altri
  progetti reali** e integrare la soluzione, invece di descrivere il problema.
- Se trovi errori, **correggili**: non limitarti a segnalarli.
- Esponi il risultato e gli eventuali blocchi, non una sequenza di pulsanti
  tecnici da premere.
- Chiudere ogni sessione con il link di produzione:
  **https://gestionalecloud.onrender.com**

### Dati e prestazioni
- **Niente doppioni, codice morto o sistemi paralleli: un solo sistema per
  funzione.** Quando ne compare un secondo, si elimina, non si affianca.
- **Non inventare numeri.** Importi tabellari (CCNL, prezzi, aliquote) vanno
  presi dalla fonte o dichiarati da verificare. Se manca il dato: campo vuoto e
  segnalazione, mai un valore plausibile.
- I dati già letti **si tengono in memoria**: ogni rilettura inutile di
  Supabase o Drive è un costo.

### Credenziali
- Token, PIN, password e chiavi **solo nelle variabili d'ambiente di Render**
  (`render.yaml` le dichiara con `sync: false`). Mai nel codice, mai nei file
  di memoria, mai in chat, nemmeno mascherati.
- Per le azioni live che richiedono il PIN, usarlo inline in un singolo
  comando e non scriverlo su disco.
- Ogni variabile nuova richiede descrizione, default sicuro, proprietario,
  rotazione se segreta, e va tolta quando non ha più consumatori.

### Design (vale per HR, Menu e Lotti; l'ERP ha il suo layout)
- Salvia `#5b7a6b` (scuro `#3f5a4e`) su crema `#faf7f0`; card `#fffefb`,
  bordi sabbia `#e6e0d4`, inchiostro `#2a3329`.
- Semantici caldi: pericolo `#d35f4e`, avviso `#c4894a`, successo `#3d8168`,
  informazione `#8a6f47`.
- **Vietati blu, indaco, viola e ciano**, sia come classi Tailwind sia come
  hex negli stili inline: si rimappano su salvia o sabbia. **Vietati anche i
  grigi freddi**: `gray` e `slate` di Tailwind sono blu-tinte, e un `#64748b`
  a mano stona sulla crema. `frontend_lotti` e `frontend_menu` rimappano nel
  loro `tailwind.config.js` le scale fredde su sabbia e
  `gray`/`slate`/`zinc`/`neutral` su una neutra calda dai token (`stone` e
  `amber` sono gia' caldi). Scansione dopo ogni modifica frontend, **sui
  bundle compilati** (un remap del config si vede solo li'):
  `grep -rEn "5D29C7|1E1B4B|7c3aed|8b5cf6|6366f1|4f46e5|violet-|indigo-|bg-blue-|bg-sky-|text-blue-|border-blue-|3b82f6|2563eb|1d4ed8|F1F5F9|E2E8F0|CBD5E1|94A3B8|64748B|475569|0F172A|1E293B|6B7280|9CA3AF|D1D5DB|E5E7EB|374151|111827"`
- **Un solo font per tutte e quattro le app, ERP compreso: Plus Jakarta Sans**
  (400-800, da Google Fonts). Non introdurre una seconda famiglia: un titolo
  si distingue dal **peso** (700/800) e dalla spaziatura (`-0.02em`), mai dal
  carattere. `mono` resta solo per le colonne di importi (`tabular-nums`).
- Il colore non e' mai un nome: una variabile o una costante si chiama per
  quello che contiene (`SALVIA`, `--primary`), mai `NAVY` o `--violet` con
  dentro il verde. Una classe Tailwind non si costruisce a runtime
  (`bg-${x}-100`): il JIT non la genera e l'elemento resta senza stile.
- Icone Lucide, mai emoji nelle interfacce nuove (su Android rendono con
  colori di sistema non controllabili).
- Ogni pagina centrata, **mai scroll orizzontale su smartphone**: le tabelle
  larghe diventano card impilate. Tocco minimo 44px.
- L'ERP ha i suoi **colori** in `frontend/src/lib/utils.js` (slate freddo e
  oro, 13px, raggi 6-10px) e usa `PageLayout`/`PageHeader`: non introdurre
  Tailwind né un secondo sistema di token. Il font invece è condiviso. Il colore non è mai l'unica informazione: ogni badge ha anche testo.
- Le app portate pari pari mantengono il loro aspetto: nessuna contaminazione
  con il layout dell'ERP.

### Le mani sporche
Il pasticcere e il banconista hanno **sempre le mani sporche**: nei flussi
operativi si sceglie da tendine, chip e bottoni grandi, non si scrive a
tastiera. Ogni campo di testo libero (motivi, azioni correttive, note) va
sostituito con opzioni predefinite più «Altro (scrivi tu)» come eccezione.

## Convenzioni tecniche trasversali

- **Importi sempre `Decimal`** con valuta esplicita, mai `float`.
- **Hash degli originali SHA-256.** L'MD5 si usa solo dove lo fornisce l'API
  Drive per trovare copie identiche, mai per una decisione nuova.
- **Date**: backend ISO-8601 con timezone, interfaccia sempre `gg/mm/aaaa`.
- Gli scheduler girano sul fuso **`Europe/Rome`**.
- Il codice tributo è **sempre una stringa**, mai convertito a numero. Lo
  stesso vale per codice avviso e IUV.
- Errori API con `code`, `message`, `details`, `correlation_id`; paginazione e
  limiti dichiarati. **L'autorizzazione sta nel backend**, mai solo nella UI.
- Il dato più recente si mostra per primo.
- Un comando di import **salva sempre**; una modalità di sola anteprima va
  etichettata esplicitamente come simulazione (`dry_run`).
- Endpoint senza frontend, scheduler, integrazione o test restano in
  quarantena e non si ricreano; un alias legacy reindirizza al canonico, mai
  con una risposta finta.
- **Due copie dello stesso modulo non si tengono allineate a mano.** Quando un
  sottopercorso esiste sia in `app/` sia in `app/hr/`, la logica va in un
  modulo solo sotto `app/` e il lato HR diventa un **re-export** (solo import,
  docstring e `__all__`). Prima di fondere, il diff si **classifica riga per
  riga**: ogni differenza è una correzione presente da un lato solo oppure una
  divergenza voluta, e va detto quale. Nessuna copia si cancella «perché
  sembra vecchia».
- Prima di dichiarare morto un modulo, la prova è la **raggiungibilità reale**,
  non il nome: gli import relativi (`from .routers import x`) e quelli dentro
  una funzione contano, e `tests/runtime/test_fork_app_hr.py` nomina i
  duplicati **perché** lo sono, quindi non vale come citazione.

## Archivio dati e architettura

- **Supabase è l'unico archivio, senza eccezioni**: un solo progetto
  `GestionaleCloud`, `render.yaml` impone `DATA_BACKEND=supabase` ed è
  l'unico valore accettato dal codice. Drive resta la fonte degli
  **originali documentali**, non il database. Il vecchio runtime Google
  Sheets (backend, libreria di sincronizzazione, endpoint admin e job
  schedulato) è stato rimosso il 19/09/2026: non esiste più nel codice, nemmeno
  come fallback di sviluppo.
- Schemi: `gestionale` (ERP: `documents`, `blobs`, `collection_versions`,
  `protocollo_drive`, `runtime_scheduler_leases`), `hr` (tabelle `app_*`,
  `id text` + `doc jsonb`), `lotti` (`lotti_documents` + RPC `lotti_*`),
  `menu` (tabelle + bucket `menu-images`), `legacy_staging` (archivio
  CeraldiFatture, sola consultazione). Solo `menu` e `public` sono
  raggiungibili da `anon`/`authenticated`.
- I PDF HR vivono in `gestionale.blobs` (chiave = SHA-256, conteggio dei
  riferimenti): si caricano su richiesta, mai idratati in memoria.
- **Cache incrementale del runtime** (ERP `supabase_runtime_database.py`, HR
  `app/hr/db_supabase.py`): ogni collezione letta resta in memoria nella
  versione leggera (senza XML/PDF/foto); una firma per tutte le collezioni al
  più ogni 15 s, poi solo i delta; finestra di grazia 120 s se la firma
  fallisce. `GC_RUNTIME_CACHE=0` / `HR_RUNTIME_CACHE=0` la spengono.
- `/api/health` risponde entro 2 s anche con la probe appesa (`degraded`, non
  503; `?strict=true` per il 503). Una sola probe in volo per processo.
- Gli scheduler acquisiscono una lease distribuita su Supabase: il lock locale
  resta solo come riserva prima che la connessione sia disponibile (avvio,
  test). **La lease si restituisce allo spegnimento**
  (`rilascia_lease_attive`), non si lascia scadere: un processo che muore
  tenendola blocca il suo job per tutto il TTL (900 s) e chi subentra può solo
  saltare il turno. Per lo stesso motivo `stop_scheduler` chiude con
  `shutdown(wait=False)`: i job sono coroutine dello stesso event loop, e
  aspettarli da dentro il loop impedisce allo spegnimento di arrivare in fondo.
- Il download di un file Drive sta in un posto solo,
  `app/services/drive_download.py`: non è specifico di una sezione.
- PostgREST esegue le RPC del runtime come ruolo `anon`, con
  `statement_timeout` 20 s; `authenticator` resta a 8 s. Da rivedere se si
  cambia compute o si riduce il payload di `documents`.

### Regole per chi scrive codice sui dati

1. Liste, conteggi e lookup usano sempre una proiezione senza payload
   (`metadata_projection(collection)`): viene servita dalla cache senza RPC.
2. Il payload si legge **per id** (`find_one({"id": …})`), mai con `find({})`.
3. «Ha il PDF / senza XML» si filtra sul marcatore `_payload_stato`, non sul
   contenuto.
4. Un endpoint che lavora su un'intera collezione fa **un prefetch unico** e
   gira **in background** con stato in `sistema_stato`: oltre i 5 minuti il
   proxy Render taglia la richiesta.
5. Migrazioni DDL su `gestionale.documents` a database scarico o con
   `create index concurrently`. Ogni DDL fa ricaricare lo schema a PostgREST
   (503 per minuti): l'HR fa DDL solo se la tabella manca davvero.
6. **Nessuna cancellazione con filtro**: solo per id, con
   `gc_delete_documents` / `gc_delete_blobs` / `lotti_delete_*`. `DELETE` e
   `TRUNCATE` a mano sono bloccati su `gestionale.documents`, `.blobs`,
   `lotti.lotti_documents` e `legacy_staging`; per una manutenzione voluta,
   `select gestionale.consenti_cancellazione();` e prima un backup.
7. Nessun agente e nessuna sessione automatica deve avere la password
   Postgres: solo l'API con il segreto runtime. Il ruolo dell'app è `hr_app`.
8. Un protocollo non dimentica: un file sparito da Drive diventa
   `stato='rimosso'`, un doppione va in quarantena su richiesta esplicita, una
   scrittura contabile sbagliata si **storna**, non si cancella.
9. Il secondo ingest della stessa fonte deve dare **`nuovi=0`** e zero nuove
   scritture contabili: è il criterio di collaudo dell'idempotenza.
10. **I due archivi non usano la stessa chiave.** Il runtime dell'ERP
    (`services/supabase_runtime_database.py`) indicizza i documenti per `_id`,
    l'adattatore HR (`app/hr/db_supabase.py`) per `id`, e in HR gli
    identificativi sono **testo** (UUID), mai `ObjectId`. Un codice condiviso
    fra i due rami filtra per entrambi i campi; `bson`/`motor` non devono
    comparire in codice nuovo.
11. Un nome di campo sbagliato non dà errore, dà silenzio: `{"campo": {"$ne":
    True}}` su una chiave inesistente passa **sempre**. Prima di fidarsi di un
    filtro, contare sul database quante righe hanno davvero quella chiave.
    Vale anche fra due funzioni: `supplier_result["nuovo"]` al posto di
    `supplier_created` dava sempre `False`, e un alert non è mai partito.
12. **Su `invoices` i campi canonici sono quelli inglesi**: `invoice_date`,
    `total_amount`, `invoice_number`. `data_documento` e `totale` sono derivati
    e mancano sulle fatture che il motore IVA non ha toccato: filtrarci o
    sommarci perde righe in silenzio. `iva` e `imponibile` ci sono sempre.
13. Un conteggio che torna zero tondo, o uguale al totale su ogni colonna, si
    tratta come un errore di lettura finché non è smentito. Lo stesso per uno
    stato: in archivio convivono `archived` e `archiviata`, e un filtro che ne
    conosce una sola include documenti che doveva escludere.
14. **`except Exception: pass` è vietato dove si contano euro** e non cresce
    altrove (`tests/runtime/test_guasti_muti.py`): il log dice *quale dato non
    c'è più*, non «errore». Vale anche un `%s` senza argomento: quella riga non
    viene scritta affatto.

## Identità, prove e attese

- Nessuna entità si associa per solo importo. Una relazione certa richiede
  identità/provenienza coerente e importo esatto al centesimo quando l'importo
  fa parte della prova.
- Nei casi ambigui mostra i candidati (`Scegli fattura`, `Scegli driver`,
  `Scegli verbale`) e non applicare il collegamento.
- Fattura, disposizione, ricevuta, quietanza e movimento bancario sono prove
  **distinte**, collegate da `operation_id`, mai fuse in un solo record.
- I documenti originali restano immutabili: hash, fonte, versione, timestamp e
  log. I duplicati si marcano, non si eliminano in modo permanente.
- **Una prova successiva non crea mai l'obbligo che dovrebbe dimostrare.** Il
  fatto autorevole crea subito l'attesa; la prova la soddisfa o la lascia
  `DA_VERIFICARE`.
- Stati fissi delle attese: aperti `ATTESO`, `DA_VERIFICARE`,
  `IN_ELABORAZIONE`, `ERRORE`; terminali positivi `SODDISFATTO`,
  `NON_APPLICABILE`, `SUPERATO`. `ERRORE` non chiude il processo e non vale
  come `NON_APPLICABILE`. Un processo è chiuso solo quando ogni attesa
  obbligatoria è terminale positiva (`app/services/expectation_policy.py`).
- Ogni attesa nasce con tipo, owner e `source_fact_id` obbligatori.
- Per ogni modifica a un flusso con attese serve un test che provi: il fatto
  crea l'attesa prima della prova; il reimport non duplica; la prova certa
  conserva gli ID; la prova ambigua non inventa dati; la chiusura fallisce con
  un'attesa aperta.
- Un alert mostra sempre l'elenco dei record coinvolti. Un comando di
  manutenzione che l'utente deve ripetere per correggere duplicati prevedibili
  è un difetto: la prevenzione per ID/hash sta nel flusso di importazione.

## Ingresso documenti

- `Documenti > Import` è l'unico ingresso manuale operativo. Ogni canale Drive
  ha `DA ELABORARE | ELABORATE | ERRORI`; gli id delle cartelle stanno nelle
  variabili d'ambiente di Render, non in questo file.
- Le fatture elettroniche arrivano dal canale Drive/SDI configurato. Una
  fattura italiana trovata per email è un'anomalia, non una seconda fonte.
- Gmail/IMAP acquisisce F24, quietanze, cedolini e verbali **solo** dai
  mittenti autorizzati. I mittenti non si cablano per indirizzo: regole
  versionate su indirizzo, dominio, oggetto, intestazioni PEC e tipo di
  allegato (`app/services/mittenti.py`; i builtin sono solo una base
  rigenerabile). Un solo downloader: la scansione `ALL_FOLDERS` di
  `email_full_download.py`, mai un secondo su `INBOX`.
- Le ricerche email usano `in:anywhere`, preservano message ID, thread ID e
  SHA-256, e **non spostano né cancellano gli originali**. Mai marcare letto,
  etichettare o rispondere automaticamente. Paginare fino a esaurimento, mai
  la sola prima pagina; ogni giro registra letti/nuovi/aggiornati/ambigui/
  errori e l'ultimo cursore.
- Un errore di parsing **conserva email e allegato** e crea una coda visibile:
  non si scarta nulla.
- Gli ZIP si validano prima dell'estrazione (path traversal, zip-bomb,
  estensioni vietate, limite di dimensione), poi si deduplicano e inventariano.
- Deduplica documentale certa solo con SHA-256 **e** confronto byte; mai per
  nome, dimensione, data o importo. Per i PDF amministrativi serve anche
  l'identità business (beneficiario/CRO, dipendente/periodo, F24/codici
  tributo, verbale/targa). Dedup in ingresso: hash del contenuto più
  nome+dimensione con tolleranza 10%; un documento non classificato genera un
  alert, non viene assegnato a caso.
- Pulizia Drive: solo copie esatte, **Cestino mai eliminazione permanente**,
  con anteprima e autorizzazione esplicita.
- Estratti conto: inbox unica per sei fonti; riconoscimento nell'ordine
  percorso → nome file (solo segni esclusivi) → contenuto, e il contenuto si
  prova Nexi → PayPal → mutuo → banca. «estratto conto» da solo non è un
  segno. Non riconosciuto → cartella Errori col motivo scritto, **mai
  indovinato**: indovinare significa registrare le spese Nexi come uscite dal
  conto. Arretrato pre-2026 fermo per scelta del titolare
  (`DRIVE_ESTRATTI_ANNO_MINIMO`); un nome senza anno vale come arretrato.
- Acquisizione serale RT: Render non raggiunge la rete del locale, quindi
  `scripts/sync_rt_to_drive.py` gira su un PC della LAN (ignora gli XML
  `ESITO`, SHA-256, copia atomica dei soli file nuovi). `RT_LOCAL_BASE_URL` e
  `RT_DRIVE_INBOX` sono variabili **locali**: mai su Render.

### Drive, struttura canonica

- `05_PERSONALE_E_CEDOLINI/DIPENDENTI/<COGNOME NOME>/` è il **fascicolo unico**
  della persona: cedolini (profondità 2), `BONIFICI/` (profondità 3, il canale
  bonifico legge solo dentro `BONIFICI`), `CERTIFICAZIONI UNICHE/`. I bonifici
  non stipendio stanno in `03_BANCHE_E_PAGAMENTI/BONIFICI`.
  **Attenzione**: non puntare `GOOGLE_DRIVE_BONIFICI_FOLDER_ID` a DIPENDENTI
  con un backend che non vincoli la profondità: leggerebbe i cedolini come bonifici.
- `10_BILANCI_DICHIARAZIONI/DICHIARAZIONI FISCALI`: canale
  `dichiarazione_fiscale`, senza `category_hint` perché la cartella mescola
  770/IVA/IRAP/LIPE/Redditi SC — decide `classify_document()` dal contenuto.
  Si scartano per **nome file** i singoli quadri già contenuti nel PDF intero e
  i documenti che hanno un canale proprio.
- Il protocollo Drive (`gestionale.protocollo_drive`, tabella relazionale, non
  `documents`) riconcilia Drive con l'inventario: file nuovo → riga nuova,
  cambiato → aggiornata, sparito → `stato='rimosso'` con la data. Le impronte
  collegano ogni file al documento **per contenuto**, mai per nome, e una
  stessa impronta in più posizioni non crea un secondo documento: le
  provenienze stanno in `source_occurrences`.
- Un solo motore di import per sezione: un documento storico si mette nella
  cartella `DA ELABORARE` giusta, non si carica da una pagina parallela.
- **Fatture ricevute**: `01_FATTURE_RICEVUTE/FATTURE/<anno>/` con le tre
  cartelle `Da elaborare | Elaborate | Errori` per ogni anno. Tre motori, tre
  mestieri diversi: il **giro ogni 15 minuti** (`drive_invoice_ingest.sync`)
  svuota le sole inbox, 25 file per volta, e sposta in `Elaborate` anche i
  doppioni; la **quadratura** (`/api/fatture/drive/quadratura`) ripassa le
  `Elaborate` e importa i buchi; la **ricostruzione**
  (`/api/fatture/drive/ricostruzione`) rilegge *tutto* a lotti riprendibili
  con un cursore, ripresi ogni 2 minuti dallo scheduler. Nessuna sposta un
  originale fuori dal suo anno, e l'anno lo decide il parser XML, mai il nome.
- Una coda che non cala e importa zero **non è un guasto**: i file già importati
  risultano doppioni e vengono solo spostati. A dire se manca qualcosa è la
  quadratura, non la lunghezza della coda.

## Regole contabili vincolanti

- Piano dei conti: solo CEE ufficiale in
  `app/services/piano_conti_ufficiale.py`; conversioni tramite
  `app/services/mapping_piano_conti.py`. La vecchia collezione `piano_conti` è
  dismessa: i codici storici sono alias e un conto fuori tabella viene
  **rifiutato** dal motore.
- **Un solo event bus**: `app/services/event_bus.py`, registrato all'avvio da
  `app/main.py`. `app/hr/services/event_bus.py` e' un re-export, non un
  secondo registro: un bus con handler propri che nessuno collega fa sparire
  gli eventi in silenzio. Un fatto si pubblica **una volta sola**.
- Motore unico Prima Nota: `app/services/scritture_contabili.py`. Non creare
  nuovi `insert_one` diretti per scritture contabili.
- Libro giornale in partita doppia (`movimenti_contabili`): motore unico
  `app/services/registrazione_contabile.py`, alimentato automaticamente
  all'import di fatture e corrispettivi RT (idempotente per documento con
  `idempotency_key = reg:<tipo>:<id>`, mai bloccante, esito negativo annotato
  in `registrazione_contabile_esito`). Il pregresso si recupera con
  `POST /api/piano-conti/registra-pregresso` (admin, in background). Non
  aggiungere altri punti di scrittura.
- **Ogni scrittura quadra Dare = Avere**, altrimenti non si salva.
- Il protocollo `numero_registrazione` è unico e progressivo **per anno**
  (riparte da 1 a ogni anno solare) e immutabile una volta assegnato.
- Il giornale sopravvive all'azzeramento delle fatture e si riaggancia al
  reimport con la chiave stabile della fattura; export e import sono idempotenti.
- Ogni riga di Prima Nota porta `conto_contabile` di tesoreria (19.01.01
  banca, 19.03.03 cassa, 19.01.05 Mastercard SumUp, crediti 15.07.x) **e**
  `conto_contropartita` CEE per categoria (33.03.01 fornitori, 39.07.01
  stipendi, 39.07.05 TFR, 75.01.07.x commissioni, 31.03.15 finanziamento soci,
  47.01.03 corrispettivi). I 9 conti POS articolano voci già in bilancio per
  tenere separati Numia, SumUp e PayPal: non sono conti nuovi.
- Ammortamenti: scrittura semplice DARE 05.04.01 / AVERE 01.05.01; il
  risultato d'esercizio resta con segno, con guardia anti-doppia chiusura.
- Ricavi: **solo corrispettivi RT**. Le fatture ricevute sono costi; gli
  accrediti POS e i payout non sono nuovi ricavi.
- Corrispettivi: in cassa entra **solo la quota contanti**, la quota POS va in
  Prima Nota Banca. Mai il totale.
- POS: corrispettivo XML, chiusura terminale e accredito bancario sono tre
  fatti distinti. SumUp corrente dall'API; Numia corrente dalla chiusura
  manuale serale; Numia storico ricostruito dagli export del gestore,
  deduplicati e accorpati per giorno. Tutte e tre creano l'attesa bancaria;
  l'estratto conto può soltanto riconciliarla.
- Accredito POS in banca riconosciuto solo con causale del circuito più il
  giorno operativo `DEL gg/mm/aa`; **Numia e Nexi sono lo stesso circuito**;
  commissioni e fatture del gestore escluse; attesa mancante o multipla →
  `DA_VERIFICARE`, la banca non crea la chiusura. L'accredito ricostruito
  dalla causale è **derivato**: l'export del terminale vince.
- Un versamento contanti genera uscita Cassa e corrispondente entrata Banca
  con lo stesso `operation_id`. Un trasferimento banca↔cassa sono due
  movimenti speculari collegati da `trasferimento_collegato_id` con categoria
  `trasferimento_interno`, non un flag sul singolo movimento.
- Prima Nota Banca non è la copia dell'estratto conto: una riga entra quando è
  nota la causale contabile oppure appartiene alle categorie bancarie senza
  documento ammesse dal codice.
- Riga bancaria canonica = riferimento esterno **oppure** fingerprint
  data+valuta+importo+causale+progressivo: reimportare lo stesso estratto non
  duplica. Assegni di importo ricorrente uguale ma numero o data diversi
  **non sono duplicati**. Le regole SDD creano un pagamento solo con
  identità, periodo e importo compatibili; altrimenti candidati.
- Categorizzazione movimenti banca: un solo motore,
  `app/services/categorizzazione_movimenti.py` (parole chiave su
  F24/Commissioni/Utenze/Fatture). Sopra le parole chiave, **regole
  imparate** dal titolare (`app/services/regole_riconoscimento_banca.py`,
  `/riconciliazione/regole-banca`): un pattern estratto da una causale reale
  vince sul generico, ma un pattern di solo vocabolario bancario comune (es.
  "COMMISSIONI SU BONIFICI", senza un nome di fornitore) è rifiutato alla
  creazione. Eliminare una regola non tocca i movimenti già categorizzati.
- Pagamenti stipendio via nome: regola in «Personale». Qui vale solo il
  corollario bancario — un professionista omonimo di un dipendente, o un
  pagamento occasionale a lui, non entra nel fascicolo stipendi
  (`_ESCLUSIONE_RE` in `hr_pagamenti_deposito.py`).
- Le simulazioni non scrivono sul consuntivo. La chiusura d'esercizio richiede
  checklist, anteprima, conferma forte, audit e rollback.
- Navigazione tra contropartite: un solo componente
  `frontend/src/components/LinkContropartita.jsx`; i deep-link letti dalle
  pagine sono `/fatture?invoice_id=`, `/riconciliazione/banca?movimento=`,
  `/prima-nota#sezione=banca&selected=`, `/contabilita/verifica?conto=`,
  `/contabilita/giornale?conto=|scrittura=`.

### IVA

- Il periodo non è il mese di ricezione: comanda `periodo_iva_attribuito`, e
  il flag `iva_utilizzata` impedisce la seconda detrazione.
- **`iva_detraibile` assente non vuol dire zero, vuol dire non deciso**, e
  `campi_iva_da_fattura` non lo scrive finché nessuno l'ha valutato: è
  l'unica guardia del libro giornale (`registra_fattura` rifiuta con «IVA
  detraibile non classificata»), e uno `0,00` di comodo la disarma
  registrando tutta l'IVA come costo indetraibile. All'import il campo lo
  valorizza `handlers/learning.handler_classifica_cdc`, registrato sullo
  stesso evento **dopo** il motore IVA.
- Regola del 15: operazione del mese precedente ricevuta **e** annotata entro
  il 15 → liquidazione del mese precedente, solo nello stesso anno solare.
  Ricevuta dopo il 15 → mese di ricezione. Operazione dell'anno precedente →
  **mai** retroattribuzione a dicembre: è un blocco, non un avviso.
- I 12 giorni sono un controllo sull'emissione del fornitore, mai una
  tolleranza di detrazione per noi.
- Una liquidazione confermata non si sovrascrive: ogni ricalcolo è una nuova
  versione, la riapertura è esplicita e motivata. Il calcolo annuale parte
  dalle liquidazioni confermate e dallo stato d'uso, non dalle date.
- **La LIPE è il documento canonico dell'IVA mensile**: se il nostro numero
  diverge da quello trasmesso dal commercialista, il giusto è il suo e lo
  scarto è un difetto nostro. Si legge **per posizione**
  (`app/services/lipe_parser.py`): nel livello testo del PDF le celle si
  mescolano alle caselle di spunta, e in ordine `18.058,92` diventa
  `218.058,92`. La prova non è il parser ma l'aritmetica del quadro VP —
  `VP6 = VP5 − VP4`, `VP14 = VP6 + VP8 − VP7`: un periodo che non quadra
  **non viene depositato** e non fa da fonte. Una comunicazione ritrasmessa
  (protocollo più alto) sostituisce la precedente.
- Il confronto mensile gestionale ↔ LIPE ↔ F24 è
  `GET /api/iva/confronto-commercialista/{anno}`: non aggiusta niente, dice
  dove si diverge. Un mese che non sappiamo calcolare è un «non lo so», non
  uno scostamento; una LIPE **a credito** non deve avere nessun F24, e il
  caso da segnalare è l'opposto.

### F24, tributi, dichiarazioni

- F24, singole righe tributo, quietanza e movimento bancario sono entità
  distinte. La quietanza documenta il pagamento ma **non sostituisce la prova
  bancaria** e non ricostruisce il modello: quietanza senza modello → alert
  bloccante «F24 mancante». Stato e residuo si determinano **per riga
  tributo**, non sul totale.
- Il saldo F24 non è mai un costo: ritenute 1001/1002/1012, addizionali
  3802/3847/3848 e quote a carico del lavoratore sono debiti verso enti. La
  sezione INPS non è tutta deducibile: la quota datoriale viene dalle paghe.
- RC01 regolarizza un periodo precedente: non è costo del mese in cui si paga,
  e si collega al DM10 di quel periodo senza sommare due volte i tributi.
- F24 ↔ cedolini si associano solo con soggetto, periodo, posizione
  contributiva e causali coerenti; la tolleranza vale solo sulla data di
  pagamento (mese successivo).
- Da un PDF fiscale si costruisce solo una `journal_proposal` versionata, mai
  una scrittura definitiva. Un codice tributo assente dal registro versionato
  blocca la contabilizzazione fino a validazione. La deducibilità è un esito
  versionato (`DEDUCIBILE|INDEDUCIBILE|LIMITATA|DA_VERIFICARE`): le sanzioni
  sono indeducibili, 1701/1704 sono crediti, non IVA né costo.
- IRAP è un motore separato da IRES, non sottrae mai l'intero F24, e le
  aliquote sono versionate per periodo d'imposta.
- Il catalogo dei codici tributo è consultivo: una ricerca non crea F24,
  pagamenti o scritture. Le tabelle sono **due** —
  `services/codici_tributo_f24.py` (la legge il parser) e
  `services/codici_tributo_db.py` (con le scadenze) — e
  `tests/fiscale/test_codici_tributo_coerenti.py` impedisce che tornino a dire
  il contrario: nel 2026 l'IRES era ruotata di uno, 2001 dava «acconto».
- Il **periodo di riferimento di un tributo sta sulla sua riga** (`anno`,
  `mese`), non sul modello: la data in cui l'F24 è stato pagato è un'altra
  cosa. L'IVA mensile sono i codici 6001–6012, uno per mese.
- **Nessun F24 ricostruito in automatico.** Nessun pagamento automatico è
  autorizzato.

## Personale: un solo sistema per funzione

- **L'anagrafica HR comanda** (`hr.app_dipendenti`): Lotti ne legge una
  proiezione (`sincronizza_operatori_da_hr`), il gestionale si riallinea a HR.
  Un solo stato del rapporto: `attivo` | `cessato` con data e motivo; la
  cessazione revoca il PIN. `PUT /dipendenti/{id}` aggiorna **solo i campi
  inviati**. La revoca, la chiusura dei contratti, il rifiuto delle richieste
  di assenza future e l'annullamento delle partite stipendio residue stanno
  tutti in un punto solo, `on_dipendente_cessato`: le pagine si limitano a
  pubblicare `dipendente.cessato`, non ripetono la pulizia a mano.
- **Un PIN per persona, nella scheda HR**: vale per il portale e per firmare
  in Lotti (bcrypt più impronta HMAC; mai due persone in forza con lo stesso
  PIN; mai un cessato). Il **PIN amministratore è uno solo per ERP, Menu,
  Lotti e HR** (`PIN_HASH_ADMIN`, verifica unica in `app/services/admin_pin.py`):
  apre le pagine riservate ma non è un'identità di firma sul tablet.
- **Cedolini**: il gestionale li scarica (Drive e posta) e ne ricava la Prima
  Nota salari; l'archivio che si vede è **solo in HR**
  (`hr_cedolini_deposito`, richiamato dopo ogni scrittura, dedup per chiave o
  per CF+anno+mese+tipo, mai sovrascrittura; 13ª e 14ª restano buste distinte).
- Il netto si legge solo dalla cella graficamente associata a `TOTALE NETTO` /
  `NETTO DEL MESE` / `NETTO IN BUSTA`: mai da `ARR. PREC.`, competenze,
  trattenute, TFR, arrotondamenti o dal nome file. Cella vuota → nullo,
  **mai zero**. Stati: `NETTO_VERIFICATO_DA_CEDOLINO`,
  `NETTO_NON_PRESENTE_O_NON_LEGGIBILE`, `MULTIPLE_NETS_DA_VERIFICARE`,
  `ERRORE_PARSER` (in `app/constants/stati_netto.py`); solo il primo alimenta
  Salari e bonifici, e la decisione si prende **solo** con `alimenta_salari()`,
  che fallisce **chiuso**: uno stato assente, vuoto o sconosciuto non passa.
  Su un dato che diventa un bonifico l'assenza di prova non vale come prova.
- Sulla collection `cedolini` il campo è **`pagato`**, non `pagata`: il
  femminile non esiste su nessun documento e un filtro che lo cerca passa sempre.
- **Un solo motore abbina bonifico e stipendio**: `associa_bonifici_stipendi`
  (identità completa, acconti, residuo). Nessun percorso può cercarsi da solo
  «il primo movimento con importo vicino e il nome nella descrizione»: un
  omonimo o due buste uguali nello stesso mese bastano ad attaccare il
  movimento sbagliato. Lo stesso per gli F24: `riconcilia_f24_tributi_banca`.
  Un movimento vale come prova solo se ha **evidenza bancaria ufficiale** e
  non è `in_attesa_estratto_ufficiale`.
- Il Libro Unico si legge da un router solo (`app/routers/libro_unico_parser.py`,
  chiamato dalla pipeline documentale): oltre a presenze e busta salva le voci
  codificate del cedolino e i **dati chiave** (ratei 13ª e 14ª, indennità
  L.207/24, trattamento integrativo L.21). Una voce assente resta nulla.
- Duplicato di cedolino **solo con hash del PDF uguale**: stesso dipendente,
  mese e importo non bastano (mensilità aggiuntive, arretrati, conguagli).
- Una cessazione letta in una busta vale solo se non esiste una busta
  successiva della stessa persona.
- **Pagamenti stipendio**: un solo ponte gestionale→HR
  (`hr_pagamenti_deposito`). Dipendente da CF → nome completo univoco →
  cognome univoco: la corrispondenza univoca **basta da sola** («il nome di un
  dipendente è un dipendente»: non serve la parola «stipendio» in causale né
  un lotto paghe). Resta il veto: TFR, fatture, commissioni e fornitori non
  entrano mai, nemmeno in coda, **anche con un nome dipendente dentro** la
  causale — l'esclusione vince sul nome. Ambiguo o `BENEFICIARI VARI` → coda.
  Il **lotto paghe** (≥3 dipendenti lo stesso giorno) resta un segnale per i
  casi non risolti altrimenti. Competenza da causale o nome file, altrimenti
  **regola del giorno 25**: prima del 25 = mese precedente, dal 25 = corrente.
  Stesso pagamento da PDF e da banca (dipendente, importo, data ±3 gg) → un
  solo esito, arricchito, mai duplicato.
- «Bonifici da assegnare» è una proposta di importo dovuto, stato iniziale
  `DA_ASSEGNARE`: non imposta bonifico eseguito, movimento, data di pagamento
  né riconciliazione.
- Cedolini e bonifici salario si associano per dipendente, periodo e regole
  temporali: non si richiedono importi identici quando esistono acconti o
  trattenute. Le correzioni a mano in «Paghe e bonifici» non vengono
  sovrascritte dalla sincronizzazione.
- **Dimissioni telematiche** (PDF o PEC): alert critico più scadenza UNILAV di
  cessazione a **5 giorni** dalla decorrenza (D.Lgs. 181/2000 art. 4-bis);
  revoca del lavoratore entro 7 giorni (D.Lgs. 151/2015 art. 26).
- **Giorni di chiusura** (`chiusure_attivita`): ristrutturazione 26/01–08/03/2026
  e ferie 15–23/08/2026 non sono corrispettivi mancanti.
- **Dello storico interessano solo cedolini e F24**: fatture e corrispettivi
  precedenti al 2026 restano in `legacy_staging` e non entrano in
  `invoices`/`corrispettivi`.
- Modali HR: solo il componente `Modal` di `frontend_hr/src/App.jsx` (WCAG 2.1
  AA: focus intrappolato, Esc, focus restituito). Campi dentro `<label>`,
  `aria-label` sui bottoni ripetuti, focus visibile salvia.

## Fatture: identità e duplicati

- Fornitore univoco per P.IVA → CF → id esterno verificato; gli alias sono
  solo di supporto. `canonical_id` stabile: un cambio di ragione sociale non
  crea una seconda anagrafica, e un merge conserva alias, IBAN, id precedenti,
  documenti e audit.
- Il metodo di pagamento si legge **solo dall'anagrafica fornitore**, mai
  dedotto dalla fattura; se non configurato la fattura resta `sospesa`, mai
  con un default «bonifico» **né un ripiego in cassa**: un pagamento in
  contanti senza prova è un'uscita inventata. Le righe storiche
  `source="metodo_fornitore_assente_provvisorio"` restano in archivio per
  audit ma sono escluse da elenchi e saldi (`SOURCES_ESCLUSE` in
  `app/routers/prima_nota_module/common.py`).
- «Metodo di pagamento non configurato» ha un vocabolario solo,
  `app/constants/metodi_pagamento.py`: `sospesa` (quello che scrive l'import),
  `da_configurare`, `none`, vuoto e campo assente valgono uguale. Chi tiene la
  propria lista si perde il caso più frequente.
- **Le fatture fornitore non hanno scadenza.** Decisione del titolare
  (19/09/2026): «decido io quando pagare, non c'è una data stabilita». Non si
  leggono le condizioni di pagamento dell'XML (rimessa diretta, 30 giorni data
  fattura), non si leggono le date stampate sul documento e non si inventa un
  «+30»: `data_scadenza` resta vuota. Il piano rate si conserva sul documento
  come dato dell'originale, ma non guida niente. Di conseguenza
  `check_scadenze_partite_task` salta le partite fornitore e l'avviso
  `FAT_DA_PAGARE_SCADUTA` non nasce più; F24 e stipendi, che una scadenza
  vera ce l'hanno, restano invariati.
- **«È pagata?» si chiede in un posto solo**: `e_pagata` /
  `FILTRO_NON_PAGATE` di `app/services/stato_pagamento_fattura.py`, e
  `ePagata` di `frontend/src/utils/statoFattura.js`. Lo stato vive in cinque
  campi (`stato`, `stato_pagamento`, `payment_status`, `pagato`, `paid`) e
  nessuno copre l'archivio: leggerne uno solo dichiarava non pagate 639
  fatture da 311.838,20 €, e `{"pagato": {"$ne": True}}` le riportava tutte
  fra le aperte. `status` è lo stato del documento e `stato_finanziario`
  quello della riconciliazione: nessuno dei due dice se è pagata.
- Il payload di `fattura.created` si costruisce solo con
  `app/services/eventi_fattura.py::costruisci_evento_fattura_created`, così
  import e recupero del pregresso propagano lo stesso evento.
- Un import che **non** pubblica `fattura.created` lascia la fattura senza
  partita aperta, senza alert e senza audit: nessun errore, nessuna traccia.
  Il recupero è `POST /api/admin/fatture/ripubblica-evento-created` (admin,
  background, `dry_run` per difetto), che ripubblica l'evento sugli stessi
  handler idempotenti e salta l'archivio storico.
- Spostare una fattura fra Cassa e Banca cambia metodo, relazioni e scritture
  **con lo stesso ID**: non nasce una seconda fattura.
- `app/services/fatture_identita.py` ricava l'identità dall'XML con lo stesso
  parser dell'import. L'impronta del **contenuto**
  (`content_hash_canonico`, prefisso di versione `c2:`, insensibile a BOM, a
  capo, codifica e caratteri non ASCII) prova che due XML sono la stessa
  fattura. La dedup tiene la copia già nel giornale e **storna** la scrittura
  del doppione. Collisioni aperte = `stato_import` di collisione **e**
  `status` non archiviato.
- Le note di credito ricevute (TD04/TD08, costante unica
  `app/constants/tipi_documento.py::TIPI_NOTA_CREDITO`) non sono costi: sia il
  ledger di cassa/banca (`prima_nota_module/sync.py`) sia il libro giornale
  (`registrazione_contabile.py::registra_fattura`) generano la scrittura
  invertita rispetto a una fattura normale (riduzione di costo, IVA a
  credito e debito v/fornitore, mai un cespite) e leggono `tipo_documento`
  prima di registrare.

## PartenoPay, verbali e flotta

- Conservare email, verbale, avviso, ricevuta PagoPA/PayPal e movimento banca
  come prove separate.
- Stati del verbale: `documento salvato`, `da verificare`, `attesa pagamento`,
  `attesa quietanza`, `pagato documentale`, `riconciliato banca`. L'importo si
  legge dal PDF, **mai dedotto dal nome file**. Lo stato corretto dopo un
  pagamento privo di ricevuta ufficiale è `attesa quietanza`, **mai** `attesa
  fattura`: non sono sinonimi.
- Associazione automatica driver: targa normalizzata più data/ora infrazione
  più storico assegnazioni. Le assegnazioni hanno un intervallo temporale: il
  driver è quello attivo **alla data/ora del fatto**.
- Se targa, driver, verbale o pagamento non sono univoci, conservare il
  documento e chiedere una scelta manuale. Le schede veicolo incomplete vanno
  in coda di qualità, non nel flusso normale.
- Il verbale genera un promemoria operativo a 5 giorni dalla scoperta.

## Sicurezza

- Segreti solo nelle variabili d'ambiente di Render.
- Non stampare, committare o trasferire credenziali.
- Non spostare né cancellare email e documenti originali.
- Eliminazioni reali, pagamenti e associazioni definitive ambigue richiedono
  conferma esplicita al momento dell'azione.
- Telegram è l'unico canale attivo per alert e notifiche operative: non
  registrare router, webhook o fallback WhatsApp.

## Dominio per app

### HR — contratto, accessi, turni

- **CCNL applicato: Pubblici Esercizi, Ristorazione Collettiva e Commerciale e
  Turismo** (Confcommercio-FIPE), codice CNEL **H05Y**, rinnovo 5/6/2024.
  **Non è il Terziario.** 40 ore settimanali, 14 mensilità (tredicesima a
  dicembre, quattordicesima a luglio), 26 giorni di ferie, enti EBNT/EBT,
  Fondo EST per la sanità, Fon.Te. per la previdenza complementare.
- **Login dipendente = tocca il tuo nome + PIN**: su un dispositivo condiviso
  in negozio digitare il cognome a ogni apertura era scomodissimo, e i nomi non
  sono un segreto. L'accesso amministratore è una voce a parte, non la scheda
  di un dipendente.
- Sessione lunga e persistente (7 giorni) per cucina e pasticceria: il portale
  riapre senza PIN finché il token è valido. «Esci» chiude subito.
- **Turni data-driven**, un solo punto di configurazione: per ogni dipendente
  modalità sala o barista, giorno di riposo fisso, giorni di Lunga, onomastico,
  flag «può coprire il bar». Nessun nome cablato nel codice. La preferenza di
  riposo scelta dal dipendente vince sul riposo fisso per quella settimana.
- **Timbrature solo in sede**: geofencing sulla sede in `impostazioni`
  (Ceraldi Caffè, Piazza Carità 14, Napoli, circa 40.842949 / 14.2489, raggio
  200 metri).

### Lotti — HACCP, magazzino, prezzi

- **Un solo punto d'ingresso per le fatture** e deduplica sempre attiva
  (fornitore + numero + data).
- **Prezzi solo da acquisti reali in fattura XML.** Gli ordini hanno totali
  veri: prezzo di riga, aliquota IVA dall'XML, imponibile, IVA e totale che si
  ricalcolano a ogni variazione, con le stesse colonne nel PDF.
- **FIFO consuma sempre il lotto con la data fattura più vecchia.**
- **Le bevande e gli alcolici del reparto bar** (acqua, birre, vino, prosecco,
  liquori, amari, sciroppi, succhi, bibite) si acquistano e si confrontano a
  cartone o a unità, **mai a chilo o a litro**.
- Conversioni reali: uovo 60 g, tuorlo 19 g, albume 33 g; pezzi e chili si
  convertono con il peso del pezzo.
- Ogni riga d'ordine dice **chi l'ha inserita** (dipendente, lavagna, riordino
  automatico, produzione, colazione). Le righe-nota (omaggi, riferimenti) non
  diventano prodotti di magazzino. Soglia minima e quantità di riordino a 1.
- Nomi di campo vincolanti: `ingredienti_dettaglio[].unita_misura` (non
  `unita`), `lotti.data_scadenza` in gg/mm/aaaa, `fornitori` ha per chiave
  `nome` e non `id`.
- Spostando un lotto si scrivono **sempre** sia `posizione` sia
  `frigo_numero`; per azioni reali sui lotti di un'attrezzatura si usa il match
  esatto sul nome, mai uno snapshot troncato («Frigorifero N°2» e «N°9» si
  confondono).
- `prodotti_master` è il catalogo canonico e `magazzino_unificato` il magazzino
  canonico; `prodotti_vendita` e `sconti_merce` sono domini diversi e non si
  fondono.
- Stampa: coda più print agent locale sul PC del negozio, stampante scelta per
  tipo di documento, agent autenticato con il PIN di un operatore dedicato.
- Accessi: PIN valido 2 ore; i dipendenti entrano ovunque tranne le pagine di
  amministrazione. Sui tablet condivisi il magazzino chiude la sessione dopo
  10 minuti.

### Menu — allergeni

- Gli allergeni sono un obbligo di legge, non una cortesia: **Regolamento UE
  1169/2011** e **D.Lgs. 231/2017** impongono di dichiarare i 14 allergeni
  principali per ogni prodotto. Il dato vive in `menu.menu_products.allergens`
  con i 14 id UE in `menu.menu_allergens`: **non in un file**.
- Il menu vero si gestisce su Qromo (`ceraldicaffe.qromo.it`): la sync
  sostituisce per intero categorie, sottocategorie e prodotti con
  `origine IS NULL`, e riduce gli allergeni ai 14 UE.
- **È Lotti a spingere nel Menu, non il Menu a pescare dalle ricette**, ed è
  l'unica strada ricetta → prodotto (il «Collega a una ricetta» dell'admin
  Menu era un doppione dal lato sbagliato, rimosso). Ogni ricetta la replica
  il ponte `app/lotti/servizi/menu_bridge.py` con la stessa foto
  (`origine = "lotti"`, `lotti_ref` idempotente, `menu_pubblico` → `visible`):
  le righe di Lotti sopravvivono alla sync Qromo e l'esito `menu_sync` non fa
  mai fallire l'endpoint Lotti. Pregresso con
  `POST /api/ricette-ripubblica-menu` (admin, in background).
- **Il menu pubblico non mostra categorie e sottocategorie senza prodotti
  visibili** (`menu_routes._build_hierarchy`): un riquadro vuoto in home ha
  l'immagine rotta e «0 prodotti». Il filtro sta in lettura perché è l'unico
  punto che copre anche le categorie già vuote in produzione, e perché
  `menu_products.subcategory_id` è NOT NULL (una riga nascosta la sua sezione
  deve comunque averla). Una categoria con prodotti in una sola sottocategoria
  resta visibile.
- **Le righe `origine = "lotti"` le possiede Lotti**: `PUT
  /api/menu/admin/products/{id}` le rifiuta con 409 (il ponte le riscrive
  intere a ogni salvataggio della ricetta, una correzione fatta nel Menu
  sparirebbe senza avviso).
- La ricetta ha **due prezzi**: `prezzo_vendita` è quello **al banco** (base di
  food cost e margine), `prezzo_tavolo` quello **al tavolo**, mostrato dal Menu
  digitale. Finché il tavolo non è deciso il Menu espone il banco e il ripiego
  resta visibile (`prezzo_tavolo_impostato`): non si copia l'uno nell'altro, o
  un prezzo mai scelto sembrerebbe deciso. **Valido solo se finito e maggiore
  di zero**: negativi, `nan` e `inf` sono 400 all'ingresso, `0` significa
  «togli il prezzo». Una ricetta **senza nessuno dei due** entra nel Menu
  **nascosta** (sarebbe ordinabile a 0 €) ed è contata nel backfill
  (`senza_prezzo`, `nascoste_per_prezzo`): non si inventa un ripiego.
- La categoria del Menu si sceglie sulla ricetta (`menu_category_id`,
  `menu_subcategory_id`); senza scelta resta «Produzione Ceraldi» più la
  sottocategoria per reparto. Le categorie si leggono e si creano da Lotti con
  `/api/menu-categorie`, sempre con `origine` valorizzata; se esiste già una
  categoria con quel nome di **altra** origine la creazione riesce ma la
  risposta porta un `avviso` (due riquadri «Bar» in home). **Una categoria di
  Qromo (`origine IS NULL`) non è agganciabile**: la sync la cancella e un
  prodotto di Lotti appeso lì farebbe fallire la cancellazione per chiave
  esterna.
- Chi allergeni da dichiarare non ne ha (distillati, bibite in bottiglia) si
  esclude dalla verifica, per prodotto o per reparto. Le esclusioni vivono in
  `menu.menu_allergeni_esclusioni`, **non** in una colonna di `menu_products`:
  la sync Qromo cancellerebbe qualunque flag messo lì, mentre gli id Qromo
  restano stabili. Escludere significa «non richiede la dichiarazione», non
  «nascondilo dal menu»: è conformità, si conserva e si revoca.

## Stato attuale (al 19/09/2026 — riscrivere sul posto)

- Ogni merge su `main` fa ridistribuire Render e riportare in memoria ~74.500
  righe: per qualche minuto la produzione è `degraded`. Non è un guasto, ma
  non si accodano merge, e il lavoro di fondo riparte dal suo cursore.
- Ingest cedolini: ramo vivo `services/cedolini_manager` →
  `services/salari_unificati_v2`; un netto illeggibile non diventa più zero.
  **Collaudo live non chiuso**: il giro orario Drive trova 0 file su 49 caselle.
- Il `last_login` di HR non è mai stato scritto fino al 19/09/2026 (`ObjectId`
  su un id testuale): da verificare al primo accesso col PIN.
- TFR: è accantonato. `hr.app_tfr_accantonamenti` è vuota ma il codice vivo
  scrive in `tfr_accantonamenti`: 1.175 righe, 42 dipendenti, 273.025,37 €.
- **Spento**: `PROTOCOLLO_DRIVE_ENABLED=false` (il giro portava la RAM a
  1,57 GB su 2 GB: riaccendere solo dopo averla ridotta).
- **Acceso**: scheduler, ingest Drive (fatture, estratti conto, cedolini,
  bonifici), ponte pagamenti HR, dedup fatture ogni 30 min, dichiarazioni
  fiscali fino a coda esaurita.
- Fatture in archivio **2.555**, di cui 685 pagate; collisioni 0. «Solo 2026 nel
  bilancio» è rispettata. 21 corrispettivi con contanti/POS non quadrati.
- **Su Drive 2.447 XML di fattura** (1.318 del 2026, 875 del 2025, 254 dal
  2021 al 2024). Ne sono già rientrate **396** che il gestionale non aveva
  (211.097,19 €), tutte pre-2026 e marcate `archivio_storico`. La
  ricostruzione va avanti da sola.
- **Nessuna liquidazione IVA è mai stata calcolata**: `/api/iva/liquidazioni`
  torna vuoto. Giugno e luglio 2026 sono calcolabili ma con **zero** acquisti
  (tutti in `detraibilita_da_verificare`): il saldo è l'IVA sulle vendite
  intera, 7.651,05 € e 6.211,86 €; agosto fermo su `giorni_senza_corrispettivo`.
  Corrispettivi 2026: 518.879,34 € incassati, 47.170,88 € di IVA a debito.
- Confronto con la LIPE 2026 (tre periodi, tutti quadrati): a marzo l'IVA
  esigibile combacia **al centesimo** (6.131,26 €); a gennaio mancano
  **5.005,88 €** di IVA detraibile, cioè acquisti che lui ha e noi no. Febbraio
  senza corrispettivi non è un buco: locale chiuso, e anche la LIPE ha le
  attive in bianco. Nessun F24 IVA 2026: la LIPE chiude a credito ogni mese.
- Cron Render `gestionalecloud-calderone-15min`: sospeso e senza codice, va cancellato dal pannello.
- Solo 108 prodotti del Menu su 325 hanno allergeni: obbligo di legge, da completare.

## Aperto (togliere la voce quando si chiude)

- Compute Supabase **Micro** insufficiente (crash Postgres del 17/09): valutare Small.
- Endpoint sincroni oltre i 5 minuti, da portare a lotti riprendibili:
  `/api/fatture/drive/quadratura` (tagliata a 300 s, arriva al 2022),
  `/api/paypal-api/riconcilia`, `/api/paypal-api/account-ids-non-mappati`,
  `/api/admin/riallinea-pagamenti-fatture`,
  `/api/prima-nota-salari/deposita-cedolini-in-hr`.
- Note di credito TD04 legacy (~20, precedenti al fix a `registra_fattura`):
  costo/IVA/debito aumentati anziché ridotti, da sanare con
  `storna_registrazione_fattura` per `fattura_id`.
- **Nessuno dei 187 fornitori ha `metodo_pagamento`** (solo 41 hanno un IBAN):
  finché resta così ogni fattura è `sospesa` e nulla va in Prima Nota Banca.
  Da popolare con una fonte vera, non dedotta dalle fatture.
- **Pregresso fatture**: 296 attive (173.184,83 €, 22.989,82 € di IVA) senza
  partita aperta, 280 anche fuori dal giornale (145.025,14 €). Ordine obbligato:
  `/api/admin/fatture/ripubblica-evento-created`, poi `/registra-pregresso`.
- Da lanciare, con `dry_run` prima: `/api/admin/fatture/azzera-scadenze` (642
  fatture e 971 partite con la scadenza inventata dal vecchio import);
  `/api/iva/lipe/importa` (`lipe_periodi` vuota); e
  `/api/pos-corrispettivi/chiusure-giornaliere/ricostruisci-numia` (senza, 180
  giornate su 183 restano «attende chiusura POS reale»).
- Riconciliazione: 158 fatture `riconciliata` con movimento non riconciliato,
  180 righe hub senza `fattura_id`; banca 2026 con 1.765 movimenti senza categoria.
- Drive `03/ESTRATTI CONTO/DA ELABORARE`: 291 documenti pre-2026 fermi per scelta; gli estratti importati arrivano al 17/08.
- HR: 38 bonifici con `cedolino_id` orfano, 119 in «bonifici da associare», 10
  tabelle attese dall'app assenti (turni_config, onomastici, richieste…),
  Iazzetta Francesco senza IBAN; Appuhamy, Aurigemma, Vitiello e Dell'Aquila da
  creare come storici cessati. UNILAV Moscato e Pocci da verificare (Ferrantini).
- `app/models/stati.py::STATI_PAGATI` conta «parziale» fra le pagate, ed è
  applicata a `status`, che sulle fatture vale solo archiviata/imported/
  archived: oggi non filtra niente. Da togliere o correggere.
- Drill-down «Verifica campi e F24»: agganciato al vecchio indice Drive, che
  non esiste più. `/api/download` serve `./downloads`, che nessuno popola.
- A mano, dal titolare: ruotare la password Postgres; DNS di `ceraldiapp.it` e
  servizi Render sospesi.
- Fork `app/hr/` quasi chiuso: restano **cinque** sottopercorsi duplicati
  (`routers/auth.py`, `routers/employees/dipendenti.py`, `routers/pin_login.py`,
  `routers/tfr.py`, `utils/dependencies.py`) più i tre del guscio, separati per
  scelta. Finché una coppia è aperta ogni correzione va cercata anche nel
  gemello; crescere non può, `tests/runtime/test_fork_app_hr.py` impone che la
  lista si accorci soltanto.
- `gestionale.blobs`: 216 PDF (4 MB, scritti tutti il 03/09) che **nessun
  documento cita** (zero chiavi `sha256:` in `documents`) e che solo
  `app/services/blob_store.py`, mai importato, sa leggere: o si riaggancia
  l'archivio, o si tolgono tutti e due. Stesso caso di
  `bank_reconciliation_hub` (2.017 righe), scritta da un trigger e letta da
  nessuno: o le si dà un lettore, o va spenta.
- `archivio_documenti_memoria.py` espone ancora `SheetDatabase` e
  `MemorySheetsClient`, che promettono Google Sheets senza chiamarlo mai: 54 e
  2 occorrenze in 12 file, da rinominare in un giro dedicato.

## Logica dentro al database

Su Supabase ci sono **trigger PL/pgSQL che scrivono dati contabili**: leggere
il codice non basta per sapere cosa succede a una riga. Elenco, ruolo di
ognuno e query su `pg_trigger` stanno in
`database/trg_bank_ec_before_write.sql`. La regola: **una regola contabile si
scrive in Python, versionata e testata**. Per questo il 19/09/2026
`trg_bank_ec_before_write` è stato rimosso — duplicava in SQL
`proiezione_bancaria.py`, girava prima e vinceva. Restano le guardie
anti-cancellazione, quelle su `updated_at` e `trg_bank_ec_after_write`, che
alimenta `entity_relations`.

## Verifica e pubblicazione

Per ogni modifica pertinente:

1. test mirati;
2. `python -m pytest -q` quando il cambiamento backend lo richiede;
3. `yarn test` e `yarn build` in `frontend/` quando coinvolge il frontend;
4. `git diff --check`; commit dei soli file pertinenti, mai `git add -A`;
5. **revisione avversariale del proprio diff prima di unire**: cercarvi cosa
   è sbagliato, non la conferma che funziona. Dal 19/09/2026 non c'è più un
   revisore esterno (bot Codex rimosso) e i test provano solo ciò che qualcuno
   ha pensato di scrivere. Tre domande: la chiave che leggo esiste sui dati
   veri? cosa ho dichiarato fatto senza riguardarlo? questo motore c'è già
   altrove? Da lì sono usciti l'IRES ruotata e l'email F24 mai partita. Un
   censimento di moduli mai importati conta solo se risolve gli import
   relativi **e** quelli dinamici (`__import__("app.x")`) su tutto il
   repository: cercarli nel solo `app/` più `tests/` li sovrastima di tre
   volte, e un file in più cancellato è un guasto in produzione;
6. unione su `main` (è la consegna: Render pubblica solo da lì);
7. CI verde e verifica `/api/health` sul commit pubblicato;
8. controllo live del flusso interessato senza mutare dati non autorizzati.

Produzione: **https://gestionalecloud.onrender.com**
