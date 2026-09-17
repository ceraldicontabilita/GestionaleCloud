# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

Aggiornato il 18/09/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

Prima di ogni intervento leggere `PROMPT_MASTER.md`: è la specifica normativa
unica. Questo file è soltanto il punto di ingresso operativo per Claude.
Leggere e applicare anche `docs/REGOLA_FISSA_ATTESE.md` per qualsiasi flusso
che crea obblighi, attese, prove o riconciliazioni.

Questo file contiene le regole operative per chi modifica il progetto. Il
codice corrente, i test e la configurazione effettiva di produzione hanno
precedenza sui report storici.

## Memoria canonica unica del gruppo Ceraldi

**[17/09/2026, decisione del titolare] Questo file è l'unica memoria di
progetto del gruppo.** Prima erano sparsi `AppDipendenti/CLAUDE.md`,
`Lotti/CLAUDE.md` + `Lotti/memory/REGOLE_ENZO.md` + `Lotti/memory/claude.md`,
`Menu/` e `Gestionale/AGENTS.md`, con regole che in più punti si
contraddicevano (tre "repository canonici" diversi, due politiche di branch
opposte, due scadenze di sessione per lo stesso PIN). Ora c'è un solo file: i
`CLAUDE.md` degli altri repository sono ridotti a un rimando a questo.

### Le quattro app sono un solo servizio

Un unico servizio Render (`gestionalecloud.onrender.com`, deploy automatico da
`main`) e un unico progetto Supabase servono tutto:

| Cosa | Dove vive ora | Codice |
| --- | --- | --- |
| ERP / contabilità | `/` | `app/` + `frontend/` |
| HR, portale dipendenti | `/hr`, `/hr/portale` | `app/hr/` + `frontend_hr/` |
| Menu pubblico e admin | `/menu` | `app/menu/` + `frontend_menu/` |
| Lotti (HACCP) | `/lotti` | `app/lotti/` + `frontend_lotti/` |

### Siti e repository dismessi — non riaprirli

Verificati spenti il 17/09/2026: `appdipendenti.onrender.com` (404),
`lotti-frontend.onrender.com` (404), `lotti-backend-2wwb.onrender.com` (404),
`www.ceraldiapp.it` (non risponde). Non vanno riaccesi né citati come
indirizzi validi: ogni riferimento residuo nel codice è solo una voce CORS o
un commento. Restano da chiudere a mano, quando il titolare vuole: il DNS di
`ceraldiapp.it` presso il registrar e gli eventuali servizi Render sospesi.

I repository `ceraldicontabilita/AppDipendenti`, `Lotti` e `Menu` restano
come **archivio del sorgente originale**: da lì si è copiato il codice dentro
`app/hr`, `app/lotti`, `app/menu`, e non vengono più deployati. Il repository
`ceraldicontabilita/Gestionale` (con il suo `AGENTS.md` che vietava di
riprendere il codice di GestionaleCloud) non è più raggiungibile: era un
tentativo di riscrittura parallela, abbandonato. **L'unico repository vivo è
`ceraldicontabilita/GestionaleCloud`.**

## Direttive permanenti del titolare

Valgono su tutte e quattro le app, sempre, anche quando non sono ripetute nel
resto del file.

### Metodo
- Rispondere e ragionare **in italiano**, risultati prima delle spiegazioni.
- **Tutto va portato su `main`**: si sviluppa su un branch, ma il lavoro non è
  consegnato finché non è unito su `main` e deployato. Render pubblica solo da
  `main`.
- Le funzionalità **si collaudano davvero** (dati di prova reali sul backend
  live, poi ripuliti), non si dichiarano a posto leggendo il codice. Se il
  titolare mostra uno screenshot con il bug ancora presente dopo un fix, il fix
  non ha coperto quel caso: si indaga da zero sui dati reali.
- Se un problema non si risolve subito, **cercare come lo risolvono altri
  progetti reali** (GitHub, web) e integrare la soluzione, invece di
  descrivere il problema e fermarsi.
- Chiudere ogni sessione con il link di produzione: **https://gestionalecloud.onrender.com**
- Se trovi errori, **correggili**: non limitarti a segnalarli.

