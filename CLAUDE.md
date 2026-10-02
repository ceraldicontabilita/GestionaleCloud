# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-10-01
storage_architecture: supabase
-->

Aggiornato il 02/10/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

**Gli unici documenti sono questo file, `README.md` e `PIANO_RISTRUTTURAZIONE.md`** (registro del
programma e piano approvato). Audit, mappe generate, changelog e diari raccontano com'erano le cose
in una certa data e impediscono di capire quali logiche siano in vigore: non si tengono.

## Come si tiene questo file

- Qui stanno **regole, architettura e stato attuale**. La cronaca di una
  sessione (cosa si è trovato, i numeri del giorno, le PR) **non si scrive**:
  sta nella storia di git, dove nessuno la confonde con una regola.
- «Stato attuale» e «Aperto» **si riscrivono sul posto**: un fatto superato si
  sostituisce, non gli si affianca la correzione. Una voce chiusa si toglie.
- Una regola nuova nata da un incidente entra nella sezione giusta, in una o
  due righe, senza il racconto di come ci si è arrivati.
- Non creare altri `.md`, né cartelle di documentazione, né report generati da
  script. `tests/runtime/test_claude_md.py` fa rispettare data dell'intestazione,
  divieto di capitoli datati e divieto di nuovi `.md`. **Non c'è un tetto di lunghezza**
  (decisione del titolare, 30/09/2026): si scrive quanto serve, senza ripetere la stessa regola due volte.
- Il codice, i test e la configurazione live vincono sempre su questo file.
  Se trovi una contraddizione, **correggi questo file** nello stesso commit.

## Il gruppo Ceraldi è un solo servizio

Un unico servizio Render (`gestionalecloud.onrender.com`, anche su `impresasemplice.online`; deploy
automatico da `main`, health check `/api/health`) e un unico progetto Supabase servono tutto:

| Cosa | Dove vive | Codice |
| --- | --- | --- |
| ERP / contabilità | `/` | `app/` + `frontend/` |
| HR, portale dipendenti | `/hr`, `/hr/portale` | `app/hr/` + `frontend_hr/` |
| Menu pubblico e admin | `/menu`, `/menu/admin` | `app/menu/` + `frontend_menu/` |
| Lotti (HACCP) | `/lotti` | `app/lotti/` + `frontend_lotti/` |
| Colazioni B&B | `/convenzioni` (il vecchio `/colazioni` rimanda qui) | `frontend_colazioni/` (pagina statica, nessun backend in `app/`) |

Il `Mount` di Starlette esige la barra finale: il prefisso **nudo** va
rimandato a `/<prefisso>/` fra i mount e il catch-all, o cade nella SPA
dell'ERP e chi apre `/lotti` si ritrova nel gestionale.

- Repository: `https://github.com/ceraldicontabilita/GestionaleCloud`.
  Checkout canonico Windows: `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`.
- **L'unico repository vivo è questo.** `AppDipendenti`, `Lotti` e `Menu` sono
  l'archivio del sorgente originale; `Gestionale` una riscrittura abbandonata.
- **Siti spenti, da non riaprire né citare**: `appdipendenti.onrender.com`,
  `lotti-frontend.onrender.com`, `lotti-backend-2wwb.onrender.com`, `www.ceraldiapp.it`.
  `impresasemplice.online` invece è vivo: dominio dello stesso servizio.
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
  tecnici da premere. **Quando c'è una scelta, fai la domanda** al titolare con le opzioni (la consigliata per prima).
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

### Design (salvia per HR, Menu e Lotti; l'ERP ha i colori dell'artefatto)
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
- L'ERP segue l'**artefatto «Gestore Attività»** (titolare, 26/09/2026): crema `#faf9f5`, inchiostro `#141413`, terracotta `#c15f3c`
  per azioni e stato attivo; token solo in `lib/utils.js` e `index.css`, niente Tailwind né `gs-`; vietati anche qui blu, viola e grigi
  freddi; il colore non è mai l'unica informazione (ogni badge ha testo). Ogni pagina: `PageHeader` (famiglia, titolo, perché, pastiglie), una riga di filtri, una tabella, 200 righe con «Mostra altre».
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
- **Niente «legacy»: una sola collezione, un solo sistema per funzione.** Una collezione, un alias, un endpoint, un campo o uno
  script di migrazione «vecchio» si **toglie nello stesso commit** che ne toglie l'ultimo lettore, ma solo dopo aver **contato sul
  database** che in produzione non ha righe (mai presumerlo: `piano_conti` ha dati, `attendance_presenze_calendario` e
  `email_fornitori` hanno ancora un writer vivo). Una migrazione una tantum si cancella a migrazione fatta; una lettura «in
  transizione» che unisce la vecchia e la nuova collezione conta due volte lo stesso dato. Una collezione senza righe non resta
  come costante «deprecata»: non c'è. I test che vietano scritture su un nome morto usano la stringa, non una costante.
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
  **originali documentali**, non il database.
- Schemi: `gestionale` (ERP: `documents`, `blobs`, `collection_versions`,
  `protocollo_drive`, `runtime_scheduler_leases`), `hr` (tabelle `app_*`,
  `id text` + `doc jsonb`), `lotti` (`lotti_documents` + RPC `lotti_*`),
  `menu` (tabelle + bucket `menu-images`), `legacy_staging` (resto
  dell'archivio CeraldiFatture, 5 tabelle da migrare, **staccato**: nessun codice lo legge). Solo `menu` e `public`
  sono raggiungibili da `anon`/`authenticated`.
- I PDF HR vivono in `gestionale.blobs` (chiave = SHA-256, conteggio dei
  riferimenti): si caricano su richiesta, mai idratati in memoria.
- **Cache incrementale del runtime** (ERP `supabase_runtime_database.py`, HR
  `app/hr/db_supabase.py`): ogni collezione letta resta in memoria nella
  versione leggera (senza XML/PDF/foto); una firma per tutte le collezioni al
  più ogni 15 s, poi solo i delta; finestra di grazia 120 s se la firma
  fallisce. `GC_RUNTIME_CACHE=0` / `HR_RUNTIME_CACHE=0` la spengono. Il buffer `_documents` di una collezione vale solo per l'operazione e si svuota alla fine (tenuto, ogni collezione conservava il suo ultimo lotto col payload fino all'OOM a 2 GB); `memoria_processo.py` limita le arene malloc e restituisce al sistema la memoria liberata ogni 5 minuti. **Istantanee**: i riepiloghi in sola lettura (`@istantanea`, `middleware/performance.py`) si servono pronti e si ricalcolano in sottofondo; ogni scrittura riuscita o «Rileggi» (`X-Rileggi`) le svuota; nel browser la copia della sessione è `getConCopia` (`lib/cacheGuscio.js`), mai un secondo meccanismo. Con `@istantanea(persistente=True)` l'ultimo riepilogo sopravvive al riavvio in `sistema_stato` (max 200 KB, mai oltre 7 giorni): dopo un rilascio si serve subito marcato `in_aggiornamento`/`da_copia_salvata` e si ricalcola; una scrittura la invalida (`istantanee_svuotate`), mai una copia precedente al salvataggio dell'utente. Finanziaria dice «aggiornato al» per ogni conto e avvisa se estratto conto, corrispettivi o SumUp sono fermi.
- `/api/health` di ERP, HR e Menu risponde entro 2 s anche con la probe appesa (`degraded`, non 503; `?strict=true`
  per il 503), una sola probe in volo (`services/health_probe.py`); il commit per tutte e quattro da `services/deploy_info.py`.
- Gli scheduler acquisiscono una lease distribuita su Supabase: il lock locale
  resta solo come riserva prima che la connessione sia disponibile (avvio,
  test). **La lease si restituisce allo spegnimento**
  (`rilascia_lease_attive`), non si lascia scadere: un processo che muore
  tenendola blocca il suo job per tutto il TTL (900 s) e chi subentra può solo
  saltare il turno. Per lo stesso motivo `stop_scheduler` chiude con
  `shutdown(wait=False)`: i job sono coroutine dello stesso event loop, e
  aspettarli da dentro il loop impedisce allo spegnimento di arrivare in fondo.
- Il download di un file Drive sta in un posto solo, `drive_download.py` (`scarica_originale` per id). Un solo service account (`GOOGLE_DRIVE_SA_JSON` / `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`), provato sulla cartella unica da ogni servizio Drive (`drive_credential_probe.py`).
- PostgREST esegue le RPC del runtime come ruolo `anon`, con
  `statement_timeout` 20 s; `authenticator` resta a 8 s. Compute **Small** (90 connessioni,
  database ~2,2 GB): i timeout si rivedono se si riduce il payload di `documents`.

### Regole per chi scrive codice sui dati

1. Liste, conteggi e lookup usano sempre una proiezione senza payload
   (`metadata_projection(collection)`): viene servita dalla cache senza RPC.
2. Il payload si legge **per id** (`find_one({"id": …})`), mai con `find({})`.
3. «Ha il PDF / senza XML» si filtra sul marcatore `_payload_stato`, non sul
   contenuto.
4. Un endpoint che lavora su un'intera collezione fa **un prefetch unico** e
   gira **in background** con stato in `sistema_stato`: oltre i 5 minuti il
   proxy Render taglia la richiesta. Lo stesso motore non si chiama **da un
   handler per-documento**: `fattura.created` nasce una volta per fattura e il
   giro Drive ne importa 25, quindi il costo si moltiplica per il lotto. Il
   ripasso completo sta solo in `riconcilia_documenti_e_pagamenti`, nel giro
   dei 30 minuti; l'estratto conto lo **accoda in sottofondo**, mai lo aspetta.
5. Migrazioni DDL su `gestionale.documents` a database scarico o con
   `create index concurrently`. Ogni DDL fa ricaricare lo schema a PostgREST
   (503 per minuti): l'HR fa DDL solo se la tabella manca davvero. Ogni migrazione applicata al progetto si salva nello stesso giorno in `supabase/migrations/<versione>_<nome>.sql`, con la versione del registro `supabase_migrations.schema_migrations` (letta dal registro, mai inventata: tre file del 01/10 con una versione a mano erano doppioni del registro); il file e' l'unico modo di ricostruire il database da zero.
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
    `supplier_created` dava sempre `False`, e un alert non è mai partito. `$in: [None, …]` **non** prende il campo assente: «non ancora collegato» si scrive con `pagopa_receipts.non_collegato`.
12. **Su `invoices` i campi canonici sono quelli inglesi**: `invoice_date`,
    `total_amount`, `invoice_number`. `data_documento` e `totale` sono derivati
    e mancano sulle fatture che il motore IVA non ha toccato: filtrarci o
    sommarci perde righe in silenzio. `iva` e `imponibile` ci sono sempre. L'`id` è un **numero** su 786 righe di 1.532: cercare per id con `{"$in": [testo, int]}`, cioè con l'helper unico `app/utils/id_fattura.py` (`filtro_id`, `varianti_id`): una ricerca o un aggiornamento col solo testo non trova la fattura e non dà errore.
13. Un conteggio che torna zero tondo, o uguale al totale su ogni colonna, si
    tratta come un errore di lettura finché non è smentito. Lo stesso per uno
    stato: in archivio convivono `archived` e `archiviata`, e un filtro che ne
    conosce una sola include documenti che doveva escludere.
14. **`except Exception: pass` è vietato dove si contano euro** e non cresce
    altrove (`tests/runtime/test_guasti_muti.py`): il log dice *quale dato non
    c'è più*, non «errore». Vale per un `%s` senza argomento (riga mai scritta) e
    per `str(exc)` da solo: molte eccezioni vere hanno messaggio vuoto e lasciano
    «Lettura fonte: ». Nel log ci va sempre anche `type(exc).__name__`.
15. **Un operatore di aggregazione non implementato non dà un valore sbagliato:
    fa fallire l'intera pipeline.** `$trim` mancava, e con lui sono morte per mesi
    la ricerca web prodotti (644 giri falliti di fila) e gli sconti merce: prima di
    usarne uno nuovo, `archivio_documenti_memoria.evaluate_expression` deve conoscerlo.
16. **Il calcolo puro su una collezione intera non gira sull'event loop**: oltre 5 s di loop bloccato l'health check di Render scade e
    il servizio si riavvia, azzerando i timer di tutti i giri lunghi (un giro che parte «18 minuti dopo l'avvio» non parte mai se si
    riavvia ogni 20). Si porta in `asyncio.to_thread` (`collega_ravvedimenti`: 10 s di calcolo, causa dei riavvii del 01/10/2026; la lettura delle ricevute `parse_receipt_pdf`, con l'OCR di un PDF scansionato, dal giro della cartella unica: un riavvio ogni 20 minuti fino al 02/10/2026);
    il segnale è `[loop bloccato] ripartito dopo N s` in `sorveglianza_loop`.

## Identità, prove e attese

- Nessuna entità si associa per solo importo: servono identità/provenienza coerente e importo al centesimo (anche per gli **acconti**: 2–4 bonifici allo stesso fornitore che sommano una sola fattura aperta, entro 90 giorni, `reconcile_acconti_fornitore`, nel job bancario corto). Unica
  eccezione, regola del titolare: un assegno paga la fattura di pari importo emessa nei 15 giorni prima dell'addebito,
  se è l'unica (`REGOLA_TITOLARE_GIORNI_PRECEDENTI`); il numero scritto nel report «Fatture ricevute» vince sempre.
- Nei casi ambigui mostra i candidati (`Scegli fattura`, `Scegli driver`,
  `Scegli verbale`) e non applicare il collegamento.
- Fattura, disposizione, ricevuta, quietanza e movimento bancario sono prove
  **distinte**, collegate da `operation_id`, mai fuse in un solo record.
- I documenti originali restano immutabili: hash, fonte, versione, timestamp e
  log. I duplicati si marcano, non si eliminano in modo permanente.
- Ogni documento importato (F24, quietanza, LIPE, cedolino, ricevuta di bonifico) nasce con `canale` ∈ `posta|drive|caricato|altro`
  (`app/constants/canale_documento.py`, `canale_obbligatorio`: l'etichetta che dice il canale vince, l'id Drive decide solo se manca; la prima copia arrivata lo fissa) e con uno stato
  esplicito (LIPE `canonica`+`sostituisce`, bonifico `stato_riconciliazione`, alert `aperto|risolto|ignorato`). Il dettaglio grezzo resta nel
  campo storico di ogni collezione (`import_source`, `fonte`, `source`, `origine`); `canali_documento` lo riduce per l'archivio senza `canale`. **Le buste già in archivio senza `canale`** si bonificano con `POST /api/cedolini/canale/bonifica` (admin, `dry_run`, in sottofondo, `limite`; gestionale per `id` e HR per `id` testo): `canale_ricavabile` (stesso normalizzatore) dà prima il canale già scritto (non si cambia: la prima copia lo fissa), poi un'etichetta di provenienza (i nomi di motore o archivio come `cedolino_v2` e `gestionale_cloud` non sono canali), la posta (`email_info`, nome file `AAAA-MM-GG_mittente@…`), Drive (id Drive o cartella `DA ELABORARE`/`ELABORATE`); se nessun campo lo dice resta vuoto (`non_ricavabile`). Non tocca netto né `netto_fonte`.
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
- Un alert mostra sempre l'elenco dei record coinvolti (la lista ricava il link da `entita_collection`/`entita_id`); alert falsi e verbali nati da un numero di fattura li chiude o mette in quarantena `bonifiche_automatiche.py` nel job bancario corto, per id e col motivo. Segnali incrociati in un modulo solo (`controlli_incrociati.py`, ogni mattina): beneficiario «FAVORE» diverso dal fornitore, fattura con due uscite intere, importo oltre 4× la mediana del fornitore, mese d'estratto senza movimenti (BPM, SumUp, Numia), RT dimenticata; un avviso ignorato non rinasce. Un comando di manutenzione che l'utente deve ripetere
  per correggere duplicati prevedibili è un difetto: la prevenzione per ID/hash sta nel flusso di importazione.
- **L'abbinamento parte all'arrivo del secondo pezzo, in tutti e due i sensi**, mai aspettando un giro: F24 ↔ quietanza ↔ banca (`cerca_controparti_f24`), fattura ↔ report del titolare ↔ banca (`applica_per_fattura_arrivata`, `riprocessa_estratto_dopo_import_fattura`). I giri restano solo come rete.

## Ingresso documenti

- `Documenti > Import` è l'unico ingresso manuale operativo, e lo stesso smistatore serve la cartella unica
  Drive (`DA ELABORARE | ELABORATE | ERRORI`); il suo id sta su Render, non in questo file.
- Le fatture elettroniche arrivano dal canale Drive/SDI configurato. Una
  fattura italiana trovata per email è un'anomalia, non una seconda fonte. Una fattura **estera** arriva in PDF (SumUp, Irlanda): Documenti > Import la passa al lettore unico `process_fattura_estera_pdf` solo se il testo porta una partita IVA UE non italiana, e un fornitore italiano letto dal PDF non si importa mai; resta «da verificare» e le sue righe sono solo testo (`descrizione_righe_ai`), mai importi, lette anche dal giornale; la conferma del titolare rifà classificazione e scrittura (storno e nuova registrazione, mai correzione sul posto). Dopo la conferma la fattura resta in «Confermate» col suo pagamento: senza prova elenca i PayPal con lo stesso importo al centesimo e il titolare sceglie (`collega_paypal_scelto_dal_titolare`: la sua parola sostituisce nome e numero, mai importo o valuta); un addebito bancario ufficiale già legato al PayPal chiude la catena anche se l'estratto PDF ha rimesso `riconciliato=False` (`finalizza_transazione_paypal_se_completa`).
- Gmail/IMAP acquisisce F24, quietanze, cedolini, verbali e schede tecniche **solo** dai
  mittenti autorizzati, mai cablati nel codice: regole versionate su indirizzo, dominio, oggetto,
  intestazioni PEC e tipo di allegato (`app/services/mittenti.py`; i builtin sono una base rigenerabile). Un
  solo downloader: la scansione `ALL_FOLDERS` di `email_full_download.py`, mai uno su `INBOX`: ogni ora, cursore UID per cartella in `sistema_stato` (nuovi, poi lo storico fino al primo messaggio), cartella in sola lettura e `BODY.PEEK`; credenziali solo da `gmail_credentials.py`; login rifiutato = alert `POSTA_NON_RAGGIUNGIBILE` + Telegram.
- Le ricerche email usano `in:anywhere`, preservano message ID, thread ID e
  SHA-256, e **non spostano né cancellano gli originali**. Mai marcare letto,
  etichettare o rispondere automaticamente. Paginare fino a esaurimento, mai
  la sola prima pagina; ogni giro registra letti/nuovi/aggiornati/ambigui/
  errori e l'ultimo cursore.
- Un errore di parsing **conserva email e allegato** e crea una coda visibile:
  non si scarta nulla.
- **ZIP oltre 100 MB**: restano su Drive e si importano con `POST /api/admin/documenti/import-zip-drive?file_id=…` (`drive_zip_import.py`, `dry_run` per difetto = solo anteprima): indice e voci a intervalli di byte, ogni voce dallo smistatore della cartella unica (stessi doppioni), cursore in `sistema_stato`, si riprende dopo un riavvio; niente si sposta né si cancella su Drive. Avanzamento: `GET …/stato`. Lo stesso endpoint importa una **cartella** Drive con le sottocartelle (in sola lettura: lo smistatore della cartella unica non ci scende); `DRIVE_IMPORT_CARTELLE_ID` la fa girare da sola, un controllo al giorno. **Ripasso degli errori**: ogni correzione a un lettore alza `VERSIONE_RIPASSO`; al primo giro dopo il deploy la cartella già completata rilegge **solo i file in errore** (non l'intera cartella), una volta per versione, salvando l'avanzamento ogni 10 file (un deploy lo interrompe e riprende). Un file «non quadrato» non si forza mai: si corregge il lettore e si ripassa. **Un guasto transitorio non è un errore del file**: timeout di una RPC Supabase, 5xx, memoria esaurita per l'OCR e il NUL nel testo (tolto dal payload in `_rpc`, Postgres lo rifiuta nel jsonb) restano in coda (`e_guasto_transitorio`, un solo meccanismo con i rinvii dello svuotamento: `rinvii` nel registro, al massimo `MAX_RINVII` volte, anche per le righe ERRORI nate così, rimesse in coda dal registro); poi il file resta in ERRORI col suo motivo, e il secondo giro non sposta niente. Il motivo di un F24 non quadrato porta righe lette, saldo stampato e `x1 d/c` (bordo destro in punti degli importi letti come debito e credito).
- **Cruscotto Agenti** (`/agenti`, voce «Agenti» ne «I controlli», solo admin, `routers/agenti.py`): la scheda «Settori» (`services/agenti_settori.py`, `GET /api/agenti/settori`, `@istantanea` persistente) dice per verbali, cedolini, bonifici, fatture, corrispettivi e F24 l'ultimo giro (da `sistema_stato`) e le **code ferme** con numero, link alla pagina e motivo: file in `ERRORI` per tipo, F24 non quadrati, chiusure RT scartate, verbali aperti senza driver, buste senza netto verificato, varianti da decidere, bonifici HR da associare, banca senza categoria, fatture aperte senza metodo, letture AI da rivedere; un conteggio che fallisce è `None` («Dato non disponibile»), mai zero. **Gli agenti AI non scrivono dati: scrivono proposte** (`services/agenti_proposte.py`, giro `agenti_proposte` ogni 30 minuti con lease, lotti da 10): leggono i file fermi in `ERRORI` della cartella unica e l'inbox senza categoria e salvano in `agenti_proposte` tipo dello smistatore, campi, confidenza e prove (JSON validato: tipo fuori lista = `non_riconosciuto`, importi in centesimi, codici tributo stringhe). Il titolare conferma (`POST /api/agenti/proposte/{id}/conferma`, «Conferma tutte le sicure» solo ad alta confidenza) e la conferma applica il **motore deterministico del tipo** (Drive → `drive_cartella_unica.rielabora_con_tipo`, lo stesso `_smista` con `tipo_rilevato_noto`; inbox → `upload_documento_automatico`, poi `categoria`/`processed` come la classificazione esistente), o rifiuta con motivo a chip (`tipo_sbagliato|dati_sbagliati|non_contabile|doppione|altro`); una proposta decisa non si riapplica (`gia_decisa`), un motore che fallisce la lascia aperta col motivo, ogni esito va in `audit_log`. **Un solo client**, `anthropic_llm_client.LlmChat` (timeout, 3 tentativi solo su 429/5xx/rete, `send_message_con_usage`): ogni chiamata in `agenti_ai_chiamate` (giorno di Roma, token), tetto `AGENTI_AI_TETTO_GIORNALIERO` (200) sulle chiamate vere, cache per SHA-256 + `VERSIONE_PROMPT` (la copia identica non richiama il modello); `AGENTI_AI=false` spegne il giro, senza `ANTHROPIC_API_KEY` non fa nulla e lo scrive nello stato (`sistema_stato`, `agenti_proposte`). Nessun altro lettore AI va aggiunto: quelli esistenti sono doppioni da ridurre (vedi «Aperto»).
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
  prova SumUp → Nexi → PayPal → mutuo → banca. «estratto conto» da solo non è un
  segno. Il PDF ufficiale BPM cambia impaginazione dal trimestre al 30/06/2026 (tre date — contabile, valuta, disponibile — poi l'importo: con la descrizione sulla stessa riga per le entrate, nelle righe dopo per le uscite; la data in coda è del movimento successivo): `parsers/estratto_conto_bpm_parser.py` le conosce entrambe, e la prova è l'archivio riga per riga (844 su 844 al 30/06/2026). All'import ufficiale anche le righe riconosciute solo per giorno, verso e importo (`accoppia`: la causale del PDF non ha il prefisso dell'export) si promuovono a ufficiali. La quietanza di rata «Mutui - Quietanza di pagamento_…» ha una colonna «totale netto»: si riconosce prima della guardia busta paga e va al modulo mutui. Non riconosciuto → cartella Errori col motivo scritto, **mai
  indovinato**: indovinare significa registrare le spese Nexi come uscite dal
  conto. Arretrato fermo per scelta del titolare: nella cartella unica un estratto (le sei fonti) con anno provato da
  nome o contenuto sotto `DRIVE_ESTRATTI_ANNO_MINIMO` (difetto 2025: l'anno prima si legge per riconciliare; 0 = nessun filtro) va in `ARRETRATO`, non si registra.
- **CSV «Corrispettivi» del portale AdE = dato provvisorio** (`corrispettivi_service.importa_csv_ade`, da Documenti > Import o `POST /api/corrispettivi/import-csv?dry_run=`): «Ammontare delle vendite» è l'**imponibile** (coincide al centesimo con l'XML di settembre) e «Imposta» l'IVA; il totale è derivato (`totale_derivato`) e contanti/POS restano `None`, mai per differenza. Le giornate già `definitivo_xml` non si toccano (si dichiara solo la discordanza di imponibile), una riga manuale è un conflitto, un invio = una riga (`id_invio`: secondo import `nuovi=0`, due chiusure dello stesso giorno restano due). Né Prima Nota, né giornale, né evento finché non arriva l'XML: data + matricola lo agganciano, `stato` diventa `definitivo_xml` e importi e quote si sovrascrivono (il CSV resta in `csv_ade` come storico).
- Corrispettivi: la via **primaria** è l'import degli XML (Documenti > Import, cartella unica); la copia serale RT è
  **supplementare**. Render non raggiunge la rete del locale, quindi `scripts/sync_rt_to_drive.py` gira sul **PC del
  titolare** (attività pianificata da `scripts/installa_sync_rt.ps1`, ogni sera e all'accensione) e copia in
  `DA ELABORARE` le giornate dall'ultima copiata in poi (ignora gli XML `ESITO`, SHA-256, copia atomica dei soli file
  nuovi). `RT_LOCAL_BASE_URL` e `RT_DRIVE_INBOX` sono variabili **locali**: mai su Render. **Se quel
  programma si ferma nessuno se ne accorge**: il gestionale vede solo l'assenza
  di file, e l'assenza di incassi somiglia a un locale chiuso. Il segnale da
  guardare è l'ultima giornata in `corrispettivi`, non la coda Drive: `fonti_ferme.py` avvisa (anche su
  Telegram, una volta) dopo **2 giorni d'apertura** senza chiusura RT, tolte le `chiusure_attivita`.
- **Protocollo personale e familiare** (`protocollo_personale.py`, `/api/protocollo-personale`, solo admin; collezione `protocollo_personale`, distinta dall'inventario Drive `protocollo_drive`): il foglio `REGISTRO_PROTOCOLLO` dell'xlsx del titolare su Drive si legge **per intestazione**, mai per posizione, con `POST …/import?file_id=` (`dry_run` per difetto, in sottofondo, stato in `sistema_stato`; secondo giro `nuovi=0`). Il numero `AAAA/NNNNNN` è unico e immutabile: lo stesso numero con un altro SHA-256 è `in_conflitto` e lo decide il titolare. **Niente si cancella**: `rimuovi` dà `stato='rimosso'` con motivo, l'import non lo riattiva né lo toglie perché sparito dal foglio. Ricerca AND senza accenti né maiuscole (targa anche con spazi), filtro anno (quello del documento se c'è, altrimenti del protocollo), snippet a segmenti `{t, hit}` (mai HTML), 200 righe per pagina; `testo_ocr` è payload e si legge per id, la ricerca lavora su `testo_indice` (primi 8.000 caratteri). Il testo di un PDF si aggancia solo se il suo SHA-256 è quello registrato. **Il ponte verso la contabilità è solo informativo e non ha viste proprie** (`documenti_collegati`: stessi SHA-256 nei documenti già in archivio e relazioni `entity_relations` con target `documento`): per ogni corrispondenza restituisce collezione, id e la **rotta della sezione esistente** (Tributi, PagoPA e cartelle, Verbali, Atti, Archivio documenti, `/fatture?invoice_id=`), mai i dati; non scrive relazioni, scritture né pagamenti. Una riga `personale_familiare` è `accounting_excluded`: nessun modulo contabile legge `protocollo_personale` (un test lo fissa), quindi Prima Nota, giornale, IVA, bilancio, incroci e alert non la vedono. L'OCR delle scansioni è lo stesso motore delle ricevute Mooney (`_righe_ocr_per_posizione`). Nei log solo contatori: il registro contiene nomi e codici fiscali.

### Drive, struttura canonica

- **Cartella unica** (decisione del 25/09/2026, sostituisce l'albero a 6 aree del §7-bis): «DATI SOCIETA CERALDI» con `DA ELABORARE | ELABORATE | ERRORI` (`GOOGLE_DRIVE_DATI_FOLDER_ID`); ogni file passa dallo smistatore di Documenti > Import, prima **sciolto nella radice** (il calderone del titolare) poi da `DA ELABORARE`, con le buste paga in testa (tre insieme, scritte una alla volta per dipendente e periodo), poi gli estratti conto, poi gli XML dai più recenti; ogni giro va avanti fino a coda vuota (lotto `DRIVE_CARTELLA_UNICA_BATCH`, difetto 100; fuori dalle buste l'elaborazione resta **un file alla volta**, ma i download dei successivi corrono in anticipo, `DRIVE_PRECARICA_PARALLELI` 4 e tetto `DRIVE_PRECARICA_MB` 48 sui byte scaricati e non ancora elaborati, sempre nell'ordine della coda: `precarica_in_ordine`), **Il tipo si legge una volta sola**: lo rileva il precarico (`DRIVE_PRECARICA_RILEVA`, difetto 1) mentre il file davanti si registra, e lo smistatore lo riceve gia' deciso (`tipo_rilevato_noto`); prima ogni file riconosciuto veniva letto due volte, OCR compreso. **Cache fra i giri**: id delle cartelle (1 h) ed elenco di ELABORATE (intero ogni 30 min, nel mezzo i soli file nuovi per `createdTime`; un candidato sparito si scarta al 404, mai ERRORI); la rilettura di ERRORI/ARRETRATO per le rimesse in coda ogni 10 min. **Ogni chiamata Drive riprova con backoff esponenziale** su 429, 5xx, 403 di quota e rete (`drive_download.riprova`), e `svuota` riprova un giro non partito (20, 60, 120 s). Un guasto passeggero di Supabase (5xx, schema cache) **non manda il file in ERRORI**: resta in coda, massimo 3 rinvii (`rinvii` nel registro), e le righe ERRORI nate cosi' si rimettono in coda da sole. I tempi per fase (`tempi_s`/`tempi_n`: elenco, scarico, hash, confronto doppioni, smista, sposta, registro, `attesa_precarico`) stanno in `sistema_stato` (`drive_cartella_unica_last_sync`): `attesa_precarico` alta = il collo e' il download, bassa = e' l'elaborazione.
  una copia byte-identica di un originale va nel Cestino (in `DOPPIONI` se il file è del titolare: Drive nega il Cestino al service account), «vedi documento» legge da `ELABORATE` e, per id, dai file fermi in `ERRORI`/`ARRETRATO` (`drive_cartella_unica.py`). Un file che nessun lettore riconosce va in `ARRETRATO` se è una stampa PDF di fattura XML, un formato non contabile o porta nel nome un anno passato (`motivo_fuori_contabilita`); gli altri restano in `ERRORI`. Dentro `GESTIONALE` restano solo lei e `FOTO E IMMAGINI` (immagini, cartella a parte): le cartelle dei canali sotto non esistono piu'. Le copie degli allegati email vanno in `ELABORATE` (`email_drive_archive.py`), mai in `DA ELABORARE`: lo smistatore le registrerebbe due volte. La pausa dell'import è `DRIVE_CARTELLA_UNICA_IMPORT=false`, **mai** togliere la cartella: le credenziali si provano su di lei.
- **Censimento doppioni** della cartella GESTIONALE (`drive_censimento_doppioni.py`, `DRIVE_CENSIMENTO_DOPPIONI`
  off|censisci|marca): copie esatte (MD5 + dimensione Drive) e file tecnici si **rinominano soltanto**
  («DUPLICATO DA ELIMINARE - …», «FILE TECNICO DA ELIMINARE - …»), li elimina il titolare; resta l'originale in
  `ELABORATE`, poi il più vecchio senza «(2)»; dai file che restano si toglie «(N)»/«(dupN)» (se il nome c'è già
  nella cartella diventa «nome - N»; radice `DRIVE_SIMULAZIONE_RADICE`). Lo smistatore non tocca i file marcati.
- **Apertura dell'originale: un endpoint e un componente** (DRV-04). `GET /api/originale/{tipo}/{id}` (`?indice=` per il secondo PDF di un verbale o l'allegato di una fattura, `?scarica=true`) oppure `GET /api/originale?drive_id=…|sha256=…`: solo admin, sola lettura, `app/routers/originale.py` sul servizio `app/services/originale_documento.py`, che trova i byte dove stanno (payload sul record e `blob_key` di `gestionale.blobs`, poi Drive per id con `drive_download.scarica_originale`) e risponde col tipo vero dei byte, `X-Originale-Fonte` e `X-Originale-Sha256`. Tipi: `f24`, `quietanza`, `cedolino`, `ricevuta_pagopa`, `cartella`, `documento` (deposito Documenti e allegati di posta), `documento_fiscale`, `atto`, `estratto`, `verbale`, `fattura` (XML senza busta .p7m), `allegato_fattura`, `fattura_emessa`, `bonifico`, `protocollo`, `drive`. Un lettore per famiglia (atti, estratti, cartelle, verbali, XML delle fatture) resta dov'è e il servizio lo **chiama**. Se l'originale manca è un 404 con `code` (`DOCUMENTO_NON_TROVATO`, `ORIGINALE_NON_DISPONIBILE` con l'elenco di ciò che si è provato, `ORIGINALE_NON_CORRISPONDENTE` 409), `message`, `details`, `correlation_id`: **mai un 200 vuoto**. Un `drive_id` si apre solo se è in `ELABORATE`, fermo in `ERRORI`/`ARRETRATO` (per id, mai per impronta: il titolare deve vedere il file per decidere la proposta dell'agente) o nell'inventario `protocollo_drive`, mai da un id qualunque; il **protocollo personale** si apre solo se il registro ha lo SHA-256 e i byte lo rispettano (altro file = 409, senza SHA-256 = non disponibile). I servizi che scrivono un link lo costruiscono con `url_originale()`; i vecchi indirizzi con link già in circolazione (`/api/f24-public/pdf/{id}`, `/api/f24-riconciliazione/commercialista/{id}/pdf`, `/api/documenti/documento/{id}/download`, `/api/fiscal/documents/{id}/content`, `/api/archivio-bonifici/transfers/{id}/pdf`) sono **alias 307** verso il canonico; gli altri (`/api/download`, `/api/documenti/originale`, `/api/cedolini/{id}/pdf`, PagoPA, atti, estratti, verbali, `xml-originale`) non esistono più. Nel frontend l'unico componente è `components/ApriOriginale.jsx` (`ApriOriginale` per un bottone, `VisoreOriginale` per l'elenco con un proprio stato «documento aperto»; `urlOriginale` in `lib/vista.js`): «Scarica», errore leggibile col riferimento, mai un indirizzo Drive aperto da fuori. Un file nuovo che apre un originale passa da qui: un `window.open` su un indirizzo di file o un secondo endpoint di apertura è un doppione. Prove: `tests/documenti/test_originale_documento.py`, `ApriOriginale.test.jsx`, `frontend/scripts/audit-originale.cjs`.
- Il protocollo Drive (`gestionale.protocollo_drive`, tabella relazionale, non
  `documents`) riconcilia Drive con l'inventario: file nuovo → riga nuova,
  cambiato → aggiornata, sparito → `stato='rimosso'` con la data. Le impronte
  collegano ogni file al documento **per contenuto**, mai per nome, e una
  stessa impronta in più posizioni non crea un secondo documento: le
  provenienze stanno in `source_occurrences`. **Due giri, un solo protocollo**: il
  completo (`sincronizza`: percorre tutto l'albero, ~23.000 file in memoria, vede
  anche i file spariti; spento per la RAM, `PROTOCOLLO_DRIVE_ENABLED=false`) e
  l'**incrementale** (`sincronizza_incrementale`, ogni 20 minuti, `PROTOCOLLO_DRIVE_INCREMENTALE`
  acceso per difetto): solo i file creati o modificati dall'ultimo giro riuscito (meno 10
  minuti), una pagina da 1.000 alla volta, percorso dalle cartelle fino alla radice; non vede
  i file spariti o spostati fuori (li segna solo il completo) e non rifa duplicati e
  collegamenti se non ha scritto niente. Un giro `in_corso` da oltre 3 ore e' di un processo
  morto e si chiude `interrotto`. Dopo ogni giro `riallinea_prove` riscrive (marcatore
  `prova_riallineata_il`) i documenti `senza_origine` il cui file e' ora nel protocollo: la prova
  la rifa il trigger `prova_origine` (`prova_calcola`, per MD5 o id Drive: si sceglie con le **stesse chiavi** che il trigger usa, `chiavi_prova`; un documento gia'
  riscritto e ancora senza origine non si ritocca). Senza il file nel
  protocollo la prova dice la verita' («nessun file Drive con la stessa impronta»), mai un'origine
  inventata: dal 17/09 al 01/10/2026 il protocollo non ha visto nessun file nuovo. **Il collegamento protocollo ↔ documento ha due
  chiavi**: l'impronta (`SQL_COLLEGA`, per MD5) e il `drive_file_id` scritto su F24 e quietanze
  (`gestionale.collega_protocollo_per_drive_file_id()`, SECURITY DEFINER perché `hr_app` non legge `documents`;
  `drive_protocollo.collega_per_drive_file_id`, idempotente): lo chiama lo svuotamento della cartella unica appena ha
  elaborato un file (`protocollo_collegati` nell'esito) e il giro incrementale dopo le impronte. Senza la seconda chiave
  le quietanze arrivate dopo il 15/09 restavano scollegate anche col file nel protocollo.
- **I canali Drive per sezione non esistono piu'** (DRV-16): moduli `drive_*_ingest`, router `/drive/sync|quadratura`,
  registro JSON delle cartelle e credenziali per canale tolti; lo smistatore non ne usava i parser. Restano la
  cartella unica e le foto ricette di Lotti; `fonti_ferme` e `cedolini_bloccati` (`cedolini_bloccati.py`) hanno un job proprio.
- **Corrispettivi: una riga senza `progressivo` né `id_dispositivo` non è una
  chiusura**, è una giornata senza documento, e il suo XML la **sostituisce** quando i contanti
  coincidono al centesimo (il totale no: lo storico sommava imponibile e IVA); due chiusure vere dello
  stesso giorno — chiavi XML diverse, anche sullo stesso RT — invece si sommano. Confonderli conta i
  ricavi due volte, o li raddoppia dentro una riga sola.
- Il parser legge il **non riscosso solo dalle voci che l'RT scrive** (`NonRiscosso*`, `PagatoNonRiscosso`); contanti + POS + non riscosso devono fare imponibile + IVA al centesimo, altrimenti la giornata si scarta con motivo (`non_riscosso_non_dichiarato` / `non_riscosso_non_quadrato`, file in ERRORI), mai `totale − (contanti + POS)`; nessun endpoint ricalcola il non riscosso. Le strade che scrivono `corrispettivi` sono **due**: `ingest_corrispettivo_parsed` (chiusure, con Prima Nota e giornale) e `importa_csv_ade` (riga provvisoria, mai Prima Nota); `CorrispettiviService` non esiste più.
- **«Processo interrotto durante il parsing» non è un errore del file**: è il
  marcatore che la ricostruzione scrive quando il worker muore mentre lo legge,
  e subito dopo sposta il cursore oltre. Quei file sono fatture **sane** da
  rileggere, non scarti: cercarli fra gli errori è cercarli nel posto sbagliato.
- **Un documento di un'altra sezione arrivato nel canale sbagliato non è un
  errore.** Una chiusura RT (`DatiCorrispettivi`) finita fra le fatture si
  riconosce dalla radice dell'XML — mai dal nome, che ha la stessa forma — e si
  consegna a `ingest_corrispettivo_parsed`, l'unico motore che la sa
  registrare. Trattarla da XML rotto la spediva in `Errori`, da dove nessun
  giro la ripesca: così 19 chiusure sono rimaste ferme e tre giornate di
  incasso sono rimaste fuori dai conti. Ogni punto che smista un esito deve
  conoscere tutti gli stati: quello sconosciuto cade nel ramo «errore».

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
  in `registrazione_contabile_esito`). Una fattura rifiutata per IVA non classificata rientra da sola dopo la
  classificazione (`registra_fatture_rimaste_fuori`, job bancario corto, 40 a giro); il resto del pregresso con
  `POST /api/piano-conti/registra-pregresso` (admin, in background). Non
  aggiungere altri punti di scrittura.
- **Ogni scrittura quadra Dare = Avere al centesimo esatto**, altrimenti non si salva: lo scarto fino a 0,01 € degli arrotondamenti IVA va su una riga propria «Arrotondamento IVA» (`arrotondamento: True`) nel conto CEE 53.01.29 (DARE eccede, provento) o 71.03.17 (AVERE eccede, onere), scritta da `_scrivi_movimento` per fatture, corrispettivi e scritture semplici (un punto solo); oltre 0,01 € la scrittura è rifiutata; lo storno riporta anche quella riga (titolare, 02/10/2026).
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
- **Competenza e pagamento sono due date**: il costo e l'IVA seguono la competenza (`data_competenza`, `periodo_iva_attribuito`, anno/mese della busta), il pagamento (F24, bonifico, assegno) chiude un **debito** e non genera mai un costo. F24, ritenute, contributi e saldo IVA non sono costi; il costo del personale è il lordo della busta per il mese di competenza, mai la data del bonifico. Un test end-to-end deve provare che un F24 o una ritenuta pagati non alterano `costi.totale_costi` del bilancio.
- Ammortamenti: scrittura semplice DARE 05.04.01 / AVERE 01.05.01; il
  risultato d'esercizio resta con segno, con guardia anti-doppia chiusura. Un cespite nasce da una riga fattura solo per parola intera («inCONDIZIONATo» non è un climatizzatore), mai da una nota di credito né da uno sconto.
- Ricavi: **solo corrispettivi RT**, all'imponibile e col filtro unico di `conto_economico_gestionale.py`, che dà anche il
  personale (lordo buste; contributi `None`). Le fatture ricevute sono costi; accrediti POS e payout non sono ricavi.
- Corrispettivi: in cassa entra **solo la quota contanti**, la quota POS va in Prima Nota Banca. Mai il
  totale; la chiusura POS reale **non riscrive** i contanti dell'entrata Cassa (il terminale si annota in `pos_reale_giorno`: sottrarlo dalla riga li rendeva negativi) e lo scontrino li legge dal corrispettivo. Mai il
  totale. Il **non riscosso** (sospesi, buoni, fattura) è ricavo ma non è denaro: terza gamba del DARE sui
  crediti (`01.02.01` → CEE 15.05), e solo se il documento lo **dichiara** e cassa + POS + non riscosso fa il
  totale al centesimo — mai per differenza, o un incasso non registrato sparisce lì dentro. Ignorarlo scarta
  la giornata intera, non una riga. Il totale del corrispettivo XML è l'**incassato** (contanti +
  elettronico): lo scarto verso imponibile + IVA senza voce dichiarata si scarta.