### Dati e prestazioni
- **Niente doppioni, codice morto o sistemi paralleli: un solo sistema per
  funzione.** Quando ne compare un secondo, si elimina, non si affianca.
- **Non inventare numeri.** Importi tabellari (CCNL, prezzi, aliquote) vanno
  presi dalla fonte o dichiarati da verificare.
- I dati già letti **si tengono in memoria**: ogni rilettura inutile di
  Supabase o Drive è un costo. Liste, conteggi e lookup usano sempre una
  proiezione senza payload; il payload si legge per id.

### Credenziali
- Token, PIN, password e chiavi **solo nelle variabili d'ambiente di Render**
  (`render.yaml` le dichiara con `sync: false`). Mai nel codice, mai nei file
  di memoria, mai in chat, nemmeno mascherati.
- Per le azioni live che richiedono il PIN, usarlo inline in un singolo
  comando e non scriverlo su disco.
- Mai `git add -A`: si aggiungono solo i file pertinenti e verificati.

### Design (vale per HR, Menu e Lotti; l'ERP ha il suo layout)
- Salvia `#5b7a6b` (scuro `#3f5a4e`) su crema `#faf7f0`; card `#fffefb`,
  bordi sabbia `#e6e0d4`, inchiostro `#2a3329`.
- Semantici caldi: pericolo `#d35f4e`, avviso `#c4894a`, successo `#3d8168`,
  informazione `#8a6f47`.
- **Vietati blu, indaco, viola e ciano**, sia come classi Tailwind sia come
  hex negli stili inline: si rimappano su salvia o sabbia.
- Icone Lucide, mai emoji nelle interfacce nuove (su Android rendono con
  colori di sistema non controllabili).
- Ogni pagina centrata, **mai scroll orizzontale su smartphone**: le tabelle
  larghe diventano card impilate. Tocco minimo 44px.
- Le app portate pari pari mantengono il loro aspetto: nessuna contaminazione
  con il layout dell'ERP.

### Le mani sporche (04/07/2026)
Il pasticcere e il banconista hanno **sempre le mani sporche**: nei flussi
operativi si sceglie da tendine, chip e bottoni grandi, non si scrive a
tastiera. Ogni campo di testo libero (motivi, azioni correttive, note) va
sostituito con opzioni predefinite più «Altro (scrivi tu)» come eccezione.

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

Una prova successiva non crea mai l'obbligo che dovrebbe dimostrare. Il fatto
autorevole crea subito l'attesa; la prova la soddisfa o la lascia
`DA_VERIFICARE`.

I JSON in `memoria/pagine/` e `memoria/popup/` sono mappe tecniche generate:
si aggiornano con `scripts/refresh_json_docs.py`, non a mano.

## Come si tiene questo file

- Qui stanno **regole, architettura e stato attuale**. La cronaca di una
  sessione (cosa si è trovato, numeri del giorno, PR) va in
  `memoria/diario/AAAA-MM-GG.md`, non qui.
- «Stato attuale» e «Aperto» **si riscrivono sul posto**: un fatto superato si
  sostituisce, non gli si affianca la correzione. Una voce chiusa si toglie.
- Una regola nuova nata da un incidente entra nella sezione di regole giusta,
  in una o due righe, con il rimando al diario del giorno.
- `tests/test_claude_md.py` fa rispettare tetto di righe, data
  dell'intestazione e divieto di titoli datati fuori dal diario.

## Archivio dati e architettura

- **Supabase è l'archivio unico** (decisione del titolare, 03/09/2026):
  un solo progetto `GestionaleCloud`, `render.yaml` imposta
  `DATA_BACKEND=supabase`. Drive resta la fonte degli **originali
  documentali**, non il database. Il runtime Sheets sopravvive nel codice solo
  come fallback di sviluppo; l'assetto «Drive-only» è superato
  (`memoria/diario/2026-09-03.md`).
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
  503; `?strict=true` per il 503). Gli scheduler usano una lease distribuita.

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
   (503 per minuti): l'HR fa DDL solo se la tabella manca.