- **Il reimport di un corrispettivo non cancella una prova già arrivata**: il credito POS riconciliato con l'accredito resta (se la giornata è sostituita dall'XML passa alla chiusura nuova), e una chiusura del terminale non si aggancia mai a una riga ritirata (`FILTRO_CORRISPETTIVO_ATTIVO`). L'XML promuove anche la chiusura manuale serale con un totale digitato diverso da quello dell'RT, altrimenti i contanti entrano due volte in cassa. Con due attese Numia lo stesso giorno l'accredito non ne sceglie una (`attese_pos_ambigue`), e una chiusura corretta dopo l'accredito riapre le righe d'estratto che non quadrano più. Il CSV AdE segue l'anno attivo come l'XML.
- **POS dell'XML senza chiusura del terminale** (titolare, 02/10/2026): l'XML apre comunque il credito verso il gestore per il suo `pagato_elettronico` (`_apri_credito_pos_da_xml`: conto 15.07 di gruppo, `gestore=pos_da_xml`, `fonte_credito="xml"`, `senza_chiusura_terminale`, chiave `corr:<id>:banca_credito:pos_da_xml`: il reimport non ne scrive una seconda; mai da una riga storica o manuale). La chiusura del terminale lo **sostituisce** (`_sostituisci_credito_xml`: somma dei circuiti = XML al centesimo → riga XML `archived` con `sostituito_da`, la prova bancaria passa al terminale), altrimenti resta con `differenza_terminale`; l'accredito in banca al centesimo lo chiude (`attese_pos_numia_del_giorno`: prima il credito NUMIA, se manca quello da XML); Coerenza POS lo espone in `credito_pos_da_xml` e `fase2_crediti_xml_*`. Niente doppio credito e niente ricavo in più: il ricavo è già nel corrispettivo.
- POS: corrispettivo XML, chiusura terminale e accredito bancario sono tre
  fatti distinti. Coerenza XML↔POS (`controllo-due-fasi`): un giorno con POS e **senza XML** non è uno scarto — se l'RT l'ha chiuso col giorno dopo si confronta con quella chiusura (`_giornate_senza_xml`), altrimenti resta «attendo XML», fuori dal saldo (anche nel mensile). Un Numia senza chiusura letto dall'accredito vale per la fase 1, mai come prova contro BPM (`senza_chiusura_terminale`). SumUp corrente dall'API; Numia corrente dalla chiusura
  manuale serale; Numia storico ricostruito dagli export del gestore,
  deduplicati e accorpati per giorno. **Numia è dismesso dal 05/09/2026** (titolare, 28/09/2026): l'ultima vendita accreditata è del 04/09. Le chiusure Numia mancanti le ricostruisce dagli accrediti dell'estratto conto il job bancario corto (`ricostruzione_pos_estratto_conto.py`, salta i giorni già coperti); `fonti_ferme` misura il fermo Numia fino all'ultima vendita accreditata, non a oggi: un terminale spento non è una fonte ferma. Tutte e tre creano l'attesa bancaria;
  l'estratto conto può soltanto riconciliarla. Una vendita SumUp si conta una volta: la copia `LEGACY-SUMUP-…` (codice in `id_trans`) cede alla gemella dell'API (`transazioni_del_periodo`); le chiusure oltre la finestra dei 30 giorni si riallineano ogni giorno (`riallinea_chiusure_da_archivio`), e la risincronizzazione non stacca mai una vendita dal suo `payout_id` (l'API delle vendite non lo riporta).
- Accredito POS in banca riconosciuto solo con causale del circuito più il
  giorno operativo `DEL gg/mm/aa`; **Numia e Nexi sono lo stesso circuito**;
  commissioni e fatture del gestore escluse; attesa mancante o multipla →
  `DA_VERIFICARE`, la banca non crea la chiusura. L'accredito ricostruito
  dalla causale è **derivato**: l'export del terminale vince.
- Versamento/prelievo contanti: uscita Cassa ed entrata Banca (o viceversa), stesso `operation_id`, collegate da
  `trasferimento_collegato_id`, categoria `trasferimento_interno`. È **un'operazione della banca, non una riga
  d'archivio**: le copie (vecchio archivio, CSV, Enable Banking) fanno una coppia sola, il numero vero è il massimo
  per fonte nello stesso giorno e importo (`versamenti_contanti.py`); le gambe in più dei motori si tolgono per id. La «Contabile di filiale» BPM (ricevuta di sportello) è una prova, non un movimento: `contabili_filiale.py` la attacca alla riga d'estratto con verso, importo al centesimo, 0–3 giorni e natura (versamento o parola della causale), e la riprova nel job bancario corto.
  Lo stesso per `proiezione_bancaria.py` (stipendi — lo stesso bonifico nelle copie si riconosce dal riferimento `MB…`, e «ADD.SPE» è una commissione, non uno stipendio —, commissioni, PayPal, soci, **rata mutuo** sul 31.03.05 dal numero del mutuo, quote dalla quietanza o dal piano d'ammortamento a importo identico, altrimenti `da_verificare`) e per gli assegni, presi dal giro dei 30 minuti anche da CSV e banca diretta (identità = numero, riga `provvisoria` fino al PDF ufficiale). **Assegni: un motore solo abbina** (identità + importo al centesimo, `assegni_fattura_intent`/`assegni_auto_match`; anche `/incassa` esige l'importo del movimento): niente abbinamento per importo con tolleranza, niente schede nate da una causale (`arricchisci_pagamenti_banca`), niente cancellazione per filtro. Gli stati stanno solo in `constants/stati_assegno.py`: un numero uscito dal carnet non si elimina né torna «vuoto». Numero e carnet in `carnet_assegni.py`: 10 cifre (lo zero perso si rimette, un frammento no), carnet BPM da 10 da «…1» a «…0», ricavato dal numero e mai scritto. Collegare una fattura all'intero importo di un assegno (`PUT /assegni/{id}/fatture-collegate`) la dichiara pagata subito, con lo stesso motore del report titolare (`dichiara_pagamento_banca`, `pagamenti_dichiarati_titolare.py`): riga Prima Nota Banca `dichiarato_titolare`, poi solo il riscontro dell'estratto conto. Annullo, storno o un nuovo collegamento che sostituisce il precedente ritirano la dichiarazione non ancora provata (`ritira_dichiarazione_banca`) e riaprono la fattura; una dichiarazione già sostituita dalla riga con la prova bancaria non si tocca.
- **Mutui: la rata ha una prova, non un solo «Pagata»** (`routers/mutui.py`, `services/mutui_rate_dichiarate.py`). Prove in ordine di forza:
  riga di Prima Nota Banca `rata_mutuo` (`banca`), quietanza, estratto annuale della banca (`estratto_annuale`), dichiarazione del titolare,
  «Pagata» scritto sul piano PDF (`piano`, un'istantanea, non una prova); l'identità è **numero del mutuo + scadenza**, ma **l'importo pagato deve tornare**:
  `valuta_prove` confronta in `Decimal`, al centesimo, il pagamento letto (riga di banca, quietanza, estratto) con la rata, ammettendo lo scarto del tasso variabile
  entro `TOLLERANZA_IMPORTO_CENTS` (5,00 €; sul mutuo Retail lo scarto reale è 2,75 € costante) e mostrandolo (`differenza_importo_cents`). Oltre la tolleranza, o con un importo
  illeggibile da una parte, la rata è **«Da verificare»** con la differenza, mai «Pagata» (nemmeno per la dichiarazione o per il «Pagata» del piano), resta nel residuo e
  l'anteprima della dichiarazione non la include; due pagamenti distinti della stessa fonte che sommano la rata la reggono.
  `stato_piano` conserva quello del PDF, `stato` è l'effettivo e `prova` dice chi lo regge; il residuo si calcola sullo stato effettivo.
  **«Segna le rate passate come pagate»** (`POST /api/mutui/{id}/rate-dichiarate`, admin, `dry_run` per difetto, conferma forte con la frase dell'anteprima; `…/ritira`):
  le rate scadute senza prova diventano `pagata_dichiarata_titolare` in `mutui_rate_dichiarate` (una riga per mutuo e rata, con `dichiarato_da`, motivo a scelta e `storico`), mai dentro il piano
  (un nuovo PDF la cancellerebbe); le future restano fuori, una rata già provata non si tocca e una prova arrivata dopo **sostituisce** la dichiarazione (`sostituita_da_prova`, `assorbi_dichiarazioni_rate` da «Riconcilia»).
  Nessuna scrittura in giornale né Prima Nota, nemmeno per l'anno attivo: la dichiarazione non è un movimento e l'importo del piano è una stima; il movimento vero nasce dalla proiezione bancaria.
- **PayPal pagato dal conto (non da carta)**: la transazione si collega a mano a un addebito dell'estratto, quindi alla Prima Nota Banca (`GET/POST /api/paypal-statements/transazione/{id}/candidati-banca|collega-banca`, solo admin): candidati = uscite non collegate con lo stesso importo in euro al centesimo, da 3 giorni prima a 20 dopo, anche senza «PayPal» in causale; la scelta è del titolare (mai automatica), un movimento non candidato è 409, una transazione già provata non si ricollega; in valuta estera serve la gamba di conversione in euro. Scrive i due lati come il motore automatico (`tipo_riconciliazione=paypal_scelto_dal_titolare`). La pagina mostra una card per transazione a ogni larghezza (ID intero, mai colonne strette). **L'abbinamento PayPal ↔ banca non si fa a mano e non parte all'apertura della pagina**: il giro `paypal_automatico` (`services/paypal_automatico.py`, ore 3:20 e 14:20) sincronizza l'API Reporting (finestra chiusa 3 ore prima di adesso: PayPal pubblica con ritardo, un 404 non è un guasto e non sposta il checkpoint), abbina banca, fatture e posta. Un addebito SDD si abbina con importo al centesimo, segno e data entro 10 giorni se la coppia è biunivoca (soglia `SOGLIA_SCORE_MATCH_BANCA`); N addebiti e N pagamenti dello stesso importo si abbinano in ordine di data; l'accredito «BON.DA PayPal» si abbina al prelievo T04 (o, se non è nel report, all'incasso/rimborso positivo) entro 20 giorni, mai a entrambi.
- Stipendi, PayPal e assegni in Prima Nota Banca sono **riconciliati** solo quando il loro movimento sta nell'estratto ufficiale, con giorno e importo al centesimo (`riscontro_estratto_prima_nota.py`, job bancario corto): l'export CSV non basta, e il movimento resta libero per il motore degli stipendi. Prima Nota Banca non è la copia dell'estratto conto: una riga entra quando è nota la causale contabile oppure
  appartiene alle categorie bancarie senza documento ammesse dal codice. Anche i movimenti letti dalla banca (Enable Banking, `services/enable_banking.py`,
  flag `ENABLE_BANKING_ENABLED`, sessione cifrata col solo `session_id`) vanno in `estratto_conto_movimenti` (`accoppia`), mai in Prima Nota; entrano da soli alle 07:15 e 09:00 (`giro_automatico`), «Aggiorna ora» è in Prima Nota › Banca. **Spese di lite** (`atti_giudiziari.py`): sentenza, precetto, relata e attestazione entrano da Documenti > Import, originale in `gestionale.blobs`, apribile accanto al pagamento; un'uscita va nel fascicolo solo se la causale cita sentenza o R.G. o il titolare la dichiara (`fascicolo_dichiarato`), mai per importo o controparte, e in Banca è «Spese legali e contenzioso» su 71.03 (da confermare col commercialista).
- Riga bancaria canonica = riferimento esterno **oppure** fingerprint data+valuta+importo+causale+progressivo;
  due export **dello stesso conto** con parole diverse si confrontano per giorno, segno, importo e conteggio
  (`doppioni_estratto_conto.accoppia`), prima per **riferimento banca** (in ordine, due commissioni uguali si incrociano); `unifica_copie` (job bancario corto) lo rifà su **tutto** l'archivio: una riga per movimento, copia in quarantena, Prima Nota riagganciata. Assegni con numero diverso **non sono duplicati**; stesso numero e importo è lo stesso assegno, una scheda sola (`assegni_doppioni.py`, copia in `assegni_quarantena`), e la banca lega un addebito all'assegno solo se numero **e** importo coincidono. Un numero emesso non torna disponibile; annullo e storno hanno un motivo e riaprono le fatture; ogni modifica va nello `storico`. Le regole SDD
  creano un pagamento solo con identità, periodo e importo compatibili; altrimenti candidati.
- Categorizzazione movimenti banca: un solo motore, `app/services/categorizzazione_movimenti.py` (causali BPM non ambigue: F24,
  commissioni, utenze, fatture, POS, assegni, versamenti, PayPal, rata mutuo, CBILL AdE «Rateizzazioni AdE», saldo Nexi «Addebito carta
  di credito» — giroconto, non costo; la copia di un altro export presta la sua; `categoria_dal_collegamento`: uscita con una sola fattura o
  un solo dipendente → «Fatture»/«Stipendi», socio → «Finanziamento soci»; in **entrata** rimborso/Amazon «Rimborso», torte «Acconti
  clienti», mai ricavi). Sopra le parole chiave, **regole imparate** dal titolare (`app/services/regole_riconoscimento_banca.py`,
  `/riconciliazione/regole-banca`): un pattern estratto da una causale reale
  vince sul generico, ma un pattern di solo vocabolario bancario comune (es.
  "COMMISSIONI SU BONIFICI", senza un nome di fornitore) è rifiutato alla
  creazione. Eliminare una regola non tocca i movimenti già categorizzati. L'**indice operazioni** (`operation_index.py`, Movimenti › Classifica) è un'altra cosa: una natura senza documento (commissione, trasferimento, altro) si applica anche ai movimenti della stessa **famiglia di causale** (`famiglia_causale`: il testo prima del trattino, senza numeri), solo dopo averli visti e spuntati; una natura con documento (fattura, cedolino…) è di un movimento solo.
- **«Movimenti da insegnare» (Regole banca)**: il motore unico riconosce da solo l'«ADDEBITO NEXI - SDD CORE» (= addebito carta, riscontro con l'estratto Nexi del mese prima) e i giroconti della società («Giroconto», «Mastercard SumUp», «BON.DA ceraldi group srl» → categoria `Giroconto`, mai un fornitore). Per il resto la pagina non chiede «a chi appartiene»: `GET /api/regole-riconoscimento-banca/proposte/{id}` (sola lettura, admin) dice cosa legge il motore e elenca i candidati per importo al centesimo (verbali, cartelle, fatture non pagate), e la scelta si fa in «Classifica e collega»; la regola per fornitore resta il modo di insegnare una famiglia di causali.
- Pagamenti stipendio via nome: regola in «Personale». Qui vale solo il
  corollario bancario — un professionista omonimo di un dipendente, o un
  pagamento occasionale a lui, non entra nel fascicolo stipendi
  (`_ESCLUSIONE_RE` in `hr_pagamenti_deposito.py`).
- Le simulazioni non scrivono sul consuntivo. La chiusura d'esercizio richiede
  checklist, anteprima, conferma forte, audit e rollback.
- **Area Commercialista** (`commercialista_pacchetto.py`, `/api/commercialista/pacchetto`, `/invia-pacchetto`, solo admin): il periodo è un intervallo `dal`/`al` (`intervallo_periodo`, un punto solo) e ogni scheda (banca, PayPal, SumUp, bonifici, corrispettivi, fatture per metodo, F24, stipendi, cassa, carnet, presenze) legge le sue fonti esistenti; una voce vuota o guasta si dichiara, mai riempita. Un invio = una email con un allegato per voce (`invia_email`), registrato in `commercialista_invii`. Le presenze le costruisce `hr/services/presenze_consulente.py` e il registro è uno solo, `presenze_invii`: un mese già inviato non parte due volte senza «Rinvia». L'IBAN esce sempre mascherato e il carnet assegni non ha colonna «Beneficiario» (mancante = «Da collegare»).
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
  stesso evento **dopo** il motore IVA, che subito ricalcola i campi IVA (`iva_detraibilita.py`); l'arretrato lo smaltisce il job bancario corto.
- Regola del 15: operazione del mese precedente ricevuta **e** annotata entro
  il 15 → liquidazione del mese precedente, solo nello stesso anno solare.
  Ricevuta dopo il 15 → mese di ricezione. Operazione dell'anno precedente →
  **mai** retroattribuzione a dicembre: è un blocco, non un avviso.
- **Codici IVA**: 6001–6012 sono i mesi gennaio–dicembre (6012 = dicembre), 6031–6033 i trimestrali, 6013 l'acconto di dicembre, 6099 il saldo annuale di dichiarazione. Il calcolo di 6013 (metodi storico, previsionale, analitico, soglia minima, esclusioni) e di 6099 (con maggiorazione dell'1% al mese dopo il 16/03) **non esiste ancora**: le soglie e le percentuali si prendono dalla norma, non si inventano (vedi «Aperto»). Credito e debito di dicembre passano a gennaio; oggi il riporto è solo mese su mese (`_credito_precedente`), senza credito da dichiarazione né compensazione orizzontale (soglia 25.000 € con visto di conformità).
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
  `218.058,92`. La prova è l'aritmetica del quadro VP **a segni** (credito negativo): `VP6 = VP4 − VP5`,
  `VP14 = VP6 + VP7 − VP8 − VP9 − VP10 − VP11 + VP12 − VP13`; un periodo che non quadra **non viene
  depositato** e non fa da fonte. VP13 si legge solo a destra (a sinistra c'è «Metodo»). Una comunicazione
  ritrasmessa (protocollo più alto, anche in `LIPE_2024_Itrim_<prot>.pdf`) sostituisce la precedente.
- Il confronto mensile gestionale ↔ LIPE ↔ F24 è
  `GET /api/iva/confronto-commercialista/{anno}`: non aggiusta niente, dice
  dove si diverge. Un mese che non sappiamo calcolare è un «non lo so», non
  uno scostamento; una LIPE **a credito** non deve avere nessun F24, e il
  caso da segnalare è l'opposto.

### F24, tributi, dichiarazioni

- F24, righe tributo, quietanza e movimento bancario sono entità distinte. La quietanza documenta il pagamento ma **non
  sostituisce la prova bancaria** né ricostruisce il modello (senza modello → alert «F24 mancante»); stato e residuo **per
  riga tributo**. **Un solo motore F24 ↔ banca, a livelli** (`riconcilia_f24_banca` in `f24_controllo_incrociato.py`, job
  `f24_quietanze_banca`, arrivo di quietanza o modello con `riconcilia_f24_arrivato`): ogni coppia pagamento ↔ addebito ha
  `livello` e `motivazione`. **CERTO** = importo al centesimo, addebito entro 2 giorni lavorativi (festivi in
  `calendario_lavorativo.py`), causale di delega e, per una quietanza, «DATA INCASSO» (troncata → copia in quarantena) = data
  della quietanza; un modello senza quietanza è provato da un addebito certo, uno con quietanza dall'addebito della quietanza se il
  saldo torna. **PROBABILE** (causale senza data d'incasso, o più candidati: si mostrano tutti), **PARZIALE** (differenza sotto 5 €, con la
  differenza), **NESSUN_MATCH** (con «estratto del periodo presente sì/no»: senza estratto non si dice che il pagamento manca),
  **MOVIMENTO_ORFANO** (alert, quietanza da riscaricare). Solo il CERTO scrive il pagamento; gli altri una relazione `pending` in
  `entity_relations`. Protocollo = giorno d'invio; stessa riga due volte nel giorno → alert.
- **PROBABILE e PARZIALE li chiude solo il titolare**: `POST /api/f24-riconciliazione/quietanze-banca/{id}/conferma` (admin; `id` del modello o della quietanza) sceglie **fra i candidati del motore** (altro movimento = 409) con un motivo a chip (`MOTIVI_CONFERMA_TITOLARE`, «altro» con testo) e scrive con lo stesso writer del CERTO; relazione `confirmed` con `actor=titolare` e motivo, per il PARZIALE `differenza_banca_cents` registrata, mai un conguaglio; nel frontend l'unico componente è `ConfermaAddebitoF24`. **`f24.acquisito` nasce in `salva_f24`**, una volta per modello alla prima scrittura (payload di `f24_evento_acquisito.costruisci_evento_f24_acquisito`, scadenza da `scadenza_modello`), mai da una quietanza; pregresso con `POST /api/admin/f24/ripubblica-evento-acquisito` (`dry_run`, in sottofondo, salta i modelli già provati in banca). La quietanza si riconosce per **SHA-256** (`pdf_hash`), l'MD5 sta in `pdf_hash_md5` solo per la copia identica su Drive (una riga con l'MD5 in `pdf_hash` si promuove alla prima rilettura). La quietanza abbinata al suo unico modello segna la scadenza del calendario fiscale (`_marca_scadenze_calendario`, `completato_da=quietanza_f24`, upsert per id e anno): non è una scrittura contabile.
- Il saldo F24 non è mai un costo: ritenute 1001/1002/1012, addizionali 3802/3847/3848 e quote a carico del lavoratore
  sono debiti verso enti. La sezione INPS non è tutta deducibile: la quota datoriale viene dalle paghe.
- RC01 regolarizza un periodo precedente: non è costo del mese in cui si paga, e si collega al DM10 di quel periodo senza sommare due volte i tributi.
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
- **I righi delle dichiarazioni si leggono per posizione** (`services/dichiarazioni_quadri.py`: VL32/VL33/VX1/VX2, RN1/RN2/RN17, IR26/IR27, esito ISA), perché il livello testo accoda i valori in fondo alla pagina senza etichette; casella vuota = `None`, mai 0; due valori diversi = `campi_da_verificare`. Prove in `fiscal_evidence` (id stabile), riepilogo in `fiscal_documents.quadri`; le coordinate (`layout_words`) si conservano solo sulle pagine dei quadri e della LIPE. Ripasso: `POST /api/fiscale/dichiarazioni/estrai-quadri` (admin, `dry_run`), che rilegge le coordinate dall'originale se lo trova. Un «Esito versamento unificato» (protocollo senza righe) non è una quietanza.
- **Incroci fiscali in un motore solo** (`services/incroci_fiscali.py`, `GET /api/fiscale/incroci`, giro `incroci_fiscali` alle 06:50): LIPE canonica (solo `quadratura_ok`, non sostituita) contro F24 60MM dello stesso anno/mese (soglia 1,00 €: OK, MANCANTE, PARZIALE, ECCEDENTE), IRAP IR26 contro 3800, IVA annuale VX1 contro 6099, comunicazioni 54-bis per codice e anno. Alert solo con `genera_alert` (`IVA_PAGAMENTO_MANCANTE_O_PARZIALE`, `IRAP_SALDO_MANCANTE_O_PARZIALE`, `IVA_ANNUALE_SALDO_DA_VERIFICARE`, `COMUNICAZIONE_54BIS_NON_PAGATA`), chiusi dal motore quando la condizione non vale più; `POSSIBILE_ERRORE_PERIODO_IMPUTAZIONE` e `POSSIBILE_COMPENSAZIONE_6099` (±3,00 €) restano indizi, mai alert. Un VP14 non letto è «non determinabile», mai zero; F24 non quadrati e LIPE non quadrate restano fuori con il motivo.
- **Viste per id** (solo admin, sola lettura): `/fiscale/f24/:id` (`F24Scheda`), `/fiscale/tributi/:codice` (`TributoCodice`), `/personale/cedolini/:id` (`CedolinoScheda`), `/protocollo/AAAA/NNNNNN` (`ProtocolloScheda`, anche `/protocollo/:id`). Leggono i motori che ci sono, non ne hanno di propri: `/api/fiscal/f24-rows` e `/api/f24-riconciliazione/quietanze-banca` (livelli CERTO/PROBABILE/…), `/api/f24/tributi` con `/api/fiscale/incroci` (60MM↔LIPE, 3800, 6099), `GET /api/cedolini/{id}` (`cedolino_scheda.py`: netto, `netto_fonte`, canale, versioni e decisione di `cedolini_versioni`, `/versioni` resta fisso), `/api/protocollo-personale/{anno}/{progressivo}`. I vecchi `/f24/:id`, `/tributi/:codice`, `/cedolini/:id` li rimanda `LegacyRouteResolver` (un solo punto di compatibilità, `main.jsx` non cresce: tetto di 40 `path:`). Il filtro anno è quello globale (`useAnnoVista`, `?anno=tutti` nell'indirizzo). Un valore mancante è «Dato non disponibile», mai zero (`lib/vista.js`; 0 sulle colonne di importo è «—»). **L'originale si apre solo con `ApriOriginale`** (vedi «Apertura dell'originale»). La legenda in italiano semplice sta in `lib/legendaRegole.js`, la stessa fonte delle etichette dei badge. E2E con API finte: `frontend/scripts/audit-viste-fiscali.cjs` e `audit-originale.cjs` (job «browser»).
- **Situazione fiscale legge il registro unico F24** (`registro_fiscale_f24.py`), mai l'indice Excel su Drive; un quadro del 770 caricato da solo (`componenti_770.py`) si aggancia al 770 intero per «Identificativo dichiarazione», mai per nome o importo.
- **Ricevute di pagamento pagoPA** (`pagopa_receipts.py`, un lettore per famiglia: BPM, Mooney via OCR, «Attestazione di pagamento» AdER): ogni voce «etichetta: € importo» si legge e la somma deve fare il totale al centesimo, altrimenti resta `DA_VERIFICARE` (una voce nuova non si ignora; «Importo originario» non è una voce). Stesso IUV, data e importo = stesso pagamento, un secondo file non duplica. La ricevuta non dice **che cosa** si è pagato: la natura (tributo, rata, diritti/oneri, sanzione) la sceglie il titolare (`PUT /api/pagopa/ricevute/{id}/natura`) o la dicono i soli diritti di notifica; la Mooney si aggancia al PayPal per ID transazione, mai per importo.
- **Cartella di pagamento** (`cartelle_pagamento.py`, Documenti > Import, pagina PagoPA): fatto autorevole, apre subito l'attesa `CARTELLA_DA_PAGARE`. Il termine è 60 giorni dalla **notifica**, che nel PDF non c'è: la scadenza resta vuota finché il titolare non dice la data. La chiude solo la ricevuta con lo stesso IUV e importo al centesimo (altrimenti `DA_VERIFICARE`); il verbale si aggancia solo se univoco per numero e targa. La data di notifica la scrive da sola il giro `pec_cartelle_notifiche` (ogni 6 ore, cerca in tutta la casella le PEC «Notifica cartella di pagamento n. <20 cifre>», sola lettura): la riga in archivio ha un id UUID e il numero in `source_fact_id` (`cartella:<numero>`), quindi si cerca per `source_fact_id`, mai per solo `id`.
- Il catalogo dei codici tributo è consultivo: una ricerca non crea F24, pagamenti o scritture. **Le
  descrizioni vengono solo da `services/codici_tributo_f24.py`**, causali INPS comprese (RC01 è la
  regolarizzazione, non gli artigiani); `services/codici_tributo_db.py` aggiunge le scadenze. Parser e router
  non tengono tabelle proprie (`test_codici_tributo_registro_unico.py`); `test_codici_tributo_coerenti.py`
  fissa la fonte AdE: IRES 2001 acconto I, 2002 acconto II, 2003 saldo; 3802 sostituto, 3801 autotassazione;
  TEFA/TEFN/TEFZ (Ris. 5/E 2021). Un testo «di produzione» non vale come fonte: su entrambi era sbagliato.
- **Piano tributi** (`services/piano_tributi.py`, `/api/f24/piano-tributi`): le voci ricorrenti
  del titolare aprono un'attesa per periodo; la soddisfa solo l'addebito in banca, la quietanza
  la lascia `DA_VERIFICARE`. Legge il registro unico F24, non ne tiene un secondo; l'importo
  viene dal modello arrivato, mai stimato. 3802/3848 sono rate del saldo dell'anno prima.
- Il **periodo di riferimento di un tributo sta sulla sua riga** (`anno`, `mese`), non sul modello né nella data di pagamento;
  l'IVA mensile sono i codici 6001–6012. «00MM» è il mese, «NNRR» la rata: «0101» è la rata unica, mai gennaio (`tributi_engine.mese_da_rateazione`). Una riga d'avviso non trovata mostra gli indizi `POSSIBILE_COMPENSAZIONE_6099` / `POSSIBILE_ERRORE_PERIODO_IMPUTAZIONE` (±1,00 €), mai un aggancio. **Nessun F24 ricostruito in automatico.** Nessun pagamento automatico è autorizzato.
- **Dilazione INPS** (`dilazioni_inps.py`, PEC INPS con `Allegato.zip` o Import): il piano apre una rata per scadenza; la paga la quietanza con sede, causale,
  matricola, periodo e importo al centesimo, dopo la domanda, in ordine; l'addebito è quello della quietanza. Rata scaduta senza quietanza → alert.
- **Tributi** (`tributi_per_codice.py`, `/api/f24/tributi`, pagina `/tributi`): sola lettura per codice e periodo sul registro unico; colonne inviato dal commercialista, quietanza, ravvedimento (solo periodi con sanzione/interessi nella delega), credito compensato, ritenute attese; resta = max(modello, attese) − pagato.
- **F24 a saldo zero** = pagato tutto in compensazione, mai scartato: `saldo_quietanza_cents` legge lo 0 (non «saldo non letto»), `pagamenti_da_quietanze` lo marca `compensazione_totale`, il riscontro banca lo mette in `compensate_saldo_zero` (nessun addebito atteso), l'import lo salva `QUIETANZA_COMPENSAZIONE_TOTALE` senza alert bloccante, Tributi lo conta in `compensazione_cents` (stato COMPENSATO). Un PDF senza righe tributo (ricevuta mutuo/bonifico) non è una quietanza: l'import lo rifiuta (`NON_QUIETANZA_F24`).
- **Registro versamenti** (`registro_versamenti_f24.py`, `/api/f24/tributi/versamenti`, tab della pagina Tributi): il Cassetto interno, fonte solo le quietanze. Per anno di versamento: codici con debito/credito mese per mese e mesi di riferimento «non pervenuti» (codici versati ≥3 mesi, periodo scaduto il 16 del mese dopo); crediti per codice+anno con gli F24 che li hanno usati; deleghe con origine (`origini_documento`: Posta, Drive, Caricato).
- **Alert «F24 in scadenza»** (`FiscaleSentinella`): nessun F24 ha `data_scadenza`, la scadenza è la più vicina fra le righe a debito dalla regola del codice (`scadenza_modello`, mai inventata) e l'alert parte a 15 giorni solo per un modello `da_pagare` **senza** quietanza in archivio (chi ha la quietanza ha già versato, anche se la banca non l'ha ancora provato).
- **Alert `F24_PAGAMENTO_IN_RITARDO`** (`f24_scadenze_notifiche.segnala_f24_in_ritardo`, dentro il job `f24_scadenze_check` delle 08:00/14:00, mai un giro a parte): il giorno DOPO la scadenza (`data_scadenza` del modello o regola del codice, festivi inclusi) per un modello a debito senza quietanza né addebito CERTO; il messaggio porta i giorni di ritardo e il ravvedimento dello scadenzario (`ravvedimento_atteso_modello`: sanzione ridotta per fascia + interessi legali, INPS/INAIL «da verificare») e si aggiorna ogni giorno sullo stesso alert; si chiude da solo con la quietanza o l'addebito certo; un alert ignorato non rinasce; oltre 365 giorni (`FINESTRA_RITARDO_GIORNI`) i modelli storici si contano, non si segnalano (titolare, 02/10/2026).
- **Scadenzario tributi** (`scadenzario_tributi.py`, collezione `scadenzario_tributi`, `/api/f24/tributi/scadenzario`, tab Scadenzario): per ogni riga a debito di ogni quietanza, scadenza (modello del commercialista, altrimenti regola del codice con festivi e proroga di Ferragosto; senza regola resta vuota), giorni di ritardo, ravvedimento confrontato per delega+periodo con quello di legge (sanzione 30% previgente / 25% dal 01/09/2024 ridotta per fascia; interessi legali per anno, tabella `TASSI_LEGALI` da aggiornare ogni gennaio). Esiti PUNTUALE, RAVVEDUTO, RAVVEDIMENTO_INSUFFICIENTE, RITARDO_NON_RAVVEDUTO, RITARDO_DA_VERIFICARE, SCADENZA_NON_DETERMINATA. Aggiornato a ogni quietanza importata e dal giro F24 dei 30 minuti (che allinea anche le quietanze a saldo zero già importate).
- **Avviso bonario**: `controlla_avviso` aggiunge per riga il verdetto dello scadenzario (`verdetto_riga`: NON_DOVUTO con la prova, DOVUTO, DOVUTO_DIFFERENZA, DA_VERIFICARE; data AdE diversa dalla quietanza → nota di sgravio) e il verdetto dell'avviso («Avviso n. … non dovuto: F24 pagati regolarmente con sanzioni e interessi»). La lettura automatica del PDF dell'avviso non c'è ancora: manca un esempio reale.
- **Termini di recupero** (`termini_recupero.py`, `GET /api/f24/tributi/termini`, tab della pagina Tributi, solo admin): sola lettura sulla vista `verifica.tabulato_tributi_termini`, **unica fonte dei termini** (il servizio non applica nessuna regola di legge: porta l'importo in centesimi, conta i giorni sul fuso Roma, ordina). Lo schema `verifica` non e' leggibile dal ruolo applicativo: l'ingresso e' `public.gc_termini_recupero()` (segreto runtime come le altre `gc_*`), letta da `SupabaseRuntimeDatabase.termini_recupero`; la vista costa ~5 s, quindi `@istantanea`. Predefinito: tributi senza versamento (`MANCANTE`, `F24_SENZA_QUIETANZA`), prima gli «ancora recuperabili» dalla data piu' vicina; sotto 120 giorni la riga e' rossa **e** porta la scritta; senza termine = «da verificare», mai «recuperabile». I termini sono **indicativi** (atti gia' notificati, sospensioni, denuncia del lavoratore, ruoli AdER 2020-2021 con +24 mesi): il banner «da confermare con il commercialista» e' fisso.
- **Doppio pagamento F24** (`services/f24_anomalie.py`, motore `tributi_engine.rileva_doppio_pagamento`): una riga per coppia in `f24_anomalie_doppio_pagamento` con `stato` (`da_verificare`, `confermato_doppio_pagamento`, `non_duplicato`, `rimborsato_compensato`, `chiuso_dal_consulente`) e `storico`; il titolare cambia stato con `PUT /api/f24-analisi/doppi-pagamenti/{id}/stato` (motivo obbligatorio), l'alert `POSSIBILE_DOPPIO_PAGAMENTO_F24` si chiude quando lo stato esce da `da_verificare`, una coppia decisa non si riapre. Controlli di forma (`controlli_f24`: Regione/Comune assenti o fuori tabella, riga INAIL incompleta, causale INPS sconosciuta) in un solo alert `F24_CONTROLLO_DA_VERIFICARE` per modello. Il motore F24 legge la **vista canonica** delle righe (`normalize_f24_evidence_rows`), mai le sezioni grezze: un modello importato prima dei fix di lettura si legge giusto lo stesso. Debito e credito di una riga si decidono dal **bordo destro** dell'importo (le colonne sono allineate a destra: «5.024,76» parte più a sinistra di «667,40»).
- **Ritenute**: le chiude anche la sola quietanza (1040 del periodo: riga uguale e univoca, o somma delle righe = totale del periodo; due candidate → nessuna scelta); al primo versamento Telegram «Ritenuta pagata» col protocollo, una volta (`avviso_versamento_at`), muto oltre 45 giorni.
- **Il periodo del 1040 di una parcella con ritenuta è il mese del PAGAMENTO al professionista** (`data_pagamento` della fattura, solo se `e_pagata`), versamento entro il 16 del mese dopo (`ritenute.periodo_da_pagamento`); finché la fattura non è pagata periodo e scadenza restano vuoti (`in_attesa_pagamento`), mai il mese della fattura, e nessun F24 si aggancia; il periodo si riallinea dalle fatture nel giro F24, all'import delle quietanze e all'apertura della pagina Ritenute (`_allinea_periodo_al_pagamento`). Le descrizioni e le scadenze di 1001, 1012, 3802 e DM10 (tutti al 16 del mese successivo) sono quelle AdE in `codici_tributo_f24.py`, confermate dal titolare il 02/10/2026 (`test_codici_tributo_coerenti.py` le fissa); un codice fuori dal registro versionato blocca la `journal_proposal` (`CODICE_TRIBUTO_NON_VALIDATO`).
- **F24 del 2018-2019 senza protocollo** (modulo con i dati sovrapposti, nome `NN_…_A0GHE_…`): `parse_quietanza_f24` legge data (una cifra per casella) e totale in alto, righe per coordinate, mese scritto «00MM». Senza protocollo la quietanza è il suo contenuto (`firma_contenuto`: data, saldo, righe): la stessa stampata due volte è una sola. Un guscio vuoto già in archivio (stesso `pdf_hash`, nessuna riga) si rilegge sul posto, mai «già importato».
- **F24 ravveduto** (`f24_ravvedimento.py`): l'originale del commercialista resta; modello o quietanza con sanzioni gli si affianca
  (RAVVEDIMENTO) se ogni riga codice+periodo torna al centesimo, o è maggiore solo nel periodo sanzionato (interessi cumulati).
- **Un F24 è il suo contenuto fiscale** (contribuente, data di versamento, saldo, righe codice/periodo/importo), non il PDF: `salva_f24`
  non crea un secondo modello da un'altra copia del file e ne annota la provenienza (`f24_doppioni.py`). I doppioni vanno in quarantena
  reversibile (`status=eliminato`, `motivo_quarantena`, `doppione_di`), la copia pagata in banca resta; `F24_QUARANTENA_DOPPIONI` accende il giro. **Modello e quietanza si confrontano riga per riga sulla stessa vista** (`normalize_f24_evidence_rows`): «01 / 01 2021» è la rata unica, mai gennaio, e una riga INPS (sede, causale, matricola) che il modello del commercialista lascia in Erario col codice = anno torna in INPS. Senza questi due riallineamenti la quietanza restava «non corrispondente» a un modello uguale.
- **Lettura degli importi F24** (`parser_f24._importo_cents_da_token`): certi PDF perdono la virgola nel livello testo, quindi «1.03712» è 1.037,12 e «99035» è 990,35 (senza virgola le ultime due cifre sono sempre i centesimi; letto come 1.037 × 100 il saldo sbagliava di centinaia di migliaia di euro). Il codice 4xxx (es. 4731) è un codice Erario come 1xxx/2xxx; il periodo INPS può essere scritto unito («072022») e il comune dei tributi locali in una parola («F839»). Una delega su più pagine **senza «MOD NUM»** ha un saldo per pagina (si confronta pagina per pagina, mai la somma di tutto col saldo della prima). Un F24 che non quadra non si salva, e l'errore elenca saldo stampato e righe lette (`f24_canonico._dettaglio_quadratura`): la causa si legge da lì, non riaprendo il PDF. **Il reimport dello stesso modello rinfresca le righe e non riscrive lo stato**: un modello già pagato in banca o in quarantena resta com'è (`f24_canonico`). Un modello che è esso stesso un ravvedimento (righe 89xx/19xx, `e_modello_di_ravvedimento`) non fa da modello del commercialista: la sua data è il giorno del versamento, mai la scadenza.

- **Indice relazionale e relazioni documentali** (`indice_relazionale.py`, `relazioni_documentali.py`, `/api/indice-relazionale`, solo admin): l'indice è una vista di sola lettura su `entity_relations`, non un secondo registro (filtri anche per `documento` = `drive_id`; il riepilogo dice per regola e per motivo). Export csv/json/xlsx **riproducibile** (righe per chiave, nessuna data di generazione, importi `Decimal`, gg/mm/aaaa in csv/xlsx). Un originale su Drive è la relazione `has_source_document` verso target `documento` (id = `drive_id`); `POST …/relazioni-documentali/backfill` è `dry_run` per difetto, in sottofondo (`sistema_stato`, chiave `relazioni_documentali`), a lotti (`limite`, si ripete finché `restanti`=0), il secondo giro dà 0, una relazione revocata non rinasce. Fonti, lette una volta (un prefetch): `drive_file_id` del documento (se c'è vale solo quello); poi, dove manca, l'**impronta del file** (SHA-256 col registro `drive_cartella_unica` solo in `ELABORATE` — `registro_originali.py`: fra copie identiche l'originale è l'unico non `gia_presente`, altrimenti `pending` `impronta_su_piu_file_identici`; MD5 col protocollo, solo per ritrovare la copia identica) su fatture, F24, quietanze, buste, inbox, bonifici, ricevute PagoPA, cartelle, estratti conto (originali, Nexi, PayPal, SumUp, mutui); i `collegamento_*` del protocollo verso entità vive (le id HR si verificano in `hr.app_cedolini`/`app_bonifici`, chiave `id` testo; se l'HR non risponde si dichiara `non_verificato`, non si scarta); le **occorrenze** (`source_occurrences`: copie dello stesso contenuto che il motore ha visto arrivare, confermate, non ambiguità). Mai per nome o importo. `pending` (DA_VERIFICARE): entità con più file non attestati, file con più fatture/F24/quietanze; busta e cedolino HR possono avere più file e condividerli (documento combinato). **Il `drive_file_id` del cedolino** si scrive (solo con `dry_run=false`, mai sovrascritto) quando l'originale è uno: l'impronta propria della busta o l'unico file in cui compare; con più copie senza impronta propria resta vuoto (`drive_file_id_da_verificare`) e le copie restano relazioni. **Collegamenti del protocollo verso entità sparite** (la quietanza fusa con una copia ha cambiato id): `POST …/protocollo-collegamenti/bonifica` (`protocollo_collegamenti.py`, `dry_run`, per `drive_id` e solo se il collegamento è ancora quello letto) riaggancia solo con MD5 del file fra le occorrenze (o la propria impronta) di **una sola** entità viva, o con `doppione_di` dichiarato; zero o più candidati si elencano e non si toccano.

## Personale: un solo sistema per funzione

- **L'anagrafica HR comanda** (`hr.app_dipendenti`): Lotti ne legge una proiezione
  (`sincronizza_operatori_da_hr`), il gestionale si riallinea a HR. Un solo stato del rapporto: `attivo` |
  `cessato` con data e motivo; la cessazione revoca il PIN. `PUT /dipendenti/{id}` aggiorna **solo i campi
  inviati**. La revoca, la chiusura dei contratti, il rifiuto delle richieste di assenza future e
  l'annullamento delle partite stipendio residue stanno tutti in un punto solo, `on_dipendente_cessato`:
  le pagine si limitano a pubblicare `dipendente.cessato`, non ripetono la pulizia a mano.
- **Un PIN per persona, nella scheda HR**: vale per il portale e per firmare in Lotti (bcrypt più impronta
  HMAC; mai due persone in forza con lo stesso PIN; mai un cessato). Il **PIN amministratore è uno solo
  per ERP, Menu, Lotti e HR** (`PIN_HASH_ADMIN`, `app/services/admin_pin.py`) e si digita **solo nel login ERP**:
  HR, Lotti e Menu leggono quel cookie (`group_session.py`, `/auth/session`), senza login admin proprio (PIN, password,
  Google). Il login email + password (`/api/auth/login`, `ADMIN_PASSWORD_HASH`) non esiste piu'. Il token ERP porta un `sid` stabile nei rinnovi; i token derivati lo copiano e il logout lo revoca per
  tutte (`token_di_gruppo_ammesso`): un token admin non nato da lì non vale, il PIN personale del titolare è da operatore.
- **Cedolini**: il gestionale li scarica (Drive e posta) e ne ricava la Prima Nota salari; l'archivio che
  si vede è **solo in HR** (`hr_cedolini_deposito`, richiamato dopo ogni scrittura, dedup per chiave o per
  CF+anno+mese+tipo, mai sovrascrittura; 13ª e 14ª restano buste distinte). Una 13ª/14ª salvata come «mensile» nell'ERP si riconosce solo rileggendo il PDF (`cedolini_tipo_dal_pdf.py`: busta con stesso CF, anno e netto al centesimo), mai dal mese; da solo si applica solo mensile → 13ª/14ª, il verso contrario resta `da_decidere` al titolare. Nelle buste CSC la 13ª/14ª è la voce a codice «850 13 MENSILITA'»/«852 14A MENSILITA'» quando è l'unica competenza.
- Il netto si legge solo dalla cella graficamente associata a `TOTALE NETTO` / `NETTO DEL MESE` / `NETTO
  IN BUSTA`: mai da `ARR. PREC.`, competenze, trattenute, TFR, arrotondamenti o dal nome file. Cella vuota
  → nullo, **mai zero**. Stati: `NETTO_VERIFICATO_DA_CEDOLINO`, `NETTO_NON_PRESENTE_O_NON_LEGGIBILE`,
  `MULTIPLE_NETS_DA_VERIFICARE`, `ERRORE_PARSER` (in `app/constants/stati_netto.py`); solo il primo
  alimenta Salari e bonifici, e la decisione si prende **solo** con `alimenta_salari()`, che fallisce
  **chiuso**: uno stato assente, vuoto o sconosciuto non passa. Su un dato che diventa un bonifico
  l'assenza di prova non vale come prova.
  Zucchetti/CSC: cella **sotto** l'etichetta (`_netto_dalla_cella`); competenze − trattenute è solo un controllo, e i totali si leggono come righe intere (le trattenute «6.691,15» non sono «691,15»). I netti HR si rileggono dal PDF della riga (`cedolini_hr_riverifica.py`, un lotto ogni 20 min): cambia solo un netto verificato, il vecchio resta in `storico_netto`. In HR il netto è quello della busta **più l'acconto già recuperato** (`acconti.acconto_recuperato`, decisione del titolare del 28/09/2026): il totale del mese, non un errore di lettura.
- Sulla collection `cedolini` il campo è **`pagato`**, non `pagata`: il femminile non esiste su nessun
  documento e un filtro che lo cerca passa sempre.
- **Un solo motore abbina bonifico e stipendio**: `associa_bonifici_stipendi` (identità completa, acconti,
  residuo). Nessun percorso può cercarsi da solo «il primo movimento con importo vicino e il nome nella
  descrizione»: un omonimo o due buste uguali nello stesso mese bastano ad attaccare il movimento
  sbagliato. Lo stesso per gli F24: `riconcilia_f24_banca`. Un movimento vale come prova solo se
  ha **evidenza bancaria ufficiale** e non è `in_attesa_estratto_ufficiale`.
- **Un solo motore per ogni cedolino** (posta, Drive, Documenti > Import, pipeline email): legge
  `services/cedolini_motore.leggi_pdf` (Zucchetti classico e «s», Libro Unico, Teamsystem anche 13ª/14ª
  «14a MENS.», CSC), scrive solo `cedolini_manager.processa_tutti_cedolini_pdf`. Niente Document AI, regex
  storico o Libro Unico a parte. L'esito è sempre dichiarato: `buste`, `presenze` (foglio Aut. 301, non è
  una busta), `fuori_periodo` (prima del 2018), `non_cedolino` (contratti), `illeggibile`. Una busta con
  la cella del netto vuota entra **solo in HR** col netto nullo, mai in Prima Nota. Voci codificate e
  **dati chiave** (ratei 13ª e 14ª, L.207/24, trattamento integrativo L.21) da `parsers/cedolino_voci.py`.
- **Ogni PDF letto è una scheda Markdown** (`schede_markdown.py`); registro per anno riscritto a ogni scheda; ricarica dalle schede, mai dai PDF.
- **Doppioni d'archivio** (`doppioni_archivio.py`): stessa busta (CF, periodo, tipo, netto, lordo, trattenute), quietanza
  (protocollo **e** saldo: col saldo diverso è un'altra delega, `protocollo_condiviso_con`) o bonifico (CRO+importo; il RIF. INTERNO BPM «MB…», quello dell'estratto conto, è `rif_interno`) non si riscrive; le copie vanno in `<collezione>_quarantena`, resta la pagata. Una busta già in archivio è un esito (`gia_presenti` → ELABORATE), mai un errore; la «STAMPA DI CONTROLLO» con la definitiva identica (CF, periodo, netto) va nel Cestino (`cedolini_stampe_controllo.py`).
- **Versioni della stessa busta** (`cedolini_versioni.py`, stessi CF, anno, mese e tipo con netti diversi): la definitiva batte la «STAMPA DI CONTROLLO», la «Variante N» più alta batte le altre; senza marcatore nessuno decide (`varianti_da_decidere`, decide il titolare). La perdente resta in archivio con `status=sostituito` (mai costo, Prima Nota, HR o dovuto), la vincente porta `versioni_scartate`, `rettificato` e `storico_netto`; una perdente pagata o già in Prima Nota salari blocca il gruppo. All'arrivo la busta perdente si salva subito sostituita, mai come secondo cedolino attivo. Rapporto `GET /api/cedolini/versioni`, applicazione `POST …/applica` (`dry_run` per difetto, in sottofondo). Ogni busta porta `netto_fonte` (`cella` | `non_letto_da_lul` | assente, `constants/stati_netto.py`): competenze − trattenute non diventa mai il netto, e la pagina del Libro Unico in cui sotto «NETTO» non c'è nessun valore resta `non_letto_da_lul` col netto nullo. Il lettore per posizione del LUL **è `_netto_dalla_cella`** (CSC 2011–2020, Zucchetti 2023–2025, provato su campioni reali: ogni cella stampata si legge, una vuota è vuota davvero: mese a zero, cassa integrazione a pagamento diretto, stampa di controllo senza totali); le buste anteriori al 2018 sono `fuori_periodo` (`PAYROLL_MIN_YEAR`) e non entrano in archivio.
- Una cessazione letta in una busta vale solo se non esiste una busta successiva della stessa persona.
- **Pagamenti stipendio**: un solo ponte gestionale→HR (`hr_pagamenti_deposito`). Dipendente da CF → nome
  completo univoco → cognome univoco (in banca in testa al beneficiario dopo «FAVORE»): la corrispondenza univoca **basta da sola** («il nome di un
  dipendente è un dipendente»: non serve la parola «stipendio» in causale né un lotto paghe). Resta il
  veto: TFR, fatture, commissioni e fornitori non entrano mai, nemmeno in coda, **anche con un nome
  dipendente dentro** la causale — l'esclusione vince sul nome (anche «ADD.SPE», giroconti a Ceraldi Group, società semplici e aziende agricole). Ambiguo o `BENEFICIARI VARI` → coda, **una riga per bonifico**: il RIF. INTERNO «MB…» (`rif_banca`) unisce ricevuta ed estratto, la seconda prova completa la riga. Il
  **lotto paghe** (≥3 dipendenti lo stesso giorno) resta un segnale per i casi non risolti altrimenti.
  Competenza da causale o nome file, altrimenti **regola del giorno 25**: prima del 25 = mese precedente,
  dal 25 = corrente. Stesso pagamento da PDF e da banca (dipendente, importo, data ±3 gg) → un solo esito,
  arricchito, mai duplicato.
- **Stato del mese, TFR e cessazione**: lo stato di `paghe_mensili` conta gli acconti di `acconti_dipendenti` come la posizione (`acconti_registro_del_mese`), e l'associazione di un acconto lo ricalcola subito. Il veto TFR copre anche «T.F.R.» e «trattamento di fine rapporto»; l'acconto TFR e l'accantonamento scrivono il **giornale del gestionale** (29.01.01 / 39.07.05), mai quello dello schema HR, e un acconto eliminato o corretto si storna con `acconto_tfr_rettifica`. `on_dipendente_cessato` lavora ciascun archivio dove vive la sua collezione: contratti e assenze in HR, partite stipendio nel gestionale.
- **Acconto TFR, un motore solo** (`services/tfr_acconti.py`, usato da `app/routers/tfr.py` e `app/hr/routers/tfr.py`): scala `tfr_accantonato` nell'archivio dell'anagrafica e scrive nel giornale **del gestionale** DARE 29.01.01 / AVERE 39.07.05; una correzione o l'eliminazione **storna** (`acconto_tfr_rettifica`, per differenza), mai cancella. Accantonamento (67.01.07.01 / 29.01.01, idempotente per dipendente+anno, totale ≤ 0 rifiutato) e liquidazione (29.01.01 / 39.07.05, ritenute 39.07.05 / 35.03.15) usano gli stessi conti nei due router; i conti 05.03.03, 02.04.01, 02.02.01 non esistono più in `registrazione_contabile`. La pagina TFR di HR mostra le **quote da buste** del gestionale (`services/tfr_quote_buste.py`: righe mensili di `tfr_accantonamenti`, dipendente per CF o stesso id, mai per nome) accanto al valore HR senza sommarle: `tfr_fonte` ∈ `manuale|buste|nessuna`, il manuale vince, senza nessuno dei due `tfr_accantonato` è `null`, mai zero.
- **`cedolini.pagato` ha un solo scrittore**, `services/cedolini_pagamento.py` (`segna_cedolino_pagato`/`riapri_cedolino`: voce in `pagamenti[]` con `riferimento` univoco, `importo_pagato` = somma, `pagato` al centesimo o dichiarato): lo usano il motore automatico (`salari_unificati_v2`), il pagamento manuale e l'HR. L'associazione manuale di un bonifico stipendio (`/bonifici-da-associare/{id}/associa`, `/paghe/conferma-associazione`) porta sul cedolino del gestionale lo stato di `paghe_mensili.stato_pagamento` (per `gestionale_cedolino_id`, altrimenti CF+anno+mese+tipo; una versione `sostituito` non conta, due attivi non si scelgono); `/ritira-conferma` lo riapre; un gestionale non raggiungibile non blocca l'HR (esito in `cedolino_gestionale`).
- **«Pagato» del mese si decide in un posto solo**, `stato_paga_mese` (`constants/stati_associazione_bonifico.py`), in `Decimal` e **al centesimo**: nessuna tolleranza (titolare 02/10/2026; prima 0,50 € in tre copie), nemmeno nei filtri dei pannelli e del frontend. Un bonifico di stipendio arrivato **prima della busta** lascia il mese `in_attesa_busta` (`paghe_mensili` senza `importo_busta`, mai 0, saldo nullo), visibile in Archivio paghe e fuori da «in attesa di pagamento»; all'arrivo del cedolino `sincronizza_paghe_mensili` gli dà la busta e il pagamento già depositato lo chiude da solo, secondo giro a zero. Un pagamento di conciliazione copre la parte scelta **al centesimo**; l'eccedenza va in `eccedenze_pagamenti` `da_attribuire` (riga con avviso nella posizione, mai in dare/avere) e la destinazione (stipendio, acconto o bonus della stessa conciliazione solo se ci sta al centesimo) la sceglie il titolare con `POST /hr/api/posizione-dipendente/eccedenze/{id}/attribuisci`; mai in automatico, una attribuita non si tocca.
- **Posizione dipendente** (`services/posizione_dipendente.py`, pagina HR, solo admin; «Prima nota» di Archivio paghe è la stessa, per mese): DARE = netto di ogni busta **più l'acconto recuperato in busta** (voci `cedolino_voci.VOCI_ACCONTO_RECUPERATO`, poi `acconti.acconto_recuperato`, poi competenze − trattenute oltre 1,00 €), 13ª/14ª, parte non bonus delle conciliazioni; AVERE = bonifici, contanti, acconti fuori busta (`acconti_dipendenti`: pagamento, mai sommato a un netto). Saldo con riporto d'anno.
  Conciliazioni (`conciliazioni`, verbale in `gestionale.blobs`): totale = somma delle voci al centesimo, «importi non compilati» = totale nullo, mai inventato; il **bonus** ha un conto suo, fuori dalle paghe. In «Bonifici da associare» si sceglie il tipo: stipendio, acconto, conciliazione o bonus. Un pagamento in contanti o scritto a mano si corregge (data, importo, parte; il prima resta in `storico`), uno provato dal bonifico mai.
- **Bonifico associato a mano = `confermato_manuale`** (`services/conferma_bonifico.py`, `constants/stati_associazione_bonifico.py`): segna riga in coda, bonifico, esito e movimento; nessun motore automatico lo riassegna (`associa_bonifici_stipendi`, riallineamento competenza, ponte HR) e sparisce dai candidati degli altri dipendenti; `POST /bonifici-da-associare/{id}/ritira-conferma` (solo stipendi, con `storico`). La coda mostra fino a **10 candidati** (`services/candidati_bonifico.py`: CF > nome completo > cognome con importo uguale al residuo > importo con periodo scritto in causale; cognome condiviso elenca tutti senza proposta; **l'importo da solo non produce candidati**, nessun candidato si applica da sé), l'**avviso multi-dipendente** calcolato (nota di terzi, beneficiari vari, cognome condiviso, stesso importo su più buste) e CRO + rif. banca. Il **riscontro per busta** (`services/riscontro_bonifici.py`: confermato, da_verificare, differenza, nessun_bonifico_trovato, non_riscontrabile; priorità manuale > ricevuta > estratto) è di sola lettura: `GET /hr/api/posizione-dipendente/riscontro-bonifici`.
- **Il bonifico PDF si abbina da solo al suo movimento d'estratto** (`bonifici_da_estratto.py`, giro ogni 30 minuti, il primo 4 minuti dopo l'avvio: con deploy ravvicinati un primo giro tardivo non parte mai): il «Rif. interno» della ricevuta (`MBVT…`) è nella causale della riga d'estratto, e con l'importo al centesimo vale come identità (senza riferimento: nome completo del beneficiario in causale, importo al centesimo, al massimo 3 giorni, un solo candidato). Dal movimento il PDF eredita la fattura che il motore bancario ha individuato (`candidate_fattura_id`: attiva, non legata ad altro bonifico, importo al netto della ritenuta uguale; se punta una copia archiviata vale la gemella attiva con stessi numero, totale e P.IVA, solo se unica; la stessa operazione letta da due fonti — stesso riferimento e importo — vale con la copia che porta la fattura, se le copie non ne indicano due diverse; più bonifici dello stesso fornitore sulla stessa fattura, acconti, si collegano solo se con quelli già legati sommano il totale al centesimo, ognuno col suo riferimento banca; il riferimento è `MBVT…` o `MB0B…`; l'`id` della fattura può essere un numero, quindi si cerca e si aggiorna con testo e intero, e ogni giro rimette sulla fattura il `bonifico_ids` che il solo lato del bonifico aveva perso) o una destinazione senza documento (`destinazione_automatica`, categoria letta dall'estratto); le prove dichiarate sono quelle vere (`rif_banca_in_estratto`, mai «numero in causale»). Gli stipendi restano al motore HR. In Archivio bonifici gli esiti HR `arricchito`/`depositato` contano come associati, i `duplicato` non compaiono, e la colonna del salario non dice nulla su un pagamento che non è di un dipendente.
- «Bonifici da assegnare» è una proposta di importo dovuto, stato iniziale `DA_ASSEGNARE`: non imposta
  bonifico eseguito, movimento, data di pagamento né riconciliazione.
- Cedolini e bonifici salario si associano per dipendente, periodo e regole temporali: non si richiedono
  importi identici quando esistono acconti o trattenute. Le correzioni a mano in «Paghe e bonifici» non
  vengono sovrascritte dalla sincronizzazione.
- **Dimissioni telematiche** (PDF o PEC): alert critico più scadenza UNILAV di cessazione a **5 giorni** dalla decorrenza
  (D.Lgs. 181/2000 art. 4-bis); revoca del lavoratore entro 7 giorni (D.Lgs. 151/2015 art. 26).
- **Giorni di chiusura** (`chiusure_attivita`): ristrutturazione 26/01–08/03/2026 e ferie 15–23/08/2026
  non sono corrispettivi mancanti.
- **Dello storico interessano solo cedolini e F24**: fatture e corrispettivi precedenti all'anno attivo
  non entrano in `invoices`/`corrispettivi`, e dal 20/09/2026 non ci entrano **nemmeno come archivio di
  consultazione** (il `stato_import: archivio_storico` delle fatture e' stato tolto: erano 1.127 documenti
  e 52 MB fuori da ogni conto, che tornavano a ogni ricostruzione Drive). L'originale sta su Drive. Per
  rivedere un anno intero: cambiare l'anno attivo e rilanciare la ricostruzione, che rilegge tutti gli
  XML. Eccezione 1: la **parcella con ritenuta** (`DatiRitenuta`) di qualunque anno entra come fattura intera da Documenti > Import (`_e_parcella_con_ritenuta`, decisione del 29/09/2026: ogni 1040 ha la prova della sua fattura). Eccezione 2: la fattura dell'**anno prima** pagata quest'anno entra solo come **debito** (`debiti_anno_precedente.py`: niente
  costo né IVA; il bonifico la chiude per fornitore e importo al centesimo, debiti uguali in ordine di data, entro 180 giorni; un importo che il fornitore fattura anche quest'anno è un canone e vuole il numero in causale; va in Prima Nota Banca su 33.03.01). Gli **accrediti in entrata del 2023** (ricevuta «A VOSTRO CREDITO»: Satispay, giroconti, rimborsi)
  non si registrano (`ANNI_ACCREDITI_NON_REGISTRATI`); i bonifici disposti di ogni anno restano.
- Modali HR: solo il componente `Modal` di `frontend_hr/src/App.jsx` (WCAG 2.1 AA: focus intrappolato, Esc, focus restituito). Campi dentro `<label>`, `aria-label` sui bottoni ripetuti, focus visibile salvia.

## Fatture: identità e duplicati

- Fornitore univoco per P.IVA → CF → id esterno verificato; gli alias sono solo di supporto.
  `canonical_id` stabile: un cambio di ragione sociale non crea una seconda anagrafica, e un merge
  conserva alias, IBAN, id precedenti, documenti e audit.
- **Doppioni fornitori: un motore solo** (`services/fornitori_dedupe.py`; la P.IVA si valida e normalizza solo in `piva_validazione.py`: Luhn, prefisso IT, zeri, IdPaese UE). Il giro delle 06:20 (`unifica_fornitori_duplicati_task`) fonde da solo i **certi** (stessa P.IVA normalizzata o stesso CF) e i **probabili** (nome uguale/contenuto/con refuso, perdente senza P.IVA né CF, un solo candidato forte); il resto è «da decidere» (`GET /api/suppliers/duplicati/da-decidere`, card nella pagina Fornitori). **Due P.IVA valide diverse non si fondono mai**, nemmeno a mano. La fusione è soft (`status='unificato'`, `merged_into`, mai DELETE): ripunta per id fatture, scadenze, acquisti, metodi, parole chiave, alert, movimenti e proposte, `partite_aperte.controparte_id`, per P.IVA Prima Nota/assegni/pagamenti, e lascia alias, `iban_alternativi`, `id_precedenti`, `storico_fusioni`. Un fornitore senza P.IVA la riceve dalle sue fatture solo se è una sola e valida (`piva_fonte='fatture'`); una P.IVA che non torna resta com'è e la scheda dice «P.IVA da verificare» (`vista_piva`), mai corretta. L'import fatture cerca la P.IVA in tutte le sue scritture e il CF, e non riattiva un fornitore unificato. Lotti tiene i suoi `fornitori` per nome (decisioni di esclusione): non si fondono da qui.
- **Il metodo del fornitore ha una data** (`metodo_pagamento_dal`, ISO nel database, gg/mm/aaaa in pagina, la stessa dello storico): lo stampa a oggi solo un cambio di metodo, mai un semplice salvataggio della scheda. «Sempre per cassa dal 01/01/2025» si applica alle fatture già importate con `POST /api/suppliers/{id}/applica-metodo-dal` (`services/metodo_fornitore_dal.py`, admin, `dry_run` per difetto, in background, stato in `sistema_stato`): usa la stessa conferma di Prima Nota Cassa (`conferma_fattura_provvisoria`, la parola del titolare è l'approvazione), non un motore nuovo; solo per la Cassa. Non tocca una fattura con prova in banca, un assegno o una dichiarazione in banca del titolare (le elenca come conflitto), né note di credito, estere, rate multiple e pagamenti parziali; il secondo giro chiude zero.
- Il metodo del fornitore ha **un solo scrittore**, `update_supplier` (`PUT /api/suppliers/{id}`); `PUT …/metodo-pagamento` è un alias che lo chiama: data «dal» e storico vengono sempre da lì. `data_pagamento` di una fattura pagata con assegno è la data dell'addebito in banca (`fatture_pagate_con_assegno`, `data_pagamento_fonte=addebito_banca`); prima dell'addebito è quella dichiarata (`data_pagamento_fonte=dichiarata`), mai la data di compilazione.
- Il metodo di pagamento si legge **solo dall'anagrafica fornitore**, mai dedotto dalla fattura; se non configurato
  la fattura resta `sospesa`, mai con un default «bonifico» **né un ripiego in cassa**: le righe storiche di quel
  ripiego restano per audit, fuori da elenchi e saldi (`SOURCES_ESCLUSE` in `prima_nota_module/common.py`).
- **Come è stata pagata una fattura lo dice il titolare** (report «Fatture ricevute» con colonne metodo/carta/assegno,
  Documenti > Import): `pagamenti_dichiarati_titolare.py` usa solo i motori esistenti; il metodo del fornitore (uno → quello, più → `misto`) lo scrive **solo se manca**. Fino all'ultima data del report (`data_limite_dichiarazioni`) comanda il report, poi il fornitore. La cassa d'ufficio `metodo_fornitore_assente_provvisorio` non prova un pagamento.
  Banca/carta/PayPal/assegno dichiarati: riga Prima Nota Banca `dichiarato_titolare`, fattura pagata e `in_attesa_riscontro_banca`; il movimento trovato la **sostituisce** (`assorbi_righe_dichiarate`), mai affianca.
- «Metodo di pagamento non configurato» ha un vocabolario solo, `app/constants/metodi_pagamento.py`:
  `sospesa` (quello che scrive l'import), `da_configurare`, `none`, vuoto e campo assente valgono uguale.
  Chi tiene la propria lista si perde il caso più frequente.
- **Le fatture fornitore non hanno scadenza.** Decisione del titolare (19/09/2026): «decido io quando
  pagare». Non si leggono le condizioni di pagamento dell'XML, non si leggono le date sul documento e non
  si inventa un «+30»: `data_scadenza` resta vuota. Il piano rate si conserva come dato dell'originale ma
  non guida niente. `check_scadenze_partite_task` salta le partite fornitore e `FAT_DA_PAGARE_SCADUTA` non
  nasce più; F24 e stipendi, che una scadenza vera ce l'hanno, restano invariati.
- **«È pagata?» si chiede in un posto solo**: `e_pagata` / `FILTRO_NON_PAGATE` di
  `app/services/stato_pagamento_fattura.py`, e `ePagata` di `frontend/src/utils/statoFattura.js`. Lo stato
  vive in cinque campi (`stato`, `stato_pagamento`, `payment_status`, `pagato`, `paid`) e nessuno copre
  l'archivio: leggerne uno solo dichiarava non pagate 639 fatture da 311.838,20 €, e `{"pagato": {"$ne":
  True}}` le riportava tutte fra le aperte. In archivio una fattura aperta si dichiara pagata da **una tendina sola** («Pagata con…», `ScegliPagamentoFattura.jsx`: cassa con data → `provvisori/conferma`, banca → estratto conto, assegno → registro assegni): nessun motore nuovo, e su una fattura già in Cassa o Banca non compare. `status` è lo stato del documento e `stato_finanziario` quello
  della riconciliazione: nessuno dei due dice se è pagata. Pagata con assegni addebitati (prova ufficiale, quote = totale al centesimo): i cinque campi e `data_pagamento` si allineano alla banca (`fatture_pagate_con_assegno`, job bancario corto).
- Il payload di `fattura.created` si costruisce solo con
  `app/services/eventi_fattura.py::costruisci_evento_fattura_created`, così import e recupero del
  pregresso propagano lo stesso evento.
- Un import che **non** pubblica `fattura.created` lascia la fattura senza partita aperta, senza alert e
  senza audit: nessun errore, nessuna traccia. Il recupero è `POST
  /api/admin/fatture/ripubblica-evento-created` (admin, background, `dry_run` per difetto), sugli stessi
  handler idempotenti.
- Spostare una fattura fra Cassa e Banca cambia metodo, relazioni e scritture **con lo stesso ID**. Lo spostamento riallinea anche il conto di tesoreria (19.03.03 cassa, 19.01.01 banca) e `metodo_pagamento_effettivo`, e una riga banca con prova d'estratto non si sposta in cassa (409): sarebbe un'uscita doppia. Il ripasso `ripristina_provvisori_metodo_errato` (cambio metodo del fornitore) non tocca mai una riga con prova bancaria né la fattura che ne è provata. Parcella con ritenuta: al fornitore esce il **netto** (`importo_ritenuta` dal `DatiRitenuta`), la ritenuta va in F24 (all'arrivo alert `RITENUTA_DA_VERSARE` più Telegram, chiuso dal 1040 versato); una riga con prova bancaria non si declassa mai a dichiarata.
- `app/services/fatture_identita.py` ricava l'identità dall'XML con lo stesso parser dell'import.
  L'impronta del **contenuto** (`content_hash_canonico`, prefisso di versione `c2:`, insensibile a BOM, a
  capo, codifica e caratteri non ASCII) prova che due XML sono la stessa fattura. La dedup tiene la copia
  già nel giornale e **storna** la scrittura del doppione. Collisioni aperte = `stato_import` di
  collisione **e** `status` non archiviato.
- **Una fattura con la stessa chiave contabile si decide in un posto solo**, `decidi_stessa_chiave` (`fatture_upload.py`), per Drive **e** Documenti > Import: stesso originale (SHA-256 o impronta canonica) = già presente, `nuovi=0`; originale diverso = collisione (`stato_import=collisione_identita_da_verificare`, `status=da_verificare`, derivati bloccati, alert `FATTURA_IDENTITA_DA_VERIFICARE`), mai scartata in silenzio. Anche l'import manuale salva `content_hash` e `content_hash_canonico`.
- Note di credito ricevute (TD04/TD08, `TIPI_NOTA_CREDITO`): non costi; ledger (`prima_nota_module/sync.py`) e giornale
  (`registra_fattura`) leggono `tipo_documento` e scrivono l'inverso (meno costo, IVA a credito e debito, mai cespite).
- **Fattura emessa = cedente è la nostra P.IVA** (`FISCAL_COMPANY_ID`), da ogni ingresso: `fatture_emesse`
  (`services/fatture_emesse.py`), mai `invoices`. Fatta dopo lo scontrino: **non aumenta ricavi, IVA né crediti**; si
  aggancia al corrispettivo del giorno dello scontrino (dalla causale, se no data fattura) se unico; clienti per P.IVA→C.F.

## PartenoPay, verbali e flotta

- Conservare email, verbale, avviso, ricevuta PagoPA/PayPal e movimento banca
  come prove separate.
- Stati e motore dei verbali in un posto solo: `app/constants/stati_verbale.py`
  (nove aperti — fra cui `fattura_ricevuta`, quello di tutte le righe vere — e
  tre con prova, in maiuscolo e minuscolo: un filtro li elenca entrambi; `quarantena` non è né aperto né pagato, `e_chiuso` li unisce) e
  `riconcilia_verbali_strict`, che esige riferimento strutturato **e** importo
  uguale al centesimo, mai solo importo o data vicina. L'importo si legge dal
  PDF. `pagato_attesa_fattura` è il legacy di `pagato_attesa_quietanza`.
- Gli importi dei verbali si confrontano in **centesimi** (`amount_to_cents`/`money_cents`), mai con un float; il verbale porta `importo_centesimi`. «Pulisci duplicati» mette le copie in `stato=quarantena` per id con `doppione_di` e `motivo_quarantena`, mai `delete_many`.
- Associazione automatica driver: targa normalizzata più data/ora infrazione
  più storico assegnazioni (`assegnazioni` del veicolo, `driver_alla_data`): il
  driver è quello attivo **alla data/ora del fatto**. Se targa, driver, verbale
  o pagamento non sono univoci, conservare il documento e chiedere una scelta.
  **`driver_alla_data` (`noleggio/controlli.py`) è l'unico motore**: lo storico sta solo sul veicolo
  (`veicoli_noleggio.assegnazioni`, dal/al), la collezione `storico_assegnazioni_veicoli` non esiste più; con uno
  storico che non copre la data il driver è «da assegnare», mai quello di oggi. **La data dell'infrazione è
  `data_violazione`** (`verbali_evidence.data_violazione_verbale`; `data_infrazione` è un alias di vecchie righe,
  mai più scritto); `data_verbale` è la data dell'atto redatto, un'altra cosa (`data_evento_verbale` dice quale
  delle due si sta usando).
- **Il PDF di un verbale si legge in un posto solo**, `verbali_document_import.leggi_documento_verbale` (numero,
  IUV, targa, importo, data dal **contenuto**, mai dal nome file): `process_verbale_document` lo chiama e scrive,
  la ricostruzione lo chiama e non scrive. Il numero può avere barre («111/V/2025», «2025/000123»; una data dopo
  «verbale» non è un numero), IUV e codice avviso sono **sempre testo** (`normalizza_iuv`: un intero ha perso lo
  zero iniziale, un float le cifre: non si indovinano). L'**originale resta sul verbale** (`pdf_data`, `pdf_hash`,
  `pdf_filename`; il payload finisce in `gestionale.blobs`): la copia in `documents_inbox` sparisce quando l'inbox si svuota.
- **Un solo collegamento verbale → fattura** (`verbali_collegamento_fattura.py`): `fattura_id`, `fattura_numero` e
  la provenienza `fattura_collegamento`; data, fornitore e importo si leggono dalla fattura. I campi
  `fattura_associata_*` e `numero_fattura` non si scrivono più (si leggono solo come ripiego, `fattura_id_del_verbale`),
  la fattura non porta una seconda copia (`verbali_collegati` non si scrive più).
- **Ricostruzione dei verbali dal PDF** (`verbali_ricostruzione.py`, `POST /api/verbali-noleggio/ricostruisci-da-pdf`, admin,
  `dry_run` per difetto, in sottofondo, stato in `sistema_stato` chiave `verbali_ricostruzione`, `GET …/stato`): riempie
  **solo i campi vuoti** di un verbale con lo stesso numero; un valore diverso è un conflitto (candidato, mai applicato);
  due verbali con lo stesso numero sono ambigui e non si toccano; mai per solo importo, mai una cancellazione (le righe
  `VERB-…` restano; con `crea_da_pec` la copia conforme senza verbale vero apre il verbale dalla pipeline); porta su
  `fattura_id` e `data_violazione` i campi legacy; il secondo giro dà `da_fare = 0`; non scrive in contabilità. Un verbale
  senza originale (`senza_originale`) si ricarica da Documenti > Import, che lo riconosce per numero o IUV e ora conserva l'originale.
- **Pacchetto PartenoPay** (`partenopay_archive_import.py`): hash di ogni file contro `data.json` **e** contro
  `MANIFEST_SHA256.csv` (file fuori manifest o con hash diverso = errore che blocca; manifest vuoto = avviso, non prova);
  l'import che scrive passa solo da Documenti > Import (lo smistatore riconosce lo ZIP), `POST /api/verbali-noleggio/import-partenopay`
  è **solo anteprima**; secondo giro `nuovi = 0`, scadenza operativa e promemoria nascono una volta alla scoperta, un
  verbale già riconciliato o in quarantena non torna indietro.
- `POST /api/verbali-noleggio/{id}/upload-quietanza` (solo admin): `importo_pagato` e `data_pagamento` obbligatori, importo
  Decimal al centesimo e uguale a quello del verbale (altrimenti 409), PDF con hash; con il PDF il verbale è «pagato»,
  senza «pagato_attesa_quietanza»; stessa quietanza due volte = nessuna seconda nota presenze né seconda proposta di trattenuta.
- **Importo atteso del verbale** (`verbali_importo_atteso.py`, giro `verbali_notifications` 07:10 e all'arrivo della PEC): passati 5 giorni dalla notifica provata dalla PEC (`data_notifica_fonte="pec"`) l'atteso passa da solo all'`importo_ordinario` letto dal PDF (`importo_atteso` Decimal, `importo_atteso_fonte="ordinario_dopo_5_giorni"`), il ridotto resta in `importo_ridotto` e nello `storico`, l'alert `VERBALE_IMPORTO_ORDINARIO` e il promemoria dicono «scaduti i 5 giorni: importo ordinario»; un verbale pagato, chiuso o in quarantena non cambia, senza ordinario letto non si inventa niente, secondo giro = 0 (titolare, 02/10/2026).
- **Una ricevuta pagoPA non crea mai un verbale**: senza un verbale con lo stesso numero o IUV resta in `ricevute_pagopa` con `stato_verbale="senza_verbale"` e alert `RICEVUTA_PAGOPA_SENZA_VERBALE`; all'arrivo del verbale `process_verbale_document` la aggancia con importo al centesimo (`aggancia_ricevute_in_attesa`) e chiude l'alert; stesso numero con importo diverso è «importo non coincide», non «senza verbale».
- **Assegnazioni veicolo→driver con data e ora**: `veicoli_noleggio.assegnazioni[].dal/al` sono `AAAA-MM-GG` (giorno intero) o `AAAA-MM-GGTHH:MM`; `driver_alla_data` sceglie il driver attivo alla data **e ora** dell'infrazione (`data_ora_evento_verbale`, `ora_violazione` dal PDF); un evento senza ora nel giorno del passaggio dà i candidati e non sceglie; il PUT valida e normalizza (400 su data illeggibile o `al` < `dal`) e il cambio driver chiude/apre il periodo allo stesso minuto.
- **La trattenuta in busta per un verbale nasce in un posto solo**, `trattenute_verbali_service.proponi_trattenuta_verbale_pagato`, e solo a verbale pagato con quietanza (PDF caricato o ricevuta pagoPA/PayPal) e importo certo, stato `proposta` finché il titolare non conferma; l'assegnazione del driver, un pagamento dichiarato senza PDF e la sola prova bancaria non aprono nulla.
- Il verbale genera un promemoria operativo a 5 giorni dalla scoperta. **La PEC di notifica è la prova della notifica** (`notifiche_pec_verbali.py`): la data della PEC è `data_notifica`, da cui 5 giorni (ridotto), 30 (Giudice di Pace) e 60 (Prefetto); il numero si legge dalla copia conforme, mai dal nome file, e la notifica si aggancia al verbale vero con quel numero (`notifiche_pec`, allegati nel fascicolo), mai a un secondo verbale; senza verbale resta «da agganciare» (`POST /api/verbali-noleggio/notifiche-pec/aggancia`, `dry_run` per difetto).
- **Le PEC di notifica si agganciano da sole** nel giro giornaliero dei verbali delle 07:10 (`verbali_notifications`: prima `giro_aggancio_automatico` di `notifiche_pec_verbali.py` con `dry_run=False`, poi l'importo atteso, poi i promemoria): una PEC si lega solo al verbale vero con lo stesso numero letto dalla copia conforme; senza verbale o con due verbali veri resta `da_agganciare` col motivo (`senza_verbale`|`verbali_ambigui`), nessun verbale nasce, secondo giro = 0; l'esito dell'ultimo giro sta in `sistema_stato` (`notifiche_pec_verbali_ultimo_giro`), niente bottone né PIN (l'endpoint `…/notifiche-pec/aggancia` resta per l'anteprima). **La nota per il consulente** della trattenuta (`note_presenze_consulente`, archivio del gestionale, mese successivo alla quietanza) parte con le presenze del mese da entrambi gli invii (HR «Invia» e Pacchetto commercialista: `presenze_consulente.note_consulente_mese`, riga nel corpo dell'email e CSV `note_presenze_AAAA_MM.csv`) e dopo un invio riuscito `registra_invio` la segna `inviato_consulente`.
- **Posizione auto/driver in un posto solo**: `app/services/noleggio/posizione.py`
  (`GET /api/noleggio/posizione`, tab «Posizione auto e driver»). DARE = costi documentati
  (fatture per categoria, verbali con importo verificato); AVERE = **solo prove strutturate**
  (allocazioni bancarie confermate, Prima Nota Banca **con** estratto conto, quietanze
  PartenoPay/Mooney/PayPal/PagoPA agganciate al verbale). Prima Nota senza estratto conto =
  dichiarato, non chiude il saldo. Un SDD cumulativo si spartisce con le quote delle allocazioni
  al centesimo; il pagamento pesa sul driver **alla data del costo**. Un'uscita verso noleggiatore
  o Comune di Napoli senza relazione resta candidato, mai attribuita.
- Lo scan fatture noleggio legge solo le fatture attive (`FILTRO_FATTURA_ATTIVA`: fuori
  `archived`/`archiviata`/`deleted`, archivio storico, collisioni): ogni fattura 2026 esisteva in
  due copie e i costi erano doppi. Aliquota 0 (bollo, N1) resta 0: `0.0 or 22` inventava il 22%.

## Sicurezza

- Segreti solo nelle variabili d'ambiente di Render.
- Non stampare, committare o trasferire credenziali.
- Non spostare né cancellare email e documenti originali.
- Eliminazioni reali, pagamenti e associazioni definitive ambigue richiedono
  conferma esplicita al momento dell'azione.
- Telegram è l'unico canale attivo per alert e notifiche operative: non
  registrare router, webhook o fallback WhatsApp.
- **Ogni route è autenticata, e una nuova senza token non entra in silenzio.** L'ERP è chiuso dal middleware globale per tutto `/api/` fuori da
  `PUBLIC_PATHS` (login, liveness, callback banca col suo `state`, pagine legali); HR, Lotti e Menu vivono fuori da `/api/` e si proteggono con le
  proprie dipendenze (`require_*`, `auth_dependency`, `verify_token`). `tests/runtime/test_p2_admin_guards.py` costruisce l'inventario da `app.main:app`
  (mount compresi) e fallisce per ogni route raggiungibile senza token che non sia in una lista bianca **con il motivo**; vale anche per ogni voce nuova di
  `PUBLIC_PATHS`. I dati finanziari (Mutui, letture comprese, e il parser dei piani) hanno la guardia admin sul router. Un ordine anonimo del Menu è sempre
  «cliente» e non pagato: `cassa` e `pagato` li dichiara solo chi porta il token dello staff. Ogni route di `/api/agenti` è solo admin (segnalazioni, stato, run, decisioni, automazioni, cash-flow, settori e proposte).

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

- **Un solo punto d'ingresso per le fatture** e deduplica sempre attiva: numero + P.IVA **oppure** numero + fornitore + data (una P.IVA troncata nell'import di gennaio creava doppioni). Il
  ponte dal gestionale vede **tutte** le fatture dell'anno: il tetto per giro vale sulle **ancora da
  prendere**, mai sull'elenco intero, che arriva ordinato per data — tagliarlo butta le più recenti (erano
  444 dal 30/06) e il buco cresce da solo. Quante restano lo dice `arretrato`.
- **Una fattura che entra nel gestionale alimenta Lotti subito**: l'handler `fattura.created` importa
  **quella sola** fattura (mai un ripasso d'archivio: il giro Drive ne porta 25 per volta). Lotti è a
  valle: un suo guasto o la sua lentezza non fermano l'import contabile (coda in sottofondo). Il giro dei 15 minuti è la rete.
- **«Fattura attiva» si decide in un posto solo**, e per Lotti vale lo stesso criterio del libro giornale:
  fuori `deleted`, `archived`/`archiviata`, `archivio_storico` e le collisioni di identità aperte. Un
  filtro parallelo che guardava solo `deleted` mandava a Lotti 1.444 fatture invece di 889.
- **Il registro delle ricevute non è una prova di presenza**: vale solo se la fattura esiste ancora in
  `fatture`. **Un'impronta cambiata non è un conflitto** (il gestionale arricchisce righe e stati): conflitto è solo
  XML diverso con la fattura già in Lotti; se manca si importa. Un fornitore fuori dal magazzino si salta, non è un errore. **Nel magazzino / fuori dal magazzino ha una scelta sola**, `fornitori.esclude_magazzino` dell'anagrafica ERP per P.IVA (`services/magazzino_fornitore.py`): motivo a chip (mai testo libero, «Altro» è l'eccezione), data, chi, `storico_magazzino`, anteprima coi conteggi prima di confermare (`GET/PUT /api/suppliers/{id}/magazzino[/anteprima]`, solo admin). Il ponte e l'handler `fattura.created` leggono prima quella; dove l'anagrafica non ha mai deciso vale la decisione già presa in Lotti (`fornitori`/`fornitori_decisioni`, per nome, e un omonimo con altra P.IVA non eredita); se nessuno ha deciso il fornitore è **incluso** e la scheda dice «non deciso» (mai «escluso» d'ufficio: il vecchio `not inventory_enabled` lo faceva per 197 fornitori su 198, campo che non esiste più). Lotti riceve una **proiezione** (`imposta_esclusione`, usata anche da `/escludi`, `/approva`, `/tipo-fornitura`, qualifica e auto-classifica) e ogni scelta fatta lì torna nell'anagrafica (`registra_decisione_da_lotti`); la qualifica automatica non riporta dentro chi il titolare ha messo fuori. Escludere o includere **non cancella niente** (fatture contabili, lotti e inventario restano); includere accoda le sole fatture ancora da prendere, con l'import idempotente di sempre. `POST /api/suppliers/magazzino/allinea` (admin, `dry_run`) porta sull'anagrafica le decisioni di Lotti dove manca la scelta.
- **Un numero che non si conosce non è zero**: KPI senza fonte = «Dato non disponibile»; spesa = `total_amount` del gestionale per identità (`spesa_da_gestionale`); costo lotto = consumo × prezzo di fattura (`costo_da_consumo`), altrimenti `None` col motivo; spese, sconti e trasporto non entrano in giacenza. Dose e righe-intestazione in un posto solo (`servizi/ingredienti_ricetta.py`): un ingrediente senza dose si dichiara (`ingredienti_senza_dose`), mai saltato in silenzio; la merce mai scaricata la chiude solo il titolare (`servizi/merce_ferma.py`: simulazione, conferma, riapribile, niente si cancella). Lievito di birra: un solo motore (`servizi/lievitazione.py`) per dose, produzione e calcolatore impasti; si scala dal `lievitazione_riferimento` della ricetta alle ore/temperature di oggi e senza riferimento non si ricalcola; la produzione scarica e registra il lievito realmente usato.
- **Prezzi da acquisti reali in fattura XML, oppure da listino del fornitore dichiarato come tale.** Gli ordini hanno totali veri: prezzo di riga, aliquota
  IVA dall'XML, imponibile, IVA e totale che si ricalcolano a ogni variazione, con le stesse colonne nel PDF.
- **Listini** (`servizi/listino_fornitore.py`, `POST /catalogo-forno/importa-listino`, Excel/CSV letto per intestazione): prezzo
  che il fornitore dichiara oggi (Barone: catalogo riservato, bundlato in `data/listino_barone_2026-09-28.json` e caricato
  all'avvio solo se piu' nuovo di quello in archivio; stessa strada per `data/listini_catalogo_ceraldi_2026-07.json`, catalogo bar del vecchio archivio con un listino per fornitore, prezzi IVA esclusa, codici `CC-nnnn`). Vivono in `catalogo_forno_prodotti` (`fonte_catalogo="listino"`,
  `prezzo_listino` stringa Decimal per l'unita' «12 PZ») con la fonte `tipo="listino"` in `fonti_catalogo_esterne`; un articolo
  uscito dal listino resta con `nel_listino=False`. Nel confronto compaiono con scritta «listino» e data, mai come prezzo pagato.
- **FIFO: il lotto con la fattura più vecchia**, fra tutti i fornitori dello stesso articolo. Descrizione di fattura →
  articolo in `nome_mapping` (`servizi/articoli_fattura.py`): vince la riga **confermata** (Dizionario, «Proposte web»);
  senza conferme, parola intera e fuori i lotti che una prova dice altro («olive in acqua e sale» non è sale).
- **Bevande e alcolici del bar** (acqua, birre, vino, prosecco, liquori, amari, sciroppi, succhi, bibite) si confrontano
  a cartone o a pezzo, **mai a chilo o a litro**. Miglior fornitore: `servizi/confronto_fornitori.py`, **motore unico** per confronto,
  cataloghi e carrello (righe XML + listini, fornitore = P.IVA). Vetro e lattina non si uniscono mai, nemmeno passando per una
  descrizione che il contenitore non lo dice. Accorpamento: certo per testo, EAN o **lettura AI** (`servizi/lettura_articoli_ai.py`,
  collezione `articoli_letti_ai`, giro orario 06-22 e 3 minuti dopo l'avvio: marca, prodotto, variante, formato; misura e pezzi solo
  se scritti nella descrizione), dichiarato `abbinato_ai` e separabile con «diverso»; il resto lo decide una persona.
  `nome_mapping` resta l'ingrediente per le ricette, non l'articolo da ordinare. **Scelto un prodotto (catalogo, Ordini o
  confronto), la riga del carrello va al fornitore che costa meno** (`GET /confronto-fornitori/migliore`) e il toast lo dice;
  un cartone fatturato senza i pezzi scritti prende il numero dal listino dello stesso articolo, con la nota «da verificare».
- **Il web identifica i prodotti con un motore solo** (`servizi/lettura_articoli_ai.py`): `cerca_sul_web` è l'unica chiamata a `web_search_20250305` (stessa `ANTHROPIC_API_KEY`, la usa anche la ricerca delle schede tecniche); `identifica_col_web` (giro `lotti_identifica_col_web` ogni 25 min, 5 righe, tetto 120 chiamate al giorno, `web_cercato_at` = 30 giorni di pausa) dà una categoria del Dizionario da sola **solo** se il web (alta confidenza, almeno una fonte) e il testo di fattura concordano e la categoria è in `CATEGORIE` (`categoria_fonte="web"`, `abbinato_ai`, fonti); il resto è proposta `nome_mapping` fonte `web`.
- Conversioni reali: uovo 60 g, tuorlo 19 g, albume 33 g; pezzi e chili col peso del pezzo.
- Ogni riga d'ordine dice **chi l'ha inserita** (dipendente, lavagna, riordino automatico, produzione,
  colazione). Le righe-nota (omaggi, riferimenti) non diventano prodotti di magazzino. Soglia minima e
  quantità di riordino a 1.
- Campi vincolanti: `ingredienti_dettaglio[].unita_misura` (non `unita`), `lotti.data_scadenza` gg/mm/aaaa,
  `fornitori` per `nome` e non `id`.
- **Schede tecniche ME.PA.** (`servizi/schede_fornitore.py`): la descrizione nella mail è la riga di fattura
  e fa da chiave. Il PDF per l'ASL non si elimina né si sovrascrive; allergeni e valori per 100 g solo se
  scritti, in etichetta solo da articolo confermato o lotto consumato con la stessa descrizione.
- Spostando un lotto si scrivono **sempre** sia `posizione` sia `frigo_numero`; per azioni reali sui lotti
  di un'attrezzatura si usa il match esatto sul nome, mai uno snapshot troncato («Frigorifero N°2» e «N°9»
  si confondono). La produzione sceglie con **un solo tocco** banco oppure un apparecchio attivo censito: niente destinazione predefinita, testo libero, ripiani o «senza posizione»; il banco passa sempre dal prelievo canonico, il lotto non resta disponibile anche nel registro banco e ogni cambio posizione ha audit.
- Foto ricette: archivio unico Supabase Storage, anche per il cestino e le copie delle varianti; Drive si **legge** soltanto (foto già collegate, cartella scritta sul record), mai si scrive. La copia in `GESTIONALE/FOTO E IMMAGINI/RICETTE` la scrive dal PC `scripts/esporta_foto_ricette.py` (Drive Desktop): l'account di servizio non ha spazio nel Drive del titolare.
- `prodotti_master` è il catalogo canonico e `magazzino_unificato` il magazzino canonico;
  `prodotti_vendita` e `sconti_merce` sono domini diversi e non si fondono.
- **Il registro HACCP non si scrive da solo.** Alle 07:00 il turno *apre* la casella del giorno su ogni
  apparecchio attivo (mai su uno `fuori_servizio`) e ci mette il responsabile assegnato
  (`attrezzature_config.operatore_id`, nome da HR): `temp` resta `None`, stato `da_rilevare`. Se il titolare
  dichiara di fare lui il controllo visivo (`controllo_visivo_responsabile`), il turno annota l'**esito** —
  «conforme, entro le soglie della scheda», firmato col suo nome — e **mai un valore numerico**: quello si
  scrive solo quando c'è un'anomalia, e lo scrive lui (valore vero, fuori servizio, assistenza).
  La misura la fa una persona dal tablet, e **la firma è il PIN**
  (`servizi/firma_dipendente.py`): col PIN il nome arriva da HR e il record è `firma_verificata`; con un PIN
  sbagliato la rilevazione **non si salva**, perché una firma falsa è peggio di una registrazione mancante.
  Un giorno senza lettura si **dichiara** «non rilevato», mai riempito d'ufficio; lo storico **senza firma** resta
  ma vale «n.a.» (`servizi/haccp_attendibilita.py`). Mai `random` né codice morto in HACCP (`test_haccp_niente_evidenze_finte.py`). Apparecchi di un anno = censiti + chi ha rilevazioni (`schede_temperature.py`), mai 12 fissi; un GET non crea schede (le crea il turno); il giorno è quello di Roma; «conforme», «non rilevato» e «da rilevare» si vedono diversi anche in stampa.
- **Il responsabile di ogni frigorifero e congelatore senza assegnazione è il titolare** (decisione del 02/10/2026): il turno delle 07:00 scrive sulla casella `operatore_id="titolare"` e il nome di `responsabile_haccp` delle Impostazioni azienda (`AZIENDA_RESP_HACCP` come default), mai cablato; senza quel nome l'apparecchio resta in `senza_responsabile`, non si inventa. L'assegnazione per apparecchio è `PUT /attrezzature/{tipo}/{numero}/responsabile` (id HR, `titolare` o vuoto; nome sempre da HR o dalle Impostazioni), tendina «Responsabile» nella pagina Apparecchi. Un solo motore: `servizi/responsabile_haccp.py`. **La sessione amministratore del Gestionale firma le rilevazioni** (`firma_registrazione`: `firma_verificata`, `firma_via=sessione_admin`, nome dal token se porta l'identità HR, altrimenti dalle Impostazioni); «Amministratore» non è un nome e il ruolo `automazione` non firma mai; un PIN sbagliato resta 401. **Dichiarare la conformità e aprire le caselle si fa dai registri** (card «Controlli di oggi», `shared/TurnoHaccpOggi.jsx`, sopra Frigoriferi e Congelatori, anche sul tablet): «Dichiaro conformi i controlli di oggi» → `POST /haccp-auto/dichiara-conformi-oggi` (prima il numero di caselle aperte, poi conferma; 409 senza controllo visivo, 401 senza firma; scrive `stato=conforme`, `temp=None`), «Apri le caselle di oggi» → `POST /haccp-auto/apri-rilevazioni-oggi` solo se `turno-oggi` dà `quante_senza_casella > 0`.
- Stampa: coda più print agent locale sul PC del negozio (`scripts/print_agent.py`, PIN in `LOTTI_PRINT_AGENT_PIN`,
  variabile **locale**, mai su Render), stampante scelta per tipo di documento, token solo in `Authorization` e solo verso Lotti. Il fascicolo per un'ispezione si compone da
  `/lotti/api/manuale-haccp/stampa`: si spuntano le pagine (`SEZIONI_MANUALE`, le stesse che il generatore
  sa produrre — un test lo verifica) e il frontespizio con i dati dell'azienda c'è sempre.
- **Un PIN per entrare, non per ogni sezione**: magazzino e portale dipendenti condividono la verifica (`services/workforce_tokens.py`,
  prova `LOTTI_AUTH_SECRET` e `HR_JWT_SECRET`); l'ERP contabile resta fuori. La traduzione dei ruoli è **direzionale**
  (`operatore`↔`dipendente`), mai verso `admin`, e un token **senza** ruolo non ne riceve uno di ripiego: fallisce chiuso. Ruoli di Lotti (`servizi/ruoli.py`) sulla scheda HR (`lotti_ruolo`, `lotti_reparti`): **HACCP** registri, anomalie, conformità, apparecchi, smaltimento; **caporeparto** ricette e annullo produzione del suo reparto, smaltimento. Il token resta da operatore: `require_permesso` rilegge il ruolo a ogni scrittura (403 `RUOLO_NON_AUTORIZZATO`).
- Piano di sanificazione per area (`/sanificazione/piano`): frequenza, prodotto, diluizione, tempo di
  contatto. Niente valori di ripiego — un detergente scritto a caso rimanda a una scheda di sicurezza che
  non c'entra. `/sanificazione/scadute` dice cosa è in ritardo e cosa è ancora da compilare.
- Accessi: token 12 h, rinnovi al massimo 7 giorni dal PIN (admin 24 h, `auth_at`); PIN sbagliati contati in `pin_tentativi`, per client **e** globali; sui tablet condivisi il magazzino chiude dopo 10 minuti. Ogni scrittura o dipende da `require_admin` o è fra le operazioni di reparto di `test_scritture_riservate.py`; un URL da fuori si scarica solo con `servizi/fetch_sicuro.py`. Il JWT solo nell'header, **mai in `?token=`**: i documenti con `apriDocumentoAutenticato`.
- Backup Lotti: mai sul disco del servizio. Parti verificate (SHA-256) in `gestionale.blobs` più manifesto (`servizi/backup_archivio.py`, registro `backup_registro`); il ripristino è simulazione → backup di sicurezza verificato → sostituzione per id. Navigazione: ogni reparto del tablet ha la stessa `BarraReparto` (Indietro, Reparti, Gestionale solo titolare, Cambia operatore), ogni pagina il suo `ErrorBoundary`, un indirizzo sconosciuto «Pagina non trovata», la configurazione passa da `#impostazioni`.

### Menu — allergeni

- Gli allergeni sono un obbligo di legge, non una cortesia: **Regolamento UE 1169/2011** e **D.Lgs. 231/2017**
  impongono di dichiarare i 14 allergeni principali per ogni prodotto. Il dato vive in
  `menu.menu_products.allergens` con i 14 id UE in `menu.menu_allergens`: **non in un file**.
- Il menu vero si gestisce su Qromo (`ceraldicaffe.qromo.it`): la sync sostituisce per intero categorie,
  sottocategorie e prodotti con `origine IS NULL`, e riduce gli allergeni ai 14 UE.
- **È Lotti a spingere nel Menu, non il Menu a pescare dalle ricette**, ed è
  l'unica strada ricetta → prodotto (il «Collega a una ricetta» dell'admin
  Menu era un doppione dal lato sbagliato, rimosso). Ogni ricetta la replica
  il ponte `app/lotti/servizi/menu_bridge.py` con la stessa foto
  (`origine = "lotti"`, `lotti_ref` idempotente, `menu_pubblico` → `visible`):
  le righe di Lotti sopravvivono alla sync Qromo e l'esito `menu_sync` non fa
  mai fallire l'endpoint Lotti. Pregresso con
  `POST /api/ricette-ripubblica-menu` (admin, in background). La visibilita'
  pubblica delle nuove ricette e' spuntata per default; `pubblica_tutte=true`
  spunta anche l'archivio esistente e conserva i valori precedenti nello stato del giro.
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
  «togli il prezzo». Una ricetta **senza nessuno dei due** compare nella carta
  `/menu/carta/index.html` con **Prezzo da definire**; le API dei prodotti
  ordinabili continuano a richiedere un prezzo valido. Il backfill conta
  `senza_prezzo`, senza inventare un ripiego.
- In Lotti, **In menu → Prezzi da completare** permette all'amministratore di
  inserire il prezzo al tavolo accanto a foto e prodotto, senza aprire la scheda.
  Usa il solo endpoint canonico `PUT /api/ricette/{id}/prezzo-tavolo`: non cambia
  banco o ingredienti. La riga scompare dopo salvataggio e sincronizzazione Menu;
  un errore resta visibile e si puo' riprovare. Ricerca e reparto filtrano i dati gia' letti.
- Le spunte di Ricette **Rosticceria del giorno** e **Pasticceria classica**
  usano `categorie_rapide`, senza un secondo archivio di produzione. Sono gruppi
  operativi modificabili (non si azzerano a mezzanotte): compaiono anche in Produci.
  La scelta esplicita determina il reparto operativo; Rosticceria esclude Colazioni
  e Pasticceria classica. Nessun lotto o quantitativo nasce dalla sola spunta.
- La carta riunisce Colazione/Dolci di «Bar & Dolci» e Pasticceria di Lotti
  nella card **Dolci**; bevande in **Bar**, Rosticceria in **Food**. Il reparto
  misto Altro resta in **Altri prodotti**, senza dedurre il reparto dal nome.
  E' un raggruppamento di presentazione: ID, prezzi e categorie sorgenti restano intatti.
- In Menu admin → Prodotti, la **X nasconde**, non cancella: per Lotti passa
  dall'aggiornamento canonico di `menu_pubblico`, per Qromo aggiorna `visible`
  e la sync conserva i false gia' salvati sullo stesso ID. «Mostra anche nascosti»
  permette il ripristino. «Possibili doppioni» confronta solo il nome, mai fonde o elimina automaticamente.
- La categoria delle ricette nel Menu e' «Produzione Ceraldi» piu' la
  sottocategoria derivata dal reparto. Le categorie si leggono e si creano da Lotti con
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

### Colazioni B&B — colazioni prepagate per gli ospiti dei B&B partner

- **Una pagina sola** (`frontend_colazioni/index.html`, JS senza build) servita da `/convenzioni/` con `StaticFiles`.
  Parla con Supabase solo tramite funzioni RPC `bb_*` `SECURITY DEFINER`; le tabelle `bb_*` hanno RLS attiva **senza policy**:
  la chiave pubblicabile non legge niente da sola. Le funzioni sono in `frontend_colazioni/sql/` (`supabase.sql`, poi `supabase-N.sql`).
  La catena e' completa fino a v28: v1-4, 7, 8, 10 e 13-28 in `frontend_colazioni/sql/`, le cinque che mancavano (v5, v6, v9, v11, v12)
  in `supabase/migrations/` come `…_colazioni_bb_vN_*.sql`; sono gia' applicate, i file non vanno rieseguiti.
- **Tre ruoli, tre link**: titolare (`#/titolare`), albergatore (`#/hotel/<accesso>`), ospite (`#/ospite/<codice>`, un QR per camera, **mai prezzi**). Il QR del voucher è il link ospite completo e lo scanner accetta codice o link; «Copia link per NFC» copia il link ospite, «Copia link recensioni» è un bottone a parte.
- **Audit del 02/10/2026** (`supabase/migrations/20261002132237_colazioni_audit_02_10.sql`, applicata a pezzi): gli ordini mattutini dell'albergatore (`/api/colazioni/ordini-prodotti/albergatore[/elenco]`) sono in `PUBLIC_PATHS` col motivo (la credenziale è il token `tk:` di Supabase, verificato dall'handler con `bb_alb_stato`, 401 se il database lo rifiuta; ogni altro `/api/colazioni/*` resta chiuso dal middleware, `test_colazioni_accesso.py`). **Extra per giorno** (titolare): `bb_vouchers.extra` è `[{giorno, voci, totale}]`, l'incasso è per giorno (`extra_pagati_giorni`, `bb_tit_extra_incassato(p,vid,pgiorno)`), l'ospite ordina per il giorno scelto (`bb_ospite_salva(…,pgiorno)`: mai passato né fuori soggiorno; un giorno incassato non cambia più), Produzione e scanner mostrano solo gli extra del giorno, la differenza senza glutine è una voce del giorno in cui l'ospite salva; prezzi sempre dal catalogo, mai dal browser; la colonna `extra_pagato` resta inerte. **Annullo**: l'albergatore rimborsa solo entro `data_fine`, dopo decide il titolare con motivo a chip (`bb_tit_annulla(p,vid,pmotivo)`; `annullo_motivo/annullato_da/annullato_il`). `bb_ospite_salva` valida `richieste` (solo `allergie` = id di `menu.menu_allergens`, `nota` ≤500, `modifiche` con chiavi note) e la pagina legge ogni lista con `Array.isArray`; un codice sconosciuto dà `{errore}`, non un'eccezione, così il conteggio per IP resta scritto. Codice voucher a 16 caratteri (i vecchi a 10 restano validi); `bb_ospite`/`bb_ospite_salva` limitate per IP (`ospite:<ip>`, 60 in 10 minuti, 15 di blocco); `bb_ip()` ricade su `x-real-ip`/`cf-connecting-ip` e la soglia per IP vale solo con IP noto. Il titolare non cambia il PIN dell'albergatore (`bb_tit_struttura_salva` tocca solo nome, indirizzo, telefono, email); una struttura si **disattiva** con `bb_tit_struttura_disattiva(p,sid,pmotivo)` (PIN e inviti azzerati, sessioni fatte scadere, link recensioni spento; borsellino e storico restano) e si riattiva solo con un nuovo invito (`bb_tit_invito_rigenera`); una struttura `demo` deve prima registrare il gestore (v24: `registrazione_richiesta`). Recensioni: senza `recensioni_informativa_url` nessun consenso può essere «sì» (RPC e UI); il consenso registra la `fonte` della visita; con `bar_lat/bar_lon/bar_raggio_m` in `bb_config` ogni posizione porta `distanza_m` e `in_sede` (null se mancano), solo informazione, mai un blocco. La pagina ha una CSP (`connect-src` solo Supabase e `self`), `integrity` su qrcodejs e nessun valore interpolato dentro un `onclick` (id/`data-*` più listener). **Le vecchie firme sono rinominate `*_v23` e chiuse ad anon, non eliminate** (`bb_alb_crea_voucher`, `bb_alb_crea_batch`, `bb_tit_menu_*`, `bb_tit_bar_set`, `bb_tit_voci_salva`, `bb_pin_stato`, `bb_tit_tavolo_set` e le firme precedenti di `bb_annulla`, `bb_tit_annulla`, `bb_ospite_salva`, `bb_tit_extra_incassato`, `bb_tit_struttura_salva`, `bb_recensioni_posizione`): lo strumento di sessione blocca ogni cancellazione, e una chiusura di sessione è `scade=now()`. `gc_assert_runtime_secret` e le colonne `bb_prodotti.descrizione_lunga/materiali` sono ora nel registro delle migrazioni.
- **Titolare: nessun PIN suo, vale quello del gestionale.** La pagina chiama `POST /api/colazioni/accesso` (`app/routers/colazioni.py`, solo admin,
  cookie o Bearer dell'ERP, MFA compresa); il backend chiede al database `bb_tit_sessione_apri` con la chiave di runtime `x-gc-api-key`
  (la stessa di `gc_assert_runtime_secret`) e restituisce un token `tk:…` valido 12 ore, che la pagina passa come `p` alle RPC. Se il gestionale
  non e' aperto, la pagina chiede il PIN e lo verifica con `/api/auth/pin-login`. Cambiare o resettare il PIN del titolare = farlo nel gestionale.
- **Albergatore: PIN suo.** Lo sceglie con l'invito (`#/invito/<token>`, e' la registrazione) e riceve un **codice di recupero** (8 caratteri, si vede una sola volta,
  in `bb_strutture.recupero_hash`). PIN perso: `#/recupero/<accesso>` con codice e nuovo PIN; senza codice, «Chiedi aiuto al bar» crea una richiesta
  (`bb_richieste_pin`) che compare nel Cruscotto e si chiude mandando un nuovo invito. Dal Profilo cambia il PIN e rigenera il codice.
  L'accesso passa da `bb_alb_login`, che dopo 5 errori blocca per 15 minuti (`bb_tentativi`, anche per IP): le altre RPC accettano solo il token di sessione
  (`bb_sessioni`, 12 ore) e mai il PIN, perche' un'eccezione annulla il conteggio dei tentativi. Non esistono piu' una «modalita' prova senza PIN» ne' un PIN
  del titolare nel database (`supabase-21.sql`): `bb_check_*` non sono chiamabili dall'esterno e `bb_pin_off()` risponde sempre falso.
- **Colazioni per struttura**: ogni hotel ha le sue colazioni (`bb_colazioni`, con nome, prezzo a persona e voci dal catalogo o libere).
  Le **standard** sono le stesse righe con `struttura_id` nullo: si importano in una struttura e poi si personalizzano, senza legame.
  L'albergatore compila una pagina sola: camere, ospiti, dal/al, colazione. Un voucher vale per tutto il soggiorno (massimo 31 giorni),
  fino a tanti ritiri al giorno quanti sono gli ospiti. Ogni camera ha il proprio valore predefinito `servizio_tavolo`, modificabile
  nella singola prenotazione: solo le righe spuntate aggiungono al prezzo dell'hotel il supplemento configurato
  (`bb_config.supplemento_tavolo`, 1,50 € a persona per colazione); le altre restano al banco.
- **Fatture delle ricariche**: ogni ricarica che diventa confermata (carta SumUp, contanti al bar, ricarica registrata a mano) crea una riga in `bb_fatture_da_emettere`
  (trigger `bb_trg_fattura_ricarica`, una sola riga per movimento). L'albergatore inserisce i **dati fiscali** (ragione sociale, P.IVA o C.F., indirizzo, codice destinatario/PEC) in registrazione o nel Profilo
  (`bb_alb_fiscali_salva`, validati lato server); senza dati completi non puo' ricaricare con carta. Il titolare le lavora nel tab **Fatture**: copia i dati, emette la fattura da SumUp Fatture
  (l'API pubblica di SumUp **non ha** endpoint per le fatture: provati `/v0.1/me/invoices` e simili, tutti 404) e segna numero e data; «Non dovuta» chiude le prove. Aliquota IVA e momento dell'emissione
  (buono corrispettivo monouso: IVA gia' alla vendita?) li decide il commercialista: l'app non calcola l'IVA.
- **Borsellino**: il saldo e' la somma dei movimenti confermati (`bb_saldo`); annullare un voucher rimborsa le non ritirate.
  Ricarica con SumUp (checkout ospitato lato server, `bb_sumup_verifica` accredita solo con stato PAID e importo e riferimento uguali;
  la chiave sta nel vault `sumup_api_key`) o in contanti al bar (il titolare conferma). **SumUp non e' ancora attivato**: manca la chiave.
- **Menu**: catalogo proprio `bb_prod_cat`/`bb_prod_sub`/`bb_prodotti` importato da Qromo, **separato** da `menu.*` che non si tocca.
  I prezzi in uso sono quelli **banco** (i prezzi tavolo restano in `prezzo_tavolo`); gli allergeni sono l'unione di Qromo e del gestionale.
  Foto, testi lunghi e ingredienti sono file statici in `frontend_colazioni/menu-img/` (`extra.json`). Extra dell'ospite: prezzi calcolati
  dal server, si pagano al bar; le versioni senza glutine (`bb_senza_glutine`) aggiungono solo la differenza.
- **Scelte giornaliere dell'ospite** (v27-v28): il QR resta unico per tutto il soggiorno; extra e incassi usano il formato giornaliero
  verificato dall'audit, mentre modifiche e sostituzioni sono in `bb_voucher_giorni` per la singola data. Lo stesso QR propone oggi e
  consente di preparare i giorni futuri con tre sole azioni (cambia prodotto, aggiungi extra, allergie). Produzione e scanner leggono
  esclusivamente la scelta del giorno; limiti per IP, validazione server e prezzi da catalogo restano obbligatori.
- **Avvisi operativi esterni** (v26-v28): la prenotazione dell'albergatore e ogni nuova composizione di extra dell'ospite accodano una
  notifica idempotente. Lo scheduler la invia al Telegram del titolare senza dipendere dall'app aperta e senza mostrarla all'albergatore;
  il testo non contiene il nome dell'ospite e l'extra indica la data a cui appartiene.
- **Dati esterni** (navi e scioperi) in cache `bb_esterni`, aggiornata dal database con l'estensione `http` (Guardia Costiera EMSWe per le navi,
  RSS del MIT per gli scioperi), al massimo ogni 20 minuti.
- **Recensioni post-consumo** (v23): dalla scheda di ogni struttura il titolare genera i link QR/NFC/Wi-Fi
  `#/recensioni/<token>/<fonte>`. Geolocalizzazione e WhatsApp sono scelte esplicite, separate e mai preselezionate;
  ogni consenso, diniego e revoca conserva timestamp, struttura, fonte e versione informativa. Solo l'opt-in WhatsApp
  con numero valido crea una riga in `bb_recensioni_inviti` dopo la conferma di fine colazione. Lo scheduler la invia
  con un template Meta approvato e ricontrolla l'ultimo consenso prima di acquisirla. URL Google/Tripadvisor, informativa
  e ritardo si configurano dalla scheda; token e phone number id Meta restano nelle variabili Render.

## Stato attuale (al 02/10/2026 — riscrivere sul posto)

- Ogni merge su `main` fa ridistribuire Render: per qualche minuto la produzione può essere `degraded`. Non si accodano merge. La health del commit `0187a45f`, letta il 30/09 alle 17:54 UTC, dichiarava `hydrated_rows=249598`, `hydration_errors=0`; il vecchio valore ~77.000 non è una misura corrente.
- TFR: la lettura RPC del runtime il 30/09 misura **1.239** righe in `tfr_accantonamenti`. L'assenza nel deposito relazionale HR, l'importo aggregato e lo stato dell'ingest posta restano baseline da riconfermare; non sono stati interrogati nell'audit in sola lettura.
- **Spento**: il giro completo del protocollo, `PROTOCOLLO_DRIVE_ENABLED=false` (RAM a 1,57 GB su 2). **Acceso**: scheduler, cartella unica Drive, giro incrementale del protocollo (ogni 20 minuti), ponte pagamenti HR, dedup fatture.
- Fatture: lettura RPC del 30/09, **1.539** righe, **1.526 del 2026** e 13 precedenti (8 del 2024, 2 del 2019, 2 del 2022, 1 del 2025). `invoice_date`, `invoice_number`, `total_amount` presenti su tutte; `id` testuale su 753, numerico su 786. Orfani e collisioni non rimisurati: non assumere zero. Il pre-2026 non è quindi interamente fuori archivio.
- **Gli XML di fattura 2026 arrivano su Drive a blocchi manuali** dal portale AdE: il ritardo è a monte.
- **Numia dismesso** dal 05/09/2026: dal 01/08 al 04/09 le chiusure Numia vengono dagli accrediti in banca (50 giornate 2026 ancora da ricostruire al 28/09, 43.115,18 €: le fa il job bancario corto). POS corrente = solo SumUp (API).
- **Estratto ufficiale BPM**: in archivio fino al 31/03/2026; il PDF al 30/06/2026 va caricato in Documenti > Import (lettore corretto il 28/09); operativo fino al 28/09 da CSV e Enable Banking.
- **Import minisito Drive completato** (dichiarazioni fiscali 826: 770, Redditi SC, IRAP, IVA, LIPE; F24 unificati 263; quietanze 548). Le dichiarazioni importate prima del 30/09 non hanno i quadri né le coordinate: si ripassano da Documenti > Import. Le IRAP `IRA_T…` e gli UNICO si riconoscono per nome e per il quadro IR/IS, mai come F24 anche se citano «Versato in F24».
- **Corrispettivi XML fino al 21/09/2026** (letto il 01/10; la copia serale RT è ferma dal 28/08); il CSV AdE di settembre copre il 23–30/09 come provvisorio. 08, 10, 14 e 17/09 non sono buchi: l'RT le ha chiuse col giorno dopo (progressivi consecutivi).
- **Nessuna liquidazione IVA calcolata**: `/api/iva/liquidazioni` torna vuoto; giugno e luglio sono calcolabili ma con **zero** acquisti (tutti `detraibilita_da_verificare`). LIPE 2026 (tre periodi, quadrati): marzo combacia al centesimo, a gennaio mancano **5.005,88 €** di IVA detraibile. Nessun F24 IVA 2026.
- Foto ricette Lotti: 20 su Storage, 307 su Drive in `FOTO E IMMAGINI/ricette_immagini_per_nome` (ricollegate per ID da `Mappa_immagini_ricette.csv`); da portare su Storage. DRV-16 chiuso nel codice: nessuna lettura di `GOOGLE_DRIVE_*_FOLDER_ID` per sezione, `DRIVE_*_FOLDER_ID`, `DRIVE_FOLDER_REGISTRY_JSON`, `GOOGLE_SERVICE_ACCOUNT_JSON_*`, `DRIVE_SIMULAZIONE_{BATCH,EDIZIONE,SOLO_TIPO}`, `ADMIN_PASSWORD(_HASH)`; su Render si cancellano a mano. La radice di `DATI SOCIETA CERALDI` conteneva ~5.500 file sciolti (3.717 PDF, 1.375 XML): li smaltisce lo smistatore a lotti.
- Lettura del Menu pubblico del 30/09: **323** prodotti, **108** con allergeni e **215** senza elenco. Le esclusioni motivate e le conferme «nessuno» richiedono il controllo riservato prima di classificare tutti i 215 come violazioni.
  Menu clienti: il QR legge solo `menu_qrcode_config.menu_url`; social in `collegamentiPubblici.js`, privacy e cookie sono pagine del Menu (`/menu/privacy`, `/menu/cookie`) col titolare da `/api/menu/titolare`.
- **Lotti indietro**: 163 fatture alimentari da giugno bloccate dal ponte (conflitti d'impronta), ultimo lotto 14/09. 119 lotti su 344 in unità non convertibili (95 KAR); 320 descrizioni con proposta web da confermare; scadenza su 15 lotti su 580, lotto vero su 27.

Correzioni dell'audit del 30/09 preparate nel workspace, **non pubblicate**:
GitHub nega push e apertura PR con HTTP 403. Il ponte Lotti verifica che
l'ID restituito dall'importatore esista prima di creare la ricevuta; una
ricevuta incompleta o riferita a fattura eliminata resta recuperabile. HR e
Lotti verificano stato/PIN nell'anagrafica anche sui token già emessi; il
rinnovo conserva l'istante dell'autenticazione originale. Il responsabile
turni accede alle operazioni Turni, non a PIN, paghe e fascicoli; un 403 non
cancella la sessione. `GET turni-config` non scrive e non sceglie omonimi.
La carta clienti del Menu legge gli stessi `menu_*` dell'admin e di Lotti,
con prezzi pubblicabili e categorie non vuote; i prodotti Lotti si
modificano nella ricetta. Qromo resta fonte di dettagli, orari e ordine,
senza sostituire i dati canonici aggiornati. Il router Mutui richiede admin
anche per le letture. I dati storici non sono stati riparati o migrati.

Giornale, lettura RPC del 30/09 alle 18:37 UTC: **1.801** scritture, **1.786
attive** secondo il predicato canonico; **1.746 quadrate** e **40 non
quadrate** (una è uno storno), con differenze assolute complessive **848,25
€**. Il valore non è un saldo da rettificare automaticamente. Tutte le
attive hanno `idempotency_key`, senza gruppi duplicati. La verifica definitiva
dei protocolli per anno e la ricostruzione da fonti restano aperte.

Collaudo locale delle patch: **6.439 test backend passati**, **337 saltati**
(332 HTTP senza backend dedicato, 4 PDF campione assenti, 1 parametro vuoto
nel controllo palette). Frontend: ERP 564, HR 19, Lotti 169, Menu 24 passati.
E2E ERP: 74 schermate e operazioni Cassa/Banca/Provvisori; HR: turno
gestione↔portale; Menu: admin↔carta e pubblicazione. Queste prove usano fixture,
non certificano tutte le relazioni del deposito reale. Runner backend:
`python scripts/collaudo_isolato.py -q`; gli E2E HR/Menu controllano host
locale e marker fixture prima delle scritture.

## Aperto (togliere la voce quando si chiude)

- **Credenziali vere nella cronologia git** (`backend/.env` in 23 commit, `memory/test_credentials.md`, `memoria/DIARIO.md`, `push_impeccable.py`, fra febbraio e aprile 2026, visibili finché il repository era pubblico; oggi non sono in `main`). Prima il titolare **ruota** tutto ciò che c'era (token GitHub, PEC Aruba, password app Gmail/IMAP, client secret PayPal, URI MongoDB Atlas, token WhatsApp, `SECRET_KEY`/`CRON_SECRET`, password admin, codice gestione riservata, chiave Emergent); poi, **solo col suo ok**, la cronologia si riscrive con `git filter-repo --invert-paths` su quei quattro percorsi, push forzato di `main`, tutti i branch e i tag, e ogni checkout si riclona (il PC del titolare compreso). Mai riscrivere la cronologia prima della rotazione: la riscrittura non revoca niente.

- **Lotti, due giri di ricerca web sulle descrizioni di fattura**: `identifica_col_web` (`lettura_articoli_ai.py`, giro `lotti_identifica_col_web`, categoria del Dizionario, `web_cercato_at`) e la campagna `ricerca_web_prodotti` (`app/lotti/routers/scheduler.py`, schede e `nome_mapping`, `ricerca_web_tentativi`, mai un tentativo registrato). Condividono l'helper `cerca_sul_web` ma sono due code e due contatori: fonderli in un giro solo.

- **Lettori AI doppi, da ridurre a `LlmChat`**: `ai_document_parser` (vision, catena `mittenti_email_sync`, coda `/ai-parser/da-rivedere`, `BatchProcessor.jsx autoMode`), `llm_document_parser` (verbali), `enhanced_document_parser` (cedolini), `document_ai_extractor` (fatture estere, modello fisso `claude-sonnet-4-5`), `hr/document_ai_extractor` (guscio), `ai_categorizzazione` (haiku fisso), `chat_ai_engine`, `fiscal_agents`: due lettori per verbali, cedolini e fatture, tre pipeline di classificazione dell'inbox (`documents_inbox_classify.auto_classify`, `ai_integration_service`, proposte), otto client Anthropic propri senza tetto né `usage` comune. Anche `cerca_sul_web` di Lotti deve contare sul tetto di `LlmChat`, non su `sync_status`. **Dopo il deploy**: `POST /api/agenti/proposte/giro` (admin) per il primo lotto, poi in `/agenti` › Settori provare che «Vedi» apra un file in `ERRORI` e che una conferma lo sposti davvero in `ELABORATE`.
- **Fornitori, da lanciare dopo il merge** (admin, prima `dry_run`): `POST /api/suppliers/magazzino/allinea` (le 88 esclusioni di Lotti sull'anagrafica); per BIG FOOD SRL `POST /api/suppliers/{id}/applica-metodo-dal` dopo aver messo «Metodo valido dal» 01/01/2025 sulla scheda (oggi è 30/09/2026 per un salvataggio della scheda). Le 6 fatture BIG FOOD già pagate con assegno, banca o dichiarazione in banca (2.711,38 €) restano dove sono finché il titolare non dice diversamente.

- **Termini di recupero**: la regola dei termini vive in una vista SQL (`verifica.tabulato_tributi_termini`, migrazioni `…013008` e `…013741`), non in Python con test: se cresce o va corretta, portarla in `termini_recupero.py` con i casi del foglio del 01/10/2026 (27 righe ancora recuperabili su 98 senza versamento al 01/10).

- `legacy_staging` (5 tabelle, ~1 MB; le altre 51 sono state cancellate: gia' nel gestionale al centesimo): restano i dati che il gestionale non puo' ricevere senza una via con admin.
  `residui_fatture_2026` (le 21 righe gia' nel gestionale per numero e importo non ci sono piu'; restano **8 parcelle FPR pagate** nel 2026 senza XML: Carini 3.206,40, Marotta 1.122,24 + 1.517,70 + 1.656,64,
  Ferrantini 1.122,24 ×3, Graziuso 2.300,00 contanti — servono gli XML dal portale AdE), `catalogo_ceraldi` (caricato in produzione come listini, vedi «Listini»: 808 righe verificate; la tabella si cancella con `select gestionale.consenti_cancellazione();` e `drop table legacy_staging.catalogo_ceraldi;`), `movimenti_carta`
  (34 movimenti carta gen–giu 2026, 18 con fattura collegata a mano: gli estratti Nexi correnti sono PDF mensili senza righe), `presenze_acconti` (da registrare in HR
  l'acconto TFR di 1.800 € a Capezzuto del 31/07/2026 e uno stipendio di agosto) e `presenze_profili` (IBAN e profilo di Murolo, assente dall'HR corrente: da chiedere al titolare se e' un ex dipendente).
  Si migrano con le vie normali (mai con SQL a mano: l'acconto TFR scrive anche il giornale), poi lo schema si cancella.
- **Collaudo funzionale dei flussi, resto**: HR — `riepilogo-aziendale` HR filtra `status` dove l'anagrafica usa `stato` (da verificare), la liquidazione TFR di HR attinge solo dal valore manuale e non dalle quote da buste, il percorso HR «Buste da email» (`/paghe/importa-email`) ha un lettore proprio fuori dal motore unico dei cedolini; corrispettivi — unificare la dedup delle due strade (`ingest_corrispettivo_parsed`, `importa_csv_ade`); F24 — all'import di un modello l'addebito si cerca due volte con la stessa funzione idempotente (`cerca_controparti_f24` e handler `on_f24_acquisito_riprocessa`): togliere il passo `banca` dal primo. **Da lanciare dopo il deploy** (admin, prima `dry_run`): `POST /api/admin/f24/ripubblica-evento-acquisito`. Decisioni del titolare in attesa: nessuna (le dodici del 02/10/2026 sono nel codice; Flotta: targhe→driver→dal da scrivere quando il titolare è al PC).
- **Residui «legacy» con dati o writer vivi** (da decidere uno a uno, non si cancellano alla cieca): `piano_conti` (31 righe, letta da `_conti_operativi_legacy` in `routers/accounting/piano_conti.py`; il piano ufficiale è in Python), `attendance_presenze_calendario` (HR, `set-presenza` la scrive ancora), `email_fornitori` (Lotti, `email_ordini.py` la scrive e la elenca), `hash_pin_legacy` (HR: i PIN col vecchio hash restano validi finché ogni persona non ne imposta uno nuovo), `extracted_documents` (vuota; `/da-rivedere` e `/da-rivedere/{id}/classifica` in `ai_parser.py` da verificare), gli alias 307 e `LegacyRouteResolver` (indirizzi già in circolazione), e i rami «schema legacy» di `alerts.py`, `scadenze.py`, `fiscalita_italiana.py`, `suppliers_module/base.py` (`_legacy_supplier_view`): togliere ognuno solo dopo aver contato le righe con quello schema.
- **Da lanciare**: `registra-pregresso` per le **21 giornate** 31/03–30/07 tenute fuori dal giornale dal
  non riscosso (67.856,00 €); fuori restano 3 giornate a incasso zero (giusto) e il **02/08**, XML che non quadra di 0,90 €.
- **All'avvio un solo `server_failed`** (02/10/2026, dopo #1020 e #1021): nei primi 5 minuti i giri di recupero partono insieme (quietanze orfane, lettura articoli AI di Lotti, letture `ssl`/`aiohttp decompress_sync` del caricamento cache) e il loop resta fermo 4-6 s; il riavvio ogni 20 minuti è chiuso, resta da scaglionare i giri d'avvio o portarli in thread.
- Endpoint sincroni oltre i 5 minuti, da portare a lotti riprendibili: `/api/paypal-api/riconcilia`, `/account-ids-non-mappati`, `riallinea-pagamenti-fatture`.
- Note di credito TD04 legacy (~20): costo/IVA/debito aumentati anziché ridotti.
- **Estratto conto SumUp** (conto 19.01.05, PDF o CSV «Resoconto transazioni»): un lettore solo (`sumup_conto.py`, saldi verificati riga per riga) scrive in `sumup_conto_movimenti`, **mai** in `estratto_conto_movimenti` (lì i motori lo leggerebbero come BPM su 19.01.01); il payout si cita per `payout_id`, il bonifico a Ceraldi Group è un giroconto a due gambe verso BPM. Stipendi e fatture si abbinano con **gli stessi motori** del conto BPM puntati sulla carta (`abbina_movimenti_sumup`: dopo l'import, nel job bancario corto `banca_versamenti_proiezione` — il giro lungo ogni deploy lo interrompe — e all'arrivo di un cedolino); la collezione la dice l'id (`collezione_del_movimento`); un bonifico che cita le sue fatture in causale le paga se la somma torna al centesimo, anche in più bonifici dello stesso fornitore ripartiti per data (`reconcile_cited_invoices`), e una riga del vecchio import (`sumupbiz_…` su 19.01.01) passa sul conto della carta. Prima Nota > SumUp mostra la quadratura con l'estratto (righe da registrare, scritture che l'estratto non ha). Aperto: la coda «Scegli fattura» non apre ancora i movimenti della carta, e la «Deduzione SumUp» di 1,01 € del 03/08 (`rettifica_payout`) scrive un'uscita sulla Mastercard che l'estratto non ha.
- **L'export «Spese» di SumUp (xlsx: Importo netto, Importo IVA, Fornitore, Stato del pagamento) non è un estratto BPM**: il parser generico prendeva l'ultima colonna «importo» (l'IVA) e il 29/09 scrisse 25 righe con 0,00 e la categoria al posto della causale. Ora `e_export_spese_sumup` lo riconosce e il parser bancario lo rifiuta (422); da Documenti > Import (`spese_sumup`) `arricchisci_da_spese_sumup` aggiunge fornitore, categoria e IVA ai movimenti SumUp che l'estratto ha già (lordo = netto + IVA al centesimo, entro 3 giorni, uscita, un solo candidato; ambigui e senza movimento si elencano, mai creati). Le 25 righe già scritte (`expenses_2026-08-01_2026-09-22.xlsx`) le mette in quarantena una sola volta l'avvio (`doppioni_estratto_conto._applica_import_errati`, marcatore in `migration_runs`, per id e col motivo; stesso comando manuale `POST /api/estratto-conto-movimenti/quarantena-import-errato?source_filename=…&dry_run=` per un altro file). Lo stesso avvio fa, con un marcatore per file (`IMPORT_ERRATI_AUTORIZZATI`), per le 242 righe dell'export «Elenco Entrate Uscite» senza segno, tutte entrate come «entrata» (`segno_assente` ora lo rifiuta): la gemella corretta c'è già in archivio, la Prima Nota nata dalle righe sbagliate si storna.
- **Bonifico con la fattura nella causale**: `classifica_destinazione_dipendente` non lo tratta da stipendio nemmeno col nome di un dipendente (`causale_fattura`, salvo parole di stipendio/TFR); l'Archivio bonifici mostra il numero della fattura e `fattura_esito` (`intero`, `acconto`, `eccede`: importo contro il dovuto netto di ritenuta) e non propone «Scegli periodo» a un bonifico con la fattura collegata o esito HR `non_stipendio`.
- **Pregresso fatture**: 299 attive (173.184,83 €, gennaio–maggio) senza partita: le rigioca il job bancario corto (`ripubblica_a_lotti`). Con `dry_run`: `azzera-scadenze` (642 fatture,
  971 partite inventate), `lipe/importa`.
- Riconciliazione: 158 fatture `riconciliata` con movimento non riconciliato, 180 righe hub senza `fattura_id`, ~260 movimenti banca senza categoria (bonifici disposti e SDD: si chiudono solo abbinandoli).
- HR: 38 bonifici con `cedolino_id` orfano, 138 in «bonifici da associare» (120 con proposta da confermare; 18 senza prova), 10 tabelle attese dall'app
  assenti (turni_config, onomastici, richieste…), Iazzetta senza IBAN; Appuhamy, Aurigemma, Vitiello,
  Dell'Aquila da creare cessati; UNILAV Moscato e Pocci.
- Noleggio: `veicoli_noleggio` è **vuota** in produzione (nessun driver né storico; le 4 targhe GX037HJ
  ALD, GW980EP Arval, HB411GV Leasys, GG782PN cessata vivono solo nelle fatture); bonifici al Comune e pagamenti
  Mooney via PayPal sono candidati senza verbale. `verbali_noleggio` ha 347 righe (lettura del 01/10): 132 `VERB-…` nate dalla PEC, 141 con
  il PDF salvato sul verbale (`pdf_data`, le 132 PEC più 9), 69 in quarantena e il resto letto dal PDF o nato da un numero di fattura
  (`fattura_ricevuta`). Per le righe lette dal PDF il `source_document_id` non è più in `documents_inbox` e senza `pdf_data` non hanno l'originale. Da fare con l'autorizzazione del titolare: l'anteprima
  `POST /api/verbali-noleggio/ricostruisci-da-pdf`, poi `dry_run=false`; ricaricare da Documenti > Import gli originali dei
  105 (le ricevute e gli avvisi PartenoPay sono su Drive); il pacchetto `PARTENOPAY_NAVIGABILE_PRONTO.zip` non è stato
  trovato su Drive, va caricato da Documenti > Import (prima l'anteprima `…/import-partenopay`).
- A mano, dal titolare: **installare la copia serale RT sul suo PC** (`scripts/installa_sync_rt.ps1`, recupera da sola le giornate dal 28/08); password Postgres; DNS ceraldiapp.it.
- Fork `app/hr/`: **quattro** sottopercorsi ancora duplicati (`routers/employees/dipendenti.py`, `routers/pin_login.py`,
  `routers/tfr.py`, `utils/dependencies.py`): ogni correzione va cercata anche nel gemello.
- **Minisito fiscale**: la cartella Drive è stata letta per intero (5.111 file: 348 nuovi, 4.472 già presenti, 154 non riconosciuti, 80 in errore); i PDF non riconosciuti sono soprattutto ISA e quadri sciolti e documenti 2006–2011. Al 01/10/2026 in `drive_cartella_unica` restano **175 F24 e 66 quietanze** in errore (non i «circa 40» di prima: i 40 erano solo i non quadrati con dettaglio), per causa: F24 — 54 non quadrati salvati prima del dettaglio (il ripasso li spiega), 25 nessuna riga letta dal modello, 24 con righe lette ma differenza da guardare, 20 con la sola riga DM10 letta e le altre sezioni perse (stampe «Converted from …/stp/…», formato banca 2020–2021), 12 righe 9001–9958 (rate e sanzioni), 11 con saldo 0 e anno/periodo letti come importo (2006–2018), 9 senza righe tributo (non sono un modello), 8 tributi locali/TEFA con l'importo letto nel credito, 6 PDF non apribili, 3 senza testo, 3 con anno/periodo letti come importo; quietanze — 27 non quadrate senza dettaglio, 20 senza livello testo (scansioni), 18 senza righe tributo (non sono una quietanza), 1 transitoria. **Nessuna di queste cause è un caso risolto senza il PDF**: il lettore legge per coordinate e le coordinate di quelle famiglie non si ricavano dall'errore (il lettore si corregge con un PDF di ognuna, mai forzando); il nuovo ripasso (`VERSIONE_RIPASSO` 2026-10-01) scrive nell'errore anche il bordo destro degli importi letti (`x1 d/c`), che dice dove cadono le colonne. I 58 errori transitori (56 dichiarazioni fiscali con timeout di Supabase, NUL nel testo OCR o memoria esaurita, 1 quietanza, 1 altro file) si rileggono da soli (vedi «Ingresso documenti»). «Giugno 2026» resta bloccato: il credito di 63,28 € della pagina 2 non è nel saldo stampato (decide il titolare). Saldo IRAP 2024 (5.164,00 €) e acconto IRAP 2025 (4.238,00 €) senza quietanza: da verificare col commercialista. **18 quietanze doppie** (17 protocolli, stesso protocollo e stesso saldo, 21.727,35 €; verificato in sola lettura il 01/10: nessuna in quarantena, nessun doppione fra le 293 senza protocollo) da mettere in quarantena con `/api/doppioni/ripulisci` (prima `dry_run`, poi `dry_run=false` con l'autorizzazione del titolare). Le due quietanze del 16/09/2026 (invio `26091616120422319`, `/000001` 9.421,15 € e `/000002` 104,54 €) sono già in archivio col riscontro CERTO sull'addebito del 17/09 e senza modello (`f24_mancante`: il modello del commercialista non è arrivato).
- `gestionale.blobs`: oltre ai backup di Lotti, 216 PDF che **nessun documento cita**; come `bank_reconciliation_hub` (2.017 righe), scritta da un trigger e letta da nessuno.

- **Relazioni documentali (DRV-03)**: da lanciare, in quest'ordine e sempre prima `dry_run`: `POST /api/indice-relazionale/protocollo-collegamenti/bonifica` (103 collegamenti del protocollo verso quietanze fuse con una copia: 102 riagganciabili con l'MD5 del file, 1 senza entità), `POST /api/cedolini/canale/bonifica` (buste senza `canale`), `POST /api/indice-relazionale/relazioni-documentali/backfill` (poi ripetere finché `restanti`=0). Restano: l'originale delle buste con molte copie e nessuna impronta propria (nessuna prova dice quale sia «il» file: decide il titolare o un nuovo lettore), `drive_file_id` sulle righe HR, la vista «documenti collegati» (DRV-04, MINI-08) e le fonti senza impronta né `drive_file_id` (estratti conto bancari BPM, inbox senza hash).
- **Protocollo personale**: il registro xlsx su Drive non è ancora importato (prima `dry_run`, poi l'import autorizzato); manca la ricerca sull'intero testo (colonna indicizzata, DRV-02), la lettura dalla pipeline invece di un `file_id` dato a mano (DRV-05); la pagina React c'è (`/protocollo/AAAA/NNNNNN`).
- **Notifiche PEC dei verbali**: circa 136 PEC in archivio (`verbali_email_attachments`) non sono ancora agganciate ai verbali veri, e nate come righe `VERB-…` senza targa né importo: prima l'anteprima (`POST /api/verbali-noleggio/notifiche-pec/aggancia`, `dry_run`), poi l'aggancio. Le righe `VERB-…` non si cancellano; si decide dopo l'anteprima se metterle in quarantena. La ricostruzione dal PDF (sopra) completa i campi del verbale vero dalla copia conforme.
- **IVA, cosa manca** (verificato sul codice): acconto 6013 e saldo 6099 come calcolo, maggiorazione 1% dopo il 16/03, credito annuale da dichiarazione e compensazione orizzontale (soglia 25.000 €), conguaglio di dicembre; il confronto con la LIPE non copre 6013, 6099, trimestrali e credito riportato. La scadenza fissa del 27/12 (`fiscalita_italiana.py`) non si sposta al lunedì. `schemas/accounting_rules.py` descrive 6001/6002 come «saldo» e «acconto» ma sono gennaio e febbraio. `_credito_precedente` esiste in due copie (`routers/iva.py`, `iva_liquidation_query.py`): ridurle a una.
- **Bilancio e competenza**: `routers/accounting/bilancio.py` seleziona i costi per data documento **oppure** data ricezione e ignora `data_competenza` (una fattura di dicembre ricevuta a gennaio può finire nell'esercizio sbagliato o in due); il debito nello stato patrimoniale usa lo stato «pagata» di oggi, non la data di pagamento rispetto a fine esercizio; il costo del personale è il solo lordo (contributi `None`).
- **Chiusura dei debiti**: il pagamento di F24, stipendi e fatture aggiorna la Prima Nota ma non scrive in `movimenti_contabili` lo storno del debito (33.03.01, debiti tributari, stipendi); il debito nello stato patrimoniale è un flag, non un saldo di conto. `scrittura_imposte` e `scrittura_versamento_iva` (`contabilita_generale.py`) non hanno chiamanti: chi le usa deve sapere che il saldo F24 non è un costo. Imposte, IVA e contributi confluiscono tutti su `CONTO_ERARIO_IMPOSTE`. Da concordare col commercialista.
- **Apertura dell'originale, resto**: il portale HR e l'HR admin hanno i loro indirizzi di file (`/hr/api/portale/buste/{id}/pdf`, `…/documenti/{id}/file`, `cedolini/{id}/download`, contratti, esiti paghe), con le regole del portale (un dipendente vede solo le sue buste) che l'endpoint unico, riservato all'admin dell'ERP, non ha: restano finché non si decide come far valere lo stesso servizio con un token da operatore. `drive_document_index` (indice Excel) non alimenta più nessuna scheda, ma lo leggono ancora `AttiAmministrativi` (`list_administrative_documents`), `/drive/fiscal/sync` e i due upload `drive_f24_model_upload`/`drive_declaration_upload`, che lo aggiornano: va tolto con loro (DRV-16).
- **F24 e banca**: il motore a livelli confronta il saldo intero, non il codice tributo (l'allocazione per singola riga è stata tolta: 0 modelli l'avevano); un modello senza data di versamento (285 su 341 modelli attivi al 01/10, quasi tutti storici) o senza saldo letto non si confronta con la banca e ora lo **dichiara** (`non_riscontrabili`, esiti `data_versamento_assente` e `saldo_assente`, nei conteggi di `riscontri_modelli_banca` e in `quietanze-banca`) senza cambiare le regole d'abbinamento. Le quietanze provate dall'addebito non promuovono ancora da sole il modello a «pagato in banca» se il saldo differisce (ravvedimenti). L'F24 del consulente del lavoro non ha un flusso separato: ritenute 1001/1012 si confrontano con i cedolini solo per somma di periodo, senza collegamento salvato; DM10, INAIL e addizionali non hanno riscontro per dipendente.
- **Colazioni B&B, da chiudere**: attivare SumUp incollando la chiave in Impostazioni; dall'SQL Editor applicare `bb_recensioni_revoca` dell'audit del 02/10 (in produzione resta la v23: contiene la cancellazione delle posizioni che lo strumento di sessione blocca) ed eliminare le funzioni `*_v23` e la colonna `bb_vouchers.extra_pagato`; «Esci» del titolare non revoca ancora la sessione DB; configurare i due URL recensione e l'informativa dalla scheda
  struttura, poi impostare su Render `WHATSAPP_CLOUD_PHONE_NUMBER_ID` e `WHATSAPP_CLOUD_ACCESS_TOKEN` e approvare
  il template `ceraldi_review_invite` con i parametri nome struttura e link;
  emissione automatica delle fatture: serve un servizio SDI con accesso da programma (SumUp Fatture non ne ha; da chiedere all'assistenza SumUp o al commercialista);
  inserire dati veri del bar (orari, WhatsApp, email) e i B&B reali; far rivedere composizioni, ingredienti e allergeni delle colazioni standard;
  varianti di prodotto (latte vegetale, gusti del gelato) salvate ma non ancora scelte dall'ospite; per gli alberghi con servizio al tavolo gli extra usano ancora i prezzi banco;
  il banner «VERSIONE DI PROVA» va tolto al lancio; eliminare i B&B demo (`bb_tit_elimina_demo`).

## Logica dentro al database

Su Supabase ci sono **trigger PL/pgSQL che scrivono dati contabili**: leggere il
codice non basta per sapere cosa succede a una riga. Elenco, ruolo di ognuno e
query su `pg_trigger` stanno in `database/trg_bank_ec_before_write.sql`. La
regola: **una regola contabile si scrive in Python, versionata e testata** — per
questo `trg_bank_ec_before_write` non c'è più, duplicava `proiezione_bancaria.py`
e vinceva perché girava prima. Restano le guardie anti-cancellazione, quelle su
`updated_at` e `trg_bank_ec_after_write`, che alimenta `entity_relations`.

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

**I minuti di GitHub Actions sono a consumo** (repository privato; il 02/10/2026 il limite di spesa ha fermato ogni run, anche su `main`), e sono l'unica voce che cresce col numero di PR: Render e Supabase hanno un canone fisso e un deploy in più non costa niente. Regole del titolare (02/10/2026): **una PR solo a lavoro finito** e collaudato in locale (test backend, test e build dei quattro frontend), mai una per ogni pezzo; sulla PR gira solo `ci.yml`, mentre `produzione.yml` (E2E col browser, audit layout, verifica live) gira **solo su `main`** o a mano; **ogni sessione finisce con un push sul branch di salvataggio** `<branch>-lavori` (un push su un branch senza PR non fa partire nessun workflow: è gratis), perché il contenitore cloud della sessione è temporaneo e il PC del titolare può essere spento: ciò che non è pushato è perso, e la sessione successiva — da PC o da telefono — riparte da `git pull` dello stesso branch, mai da un secondo tronco. Un commit di salvataggio può contenere lavoro a metà; la PR finale no.

**Segreti**: `ci.yml` ha il job «Segreti (gitleaks)» (binario fissato, `.gitleaks.toml` con i soli falsi positivi noti: chiavi di idempotenza, fixture, chiave pubblicabile Supabase, nomi delle variabili in `render.yaml`). Scansiona i file presenti, non la cronologia. Un segreto vero non si aggiunge mai alla lista bianca: si toglie dal codice e si ruota.

Produzione: **https://gestionalecloud.onrender.com**