6. **Nessuna cancellazione con filtro.** L'app cancella solo per id tramite
   `gc_delete_documents` / `gc_delete_blobs` / `lotti_delete_*`. `DELETE` e
   `TRUNCATE` a mano sono bloccati dalla guardia; per una manutenzione
   deliberata, nella stessa transazione:
   `select gestionale.consenti_cancellazione();` — e prima un backup in una
   tabella `*_rimossi_<data>` / `*_prima_<data>`.
7. Nessun agente e nessuna sessione automatica deve avere la password
   Postgres: solo l'API con il segreto runtime.
8. Un protocollo non dimentica: un file sparito da Drive diventa
   `stato='rimosso'`, un doppione va in quarantena su richiesta esplicita, una
   scrittura contabile sbagliata si **storna**, non si cancella.

## Le app del gruppo

Ogni app portata è il repository originale copiato così com'è («voglio l'app
così come era»): backend montato come sub-app FastAPI a `/<app>` PRIMA del
catch-all della SPA, import nel namespace `app.<app>.*`, frontend compilato
con la propria toolchain su Render, env con prefisso proprio (`LOTTI_*`,
`MENU_*`, `HR_*`, tutte `sync: false`). Le guardie dell'ERP
(`test_drive_only_architecture`, `test_csrf_cookie_guard`,
`test_no_hardcoded_deprecated_collections`) escludono `app/lotti`, `app/menu`,
`app/hr`. Dettaglio completo del porting: `memoria/diario/2026-09-03.md`.

- **Variabili di build dei frontend**: `REACT_APP_LOTTI_BACKEND_URL=/lotti` e
  `REACT_APP_MENU_BACKEND_URL=/menu`. Mai un nome generico
  (`REACT_APP_BACKEND_URL`): un env Render omonimo vince sul file e manda le
  chiamate a un host spento.
- **HR** (`/hr`, portale `/hr/portale`): login proprio tocca-il-nome + PIN,
  JWT `HR_JWT_SECRET`, sessione 7 giorni. Dati nello schema `hr` via
  `HR_SUPABASE_DB_URL` (`SUPABASE_DB_URL` su Render è vuota: non rimetterla).
- **Menu** (`/menu`, admin `/menu/admin`): il menu vero si gestisce su Qromo
  («Sincronizza da Qromo», cancella solo le righe con `origine IS NULL`). Ogni
  ricetta di Lotti viene replicata nel Menu dal ponte
  `app/lotti/servizi/menu_bridge.py` (`origine = "lotti"`, `lotti_ref`
  idempotente, `menu_pubblico` → `visible`); l'esito `menu_sync` non fa mai
  fallire l'endpoint Lotti.
- **Lotti** (`/lotti`): senza `LOTTI_SUPABASE_URL` l'archivio è in memoria
  (solo test). Riceve le fatture dal feed `/api/integrations/lotti/*`.
- **Doppioni eliminati, da non ricreare**: HACCP nativo (`/tracciabilita`,
  `/api/haccp/*`), pagina «Cedolini paga» (`/salari`), `BustePagaPage` HR,
  import bonifici Drive dentro HR, lettore IMAP dimissioni dentro HR, moduli
  riscritti `frontend/src/hr` e `frontend/src/menu`.

### Personale, PIN, cedolini e pagamenti: un solo sistema per funzione

- **L'anagrafica HR comanda** (`hr.app_dipendenti`): Lotti ne legge una
  proiezione (`sincronizza_operatori_da_hr`), il gestionale si riallinea a HR
  (`riallinea_cessazioni_automatiche`). Un solo stato del rapporto: `attivo` |
  `cessato` con data e motivo; la cessazione revoca il PIN. `PUT
  /dipendenti/{id}` aggiorna **solo i campi inviati**.
- **Un PIN per persona, nella scheda HR**: vale per il portale e per firmare
  in Lotti (bcrypt + impronta HMAC; mai due persone in forza con lo stesso
  PIN; mai un cessato). Il **PIN amministratore è uno solo per ERP, Menu,
  Lotti e HR** (`PIN_HASH_ADMIN`, vedi Sicurezza): apre le pagine riservate ma
  non è un'identità di firma sul tablet.
- **Cedolini**: il gestionale li scarica (Drive e posta) e ne ricava la Prima
  Nota salari; l'archivio che si vede è solo in HR (`hr_cedolini_deposito`,
  richiamato dopo ogni scrittura, dedup per chiave o per CF+anno+mese+tipo,
  mai sovrascrittura). Una cessazione letta in una busta vale solo se non
  esiste una busta successiva.
- **Pagamenti stipendio**: un solo ponte gestionale→HR
  (`hr_pagamenti_deposito`, ogni 15 min). Dipendente da CF → nome univoco →
  cognome univoco; serve un segnale «stipendio» (fascicolo della persona,
  causale, oppure lotto paghe: ≥3 dipendenti lo stesso giorno);
  `BENEFICIARI VARI` → coda; TFR, fornitori e commissioni mai. Stesso
  pagamento da PDF e da banca → un solo esito. Le correzioni a mano in «Paghe
  e bonifici» non vengono sovrascritte dalla sincronizzazione.
- **Dimissioni telematiche** (PDF o PEC): `dimissioni_adempimenti` → alert
  critico + scadenza UNILAV di cessazione a **5 giorni** dalla decorrenza
  (D.Lgs. 181/2000 art. 4-bis); revoca del lavoratore entro 7 giorni
  (D.Lgs. 151/2015 art. 26).
- **Giorni di chiusura** (`chiusure_attivita`): ristrutturazione
  26/01–08/03/2026 e ferie 15–23/08/2026 non sono corrispettivi mancanti.
- **Scopo dello storico**: del passato interessano solo **cedolini e F24**;
  fatture e corrispettivi precedenti al 2026 restano in `legacy_staging` e non
  entrano in `invoices`/`corrispettivi`.
- **Modali HR**: solo il componente `Modal` di `frontend_hr/src/App.jsx`
  (WCAG 2.1 AA); campi dentro `<label>`, `aria-label` sui bottoni ripetuti,
  focus visibile salvia.

### Drive: struttura canonica

- Ogni canale ha `DA ELABORARE | ELABORATE | ERRORI`. Gli id delle cartelle
  stanno nelle variabili d'ambiente di Render, non in questo file.
- `05_PERSONALE_E_CEDOLINI/DIPENDENTI/<COGNOME NOME>/` è il **fascicolo unico**
  della persona: cedolini (profondità 2), `BONIFICI/` (profondità 3, il canale
  bonifico legge solo dentro `BONIFICI`), `CERTIFICAZIONI UNICHE/`. I bonifici
  non stipendio stanno in `03_BANCHE_E_PAGAMENTI/BONIFICI`.
- `10_BILANCI_DICHIARAZIONI/DICHIARAZIONI FISCALI`: canale
  `dichiarazione_fiscale` (decide `classify_document()` dal contenuto; i
  singoli quadri e i documenti estranei si scartano per nome file). Un'impronta
  vista in più posizioni = un solo documento con più `source_occurrences`.
- Un solo motore di import per sezione: un documento storico si mette nella
  cartella `DA ELABORARE` giusta, non si carica da una pagina parallela.

### Fatture: identità e duplicati

`app/services/fatture_identita.py` ricava l'identità dall'XML con lo stesso
parser dell'import. L'impronta del **contenuto** (`content_hash_canonico`,
prefisso di versione `c2:`, insensibile a BOM, a capo, codifica e caratteri
non ASCII) prova che due XML sono la stessa fattura. La dedup tiene la copia
già nel giornale e storna la scrittura del doppione. Collisioni aperte =
`stato_import` di collisione **e** `status` non archiviato. Tre collisioni con
file davvero diversi restano a un operatore.

## Stato attuale (al 17/09/2026 — riscrivere sul posto)

- Produzione stabile dopo i fix del 16-17/09 (avvio, health, memoria).
- **Spento**: `PROTOCOLLO_DRIVE_ENABLED=false` (il giro portava la RAM a
  1,57 GB su 2 GB: riaccendere solo dopo aver ridotto la memoria del giro).
- **Acceso**: scheduler, ingest Drive (fatture, estratti conto, cedolini,
  bonifici), ponte pagamenti HR, dedup fatture ogni 30 min, canale
  dichiarazioni fiscali finché la coda non è esaurita.
- Fatture attive 982, collisioni aperte 0. Libro giornale: 820 fatture ferme
  per «IVA detraibile non classificata», 21 corrispettivi con ripartizione
  contanti/POS non quadrata (31/03–30/07/2026).
- Le 13 collezioni a zero dopo il 14/09 (`settings`, `scadenzario`,
  `f24_models`, `prima_nota`…) **non sono dati persi**: erano già vuote nel
  backup del 13/09. Non c'è nulla da recuperare.
- `mittenti_email` era vuota il 14/09: senza mittenti la posta non scarica
  (i builtin rientrano da soli all'avvio).
- Registro `cedolini` e `documents_inbox` del gestionale sono in
  rielaborazione dall'ingest orario.

## Aperto (togliere la voce quando si chiude)

- Compute Supabase **Micro** insufficiente (crash Postgres del 17/09
  12:33–12:38 UTC): valutare Small. `anon` ha `statement_timeout` 20 s: da
  rivedere se cambia il compute.
- Endpoint sincroni oltre i 5 minuti, da portare a prefetch + background:
  `POST /api/paypal-api/riconcilia`, `GET /api/paypal-api/account-ids-non-mappati`,
  `POST /api/admin/riallinea-pagamenti-fatture`,
  `POST /api/prima-nota-salari/deposita-cedolini-in-hr`.
- Note di credito TD04 legacy (20): il motore le registrerebbe come costi. Da
  trattare prima di classificarle.
- Riconciliazione: 158 fatture `riconciliata` con movimento non riconciliato,
  180 righe hub senza `fattura_id` (da rigenerare col motore, non a mano);
  banca 2026 con 1.765 movimenti senza categoria.
- Drive `03/ESTRATTI CONTO/DA ELABORARE`: 291 documenti pre-2026 lasciati
  fermi per scelta.
- HR: 38 bonifici con `cedolino_id` orfano, 119 in «bonifici da associare»,
  10 tabelle attese dall'app assenti (turni_config, onomastici, richieste…),
  Iazzetta Francesco senza IBAN; Appuhamy, Aurigemma, Vitiello, Dell'Aquila da
  creare come storici cessati.
- UNILAV di cessazione di Moscato Emanuele e Pocci Salvatore: non trovati in
  posta, da verificare col consulente.
- Drill-down «Verifica campi e F24» delle dichiarazioni ancora sul vecchio
  indice Drive (rotto).
- A mano, dal titolare: ruotare la password Postgres; eliminare il progetto
  Supabase di recupero (costa circa 10 $/mese); DNS di `ceraldiapp.it` e
  servizi Render sospesi.

## Diario

| File | Cosa racconta |
| --- | --- |
| `memoria/diario/2026-09-03.md` | Supabase archivio unico; porting pari pari di HR, Menu, Lotti; ponte Lotti→Menu; doppioni rimossi; deposito cedolini in HR; assetto Drive-only superato. |
| `memoria/diario/2026-09-14.md` | Cancellazione di massa e guardia; protocollo-indice Drive; fascicolo unico per dipendente; audit E2E con tabella dei backup; ponte pagamenti HR; dimissioni e chiusure; bonifica colori; regole R1-R6 del personale. |
| `memoria/diario/2026-09-15.md` | Accessibilità WCAG; guardia sulle cessazioni da cedolino; censimento Supabase e integrazione legacy (poi ristretta); restore su progetto separato; Cassetto Fiscale e dichiarazioni. |
| `memoria/diario/2026-09-16-17.md` | Collaudo E2E sul vivo; stabilità di produzione; pregresso nel giornale; doppioni fatture e impronta `c2:`; cache incrementale ERP e HR; timeout `anon`. |

## Canali operativi e conoscenza

- Telegram è l'unico canale attivo per alert e notifiche operative.
- Non registrare router, webhook o fallback WhatsApp legacy.
- Obsidian è una proiezione consultiva della documentazione: non è un database,
  non riceve scritture contabili e non sostituisce l'archivio Supabase.

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
- Libro giornale in partita doppia (`movimenti_contabili`): motore unico
  `app/services/registrazione_contabile.py`, alimentato **automaticamente**
  all'import di fatture (`fatture_upload`) e corrispettivi RT
  (`corrispettivi_helpers`, `CorrispettiviService`) tramite
  `registra_documento_import` (idempotente per documento con
  `idempotency_key = reg:<tipo>:<id>`, mai bloccante, esito negativo annotato
  in `registrazione_contabile_esito`). Il pregresso si recupera con
  `POST /api/piano-conti/registra-pregresso?dry_run=` (admin). Non aggiungere
  altri punti di scrittura.
- Navigazione tra contropartite: un solo componente
  `frontend/src/components/LinkContropartita.jsx` (`ROTTE_CONTROPARTITA`); i
  deep-link letti dalle pagine sono `/fatture?invoice_id=`,
  `/riconciliazione/banca?movimento=`, `/prima-nota#sezione=banca&selected=`,
  `/contabilita/verifica?conto=`, `/contabilita/giornale?conto=|scrittura=`.
- Ricavi: solo corrispettivi RT. Le fatture ricevute sono costi; gli accrediti
  POS e i payout non sono nuovi ricavi.
- POS: corrispettivo XML, chiusura terminale e accredito bancario sono tre
  fatti distinti. Numia e SumUp restano circuiti separati.
- SumUp corrente è acquisito dall'API; Numia corrente è la chiusura manuale
  serale; Numia storico è ricostruito dagli export operativi del gestore su
  Drive, deduplicati e accorpati per giorno. Tutte e tre le fonti creano
  l'attesa bancaria; l'estratto conto può soltanto riconciliarla.
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

- **05/09/2026, scelta del titolare:** il PIN amministratore unico per ERP,
  Menu, Lotti e HR è quello già usato da ERP/Menu (`PIN_HASH_ADMIN` in Render).
  `app/services/admin_pin.py` è l'unica verifica; i vecchi PIN amministratore
  delle sotto-app non sono alternative. Nessuna copia o modifica degli hash
  salvati. Il modale comune è `frontend_shared/PinModal.js`, parametrizzato
  per colore. I PIN personali dei dipendenti restano distinti; non dichiarare
  completata la loro unificazione finché le identità HR/Lotti non sono verificate.

- Segreti solo nelle variabili d'ambiente/secret store di Render.
- Non stampare, committare o trasferire credenziali nei documenti.
- Non spostare né cancellare email e documenti originali.
- Eliminazioni reali, pagamenti e associazioni definitive ambigue richiedono
  conferma esplicita al momento dell'azione.

## Dominio per app: le regole che non stanno nel codice

Assorbite il 17/09/2026 dai `CLAUDE.md` dei repository originali, che ora
rimandano qui.

### HR — contratto, accessi, turni

- **CCNL applicato: Pubblici Esercizi, Ristorazione Collettiva e Commerciale e
  Turismo** (Confcommercio-FIPE), codice CNEL **H05Y**, rinnovo 5/6/2024.
  **Non è il Terziario.** 40 ore settimanali, 14 mensilità (tredicesima a
  dicembre, quattordicesima a luglio), 26 giorni di ferie, enti EBNT/EBT,
  Fondo EST per la sanità, Fon.Te. per la previdenza complementare.
- **Login dipendente = tocca il tuo nome + PIN** (decisione esplicita del
  titolare): su un dispositivo condiviso in negozio digitare il cognome ad
  ogni apertura era scomodissimo, e i nomi non sono un segreto. L'accesso
  amministratore è una voce a parte, non la scheda di un dipendente.
- Sessione lunga e persistente (7 giorni) per cucina e pasticceria: il portale
  riapre senza richiedere il PIN finché il token è valido. "Esci" chiude
  subito.
- **Turni data-driven**, un solo punto di configurazione ("Configura turni"):
  per ogni dipendente modalità sala o barista, giorno di riposo fisso, giorni
  di Lunga, onomastico, flag "può coprire il bar". Nessun nome cablato nel
  codice. La preferenza di riposo scelta dal dipendente vince sul riposo fisso
  per quella settimana.
- **Timbrature solo in sede**: geofencing sulla sede in `impostazioni`
  (Ceraldi Caffè, Piazza Carità 14, Napoli, circa 40.842949 / 14.2489, raggio
  200 metri).
- Attività: bar e pasticceria, Ceraldi Group S.r.l., titolare Vincenzo Ceraldi.

### Lotti — HACCP, magazzino, prezzi

- **Un solo punto d'ingresso per le fatture** e deduplica sempre attiva
  (fornitore + numero + data).
- **Prezzi solo da acquisti reali in fattura XML.** Gli ordini hanno totali
  veri: prezzo di riga, aliquota IVA presa dall'XML, imponibile, IVA e totale
  che si ricalcolano a ogni variazione, con le stesse colonne nel PDF.
- **FIFO consuma sempre il lotto con la data fattura più vecchia.**
- **Le bevande e gli alcolici del reparto bar (acqua, birre, vino, prosecco,
  liquori, amari, sciroppi, succhi, bibite) si acquistano e si confrontano a
  cartone o a unità, MAI a chilo o a litro**: un rum o una birra si pagano a
  bottiglia, non al chilo.
- Conversioni reali: uovo 60 g, tuorlo 19 g, albume 33 g; pezzi e chili si
  convertono con il peso del pezzo.
- Ogni riga d'ordine dice **chi l'ha inserita** (dipendente, lavagna, riordino
  automatico, produzione, colazione).
- Le righe-nota (omaggi, riferimenti) non diventano prodotti di magazzino.
  Soglia minima e quantità di riordino predefinite a 1.
- Accessi: PIN valido 2 ore; i dipendenti entrano ovunque tranne le pagine di
  amministrazione (impostazioni, PIN, personale, controllo dati, backoffice,
  configurazione, backup, stampanti). Sui tablet condivisi il magazzino chiude
  la sessione dopo 10 minuti.

### Menu — allergeni

- Gli allergeni sono un obbligo di legge, non una cortesia: **Regolamento UE
  1169/2011** e **D.Lgs. 231/2017** impongono di dichiarare i 14 allergeni
  principali per ogni prodotto. Il dettaglio prodotto per prodotto è in
  `memoria/menu/ALLERGENI_MENU.md`.
- Un prodotto nuovo creato in Lotti arriva nel Menu con le stesse immagini e
  il flag "visibile nel menu pubblico".

## Indice dei documenti di riferimento

Questo file è la memoria. Gli altri `.md` del repository sono **materiale di
consultazione o output generato**, non regole: si leggono quando servono, non
a ogni sessione.

| Documento | Cosa contiene |
| --- | --- |
| `PROMPT_MASTER.md` | Specifica normativa completa, rigenerata da `scripts/genera_prompt_master.py`. Non si modifica a mano. |
| `memoria/MAPPA_ENDPOINT_COMPLETA.md`, `memoria/endpoints/*.md` | Mappa generata di tutti gli endpoint per area. |
| `memoria/AUDIT_*.md` | Audit storici datati: fotografie di un momento, non regole correnti. |
| `docs/REGOLA_FISSA_ATTESE.md` | Regola delle attese e delle prove per i flussi che creano obblighi. |
| `memoria/lotti/`, `memoria/hr/`, `memoria/menu/` | Documenti assorbiti dai repository originali (guide, PRD, changelog storici). |

Quando uno di questi contraddice questo file, **vince questo file**: gli audit
e i changelog raccontano com'erano le cose in una certa data.

## Verifica e pubblicazione

Per ogni modifica pertinente:

1. test mirati;
2. `python -m pytest -q` quando il cambiamento backend lo richiede;
3. `yarn test` e `yarn build` in `frontend/` quando coinvolge il frontend;
4. `git diff --check`;
5. commit dei soli file pertinenti;
6. unione su `main` (è la consegna: Render pubblica solo da lì);
7. CI verde e verifica `/api/health` sul commit pubblicato;
8. controllo live del flusso interessato senza mutare dati non autorizzati.

Un alert deve sempre mostrare l'elenco dei record coinvolti. Un comando di
manutenzione che l'utente deve ripetere per correggere duplicati prevedibili è
un difetto: la prevenzione per ID/hash deve stare nel flusso di importazione.
