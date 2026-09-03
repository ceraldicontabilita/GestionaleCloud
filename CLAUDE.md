# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

Aggiornato il 20/08/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

Prima di ogni intervento leggere `PROMPT_MASTER.md`: è la specifica normativa
unica. Questo file è soltanto il punto di ingresso operativo per Claude.
Leggere e applicare anche `docs/REGOLA_FISSA_ATTESE.md` per qualsiasi flusso
che crea obblighi, attese, prove o riconciliazioni.

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

Una prova successiva non crea mai l'obbligo che dovrebbe dimostrare. Il fatto
autorevole crea subito l'attesa; la prova la soddisfa o la lascia
`DA_VERIFICARE`.

I JSON in `memoria/pagine/` e `memoria/popup/` sono mappe tecniche generate:
si aggiornano con `scripts/refresh_json_docs.py`, non a mano.

## Archivio dati: stato reale e destinazione

### Decisione 03/09/2026 (titolare): Supabase è l'archivio unico

- Il titolare ha deciso di fondere le app del gruppo (AppDipendenti, Menu,
  Lotti) dentro GestionaleCloud e di usare **Supabase** (progetto
  `GestionaleCloud`, tabella `gestionale.documents` + `gestionale.blobs`)
  come unico archivio: `render.yaml` imposta `DATA_BACKEND=supabase`.
- Il runtime Sheets resta nel codice solo come fallback di sviluppo; la
  sezione "Destinazione Drive-only" qui sotto descrive l'assetto precedente
  ed è superata per la persistenza dei dati (Drive resta la fonte degli
  originali documentali, non il database).
- I PDF del modulo HR (cedolini, bonifici, documenti: ~500 MB in base64 nel
  vecchio database, di cui ~800 copie duplicate) NON vengono idratati in
  memoria: vivono in `gestionale.blobs` con chiave = SHA-256 del contenuto e
  conteggio dei riferimenti (un PDF identico citato da più documenti occupa
  spazio una volta sola; sparisce solo all'ultimo riferimento). L'adattatore
  `app/hr/db_adapter.py` li carica solo su richiesta.

### Stato precedente

- Il default del codice è `DATA_BACKEND=sheets`.
- legacy DB è stato rimosso come backend supportato e non va usato in produzione.
- Qualsiasi riferimento, variabile o script relativo a legacy DB è deprecato. Strumenti o script storici devono essere isolati, marcati come "legacy / solo per migrazione" e usati unicamente in procedure controllate e verificabili.
- La migrazione dei dati storici richiede confronto di conteggi e hash, ricostruzione completa e prove di scrittura; fino a verifica completa i dati storici non devono essere cancellati senza autorizzazione e checklist di cutover approvata.

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

## HR (AppDipendenti) portata pari pari — `app/hr/` + `frontend_hr/` a `/hr`

- **[03/09/2026]** I moduli riscritti `app/hr` + `frontend/src/hr` (rotte
  `/api/hr/...`, `/hr`, `/portale`, PIN unificato) sono stati **eliminati**:
  al loro posto c'è l'app AppDipendenti originale, così com'era. `app/hr/` =
  copia di `AppDipendenti/backend/app` con i soli import riscritti nel
  namespace `app.hr.*` (`app/hr/embed.py`: `hr_app`, `avvia_hr`/`arresta_hr`
  richiamati dal lifespan di `app/main.py` solo con scheduler attivo — ha un
  suo APScheduler — e `monta_frontend`). Montata in `app/main.py` a `/hr`
  PRIMA del catch-all della SPA dell'ERP: API a `/hr/api/...`
  (`/hr/api/health`, `/hr/api/auth/pin-login`, `/hr/api/dipendenti-cloud/...`).
- **Login proprio**, non quello del gestionale: tocca-il-nome + PIN personale
  per i dipendenti, "Accesso amministratore" con il PIN dell'env `HR_PIN_CODE`;
  JWT firmato con `HR_JWT_SECRET` (sessione dipendente 7 giorni, admin 2 ore).
  Il middleware del gestionale non c'entra: `/hr/...` è fuori da `/api/`.
  I ruoli `dipendente`/`responsabile_turni` non esistono più in
  `app/utils/ruoli.py`.
- Dati: Postgres/Supabase dell'app originale via `HR_SUPABASE_DB_URL`
  (fallback `APPDIPENDENTI_DB_URL`, poi `SUPABASE_DB_URL`), tabelle `app_<nome>`
  con colonna `doc jsonb` (adattatore Mongo→Postgres `app/hr/db_supabase.py`).
  Nessun dato HR nel registro Drive/Sheets/`gestionale.documents`.
- `frontend_hr/` = copia di `AppDipendenti/frontend` (Vite, `base: '/hr/'`,
  build in `frontend_hr/dist` compilata su Render, non committata): gestione
  desktop a `/hr/`, portale mobile a `/hr/portale`. Voce "HR" (solo admin)
  nel menu Altro = link a pagina intera.

## Menu portato pari pari — `app/menu/` + `frontend_menu/` a `/menu`

- **[03/09/2026]** Il modulo riscritto `app/menu` + `frontend/src/menu`
  (rotte `/api/menu/...`, Tailwind, `/menu-banco`) è stato **eliminato**: al
  suo posto c'è l'app Menu originale. `app/menu/` = copia di `Menu/backend`
  con import nel namespace `app.menu.*` (`app/menu/embed.py`: `menu_app`,
  `avvia_menu`/`arresta_menu` no-op). `app/menu/server.py` monta da solo il
  build `frontend_menu/build` se esiste; `app/main.py` monta `menu_app` a
  `/menu` PRIMA del catch-all della SPA: API a `/menu/api/...`
  (`/menu/api/health`, `/menu/api/admin/login`).
- **Login admin proprio** username/password (`MENU_ADMIN_USERNAME`,
  `MENU_ADMIN_PASSWORD`, JWT `MENU_JWT_SECRET`), pagina `/menu/admin/login`.
- Dati nel progetto Supabase `Lotti-HACCP`, tabelle `menu_*`
  (`menu_categories`, `menu_subcategories`, `menu_products`, `menu_allergens`,
  `menu_orders`, `menu_sale`, ...) via client PostgREST `MENU_SUPABASE_URL` /
  `MENU_SUPABASE_KEY`; immagini nel bucket Storage `menu-images`.
- **Il menu vero si gestisce su Qromo** (`ceraldicaffe.qromo.it`): bottone
  "Sincronizza da Qromo" nel tab Prodotti dell'area admin →
  `POST /menu/api/admin/sync-qromo` (`app/menu/qromo_sync.py`, aggiunta
  GestionaleCloud: legge le costanti JavaScript della home Qromo, esclude le
  sottocategorie di cassa `BANCO - *`, riduce gli allergeni ai 14 UE,
  sostituisce per intero categorie/sottocategorie/prodotti; `GET
  .../sync-qromo/preview` = prova a secco). Test: `tests/test_menu_qromo_sync.py`.
- URL del menu per i clienti (QR al tavolo):
  `https://gestionalecloud.onrender.com/menu/`. `frontend_menu/` = copia di
  `Menu/frontend` (CRA, `PUBLIC_URL=/menu` in `.env.production`, tracciato
  apposta; build compilata su Render). Voce "Menu" nel menu Altro = link a
  pagina intera su `/menu/admin`.
- **Prodotti da Lotti [03/09/2026, richiesta del titolare]**: ogni ricetta di
  Lotti viene replicata nel Menu con la stessa foto; il titolare sceglie se
  compare nel menu pubblico. Ponte `app/lotti/servizi/menu_bridge.py`
  (`pubblica_prodotto_nel_menu` / `rimuovi_prodotto_dal_menu`, client
  sincrono del Menu eseguito con `asyncio.to_thread`), agganciato in
  `app/lotti/routers/ricette.py` a `POST /lotti/api/ricette`, `PUT`/`PATCH`
  `/ricette/{id}`, `/prezzo-vendita`, `/reparto`, `POST /ricette/{id}/upload-foto`,
  `DELETE /ricette/{id}`; l'esito va nella risposta come `menu_sync`
  (`pubblicato` | `aggiornato` | `rimosso` | `non_configurato` senza
  `MENU_SUPABASE_URL` | `errore`) e non fa mai fallire l'endpoint Lotti.
  Campi: ricetta `menu_pubblico` (bool, default False, checkbox "Mostra nel
  menu pubblico" in `FormRicetta.jsx`; `PATCH` lo accetta) → `menu_products.
  visible`; `menu_products.origine = "lotti"`, `lotti_ref = "ricetta:<id>"`
  (chiave idempotente: update se esiste, altrimenti insert con id ≥ 1.000.000
  per non collidere con gli id Qromo). Categoria "Produzione Ceraldi" +
  sottocategoria per reparto (Pasticceria/Rosticceria/Bar/Altro), create al
  volo con `origine = "lotti"`. Prezzo `"3.50€"` da `prezzo_vendita`,
  allergeni Lotti → 14 id UE (`MAPPA_ALLERGENI_MENU`), descrizione = `descrizione`
  o `note`. Foto: byte da `foto_files` copiati nel bucket `menu-images` al
  percorso `lotti/<foto_id>.<jpg|png|webp>` (upsert), URL pubblico in `image`;
  non si ricarica se la riga punta già allo stesso `foto_id`. Il menu
  pubblico (`GET /menu/api/menu/`, `/subcategories/{id}`, `/products/{id}`,
  `/search`) esclude `visible=false`; `/admin/products/all` e il CRUD admin
  espongono/accettano `visible`. La sync Qromo cancella solo le righe con
  `origine IS NULL`: le righe di Lotti sopravvivono. Test:
  `app/lotti/tests/test_menu_bridge.py`, `tests/test_menu_public_visible.py`.

## App portate pari pari — `app/lotti/` + `frontend_lotti/`, `app/menu/` + `frontend_menu/`, `app/hr/` + `frontend_hr/`

- **[03/09/2026, decisione del titolare]** Le app del gruppo NON vanno
  ricostruite dentro il gestionale: si prende il repository originale e lo si
  porta dentro così com'è ("voglio l'app così come era"). Ogni app è un
  documento a sé: backend originale montato come sub-app FastAPI a
  `/<app>` (rotte `/<app>/api/...`, **proprio login**), frontend originale
  compilato con la propria toolchain e servito a `/<app>/` dalla stessa
  sub-app. Nessuna contaminazione di stile con il layout dell'ERP.
- **Lotti (HACCP)**: `app/lotti/` = copia di `Lotti/backend` con i soli import
  riscritti nel namespace `app.lotti.*` (`app/lotti/embed.py`: `lotti_app`,
  `avvia_lotti`/`arresta_lotti` richiamati dal lifespan di `app/main.py`
  perché Starlette non propaga lo startup alle sub-app, `monta_frontend`).
  Montata in `app/main.py` PRIMA del catch-all della SPA dell'ERP. Env
  namespaced per non collidere con quelle del gestionale:
  `LOTTI_SUPABASE_URL`, `LOTTI_SUPABASE_ANON_KEY`, `LOTTI_DB_SECRET`
  (progetto Supabase `Lotti-HACCP`, tabella `lotti_documents` + RPC
  `lotti_*`), `LOTTI_AUTH_SECRET` (fallback `AUTH_SECRET`), `LOTTI_DB_NAME`.
  Senza `LOTTI_SUPABASE_URL` l'archivio è in memoria (mongomock, non
  persistente: solo test/sviluppo). Il PIN admin di Lotti resta quello di
  Lotti. `frontend_lotti/` = copia di `Lotti/frontend` (CRA), build con
  `PUBLIC_URL=/lotti`, `REACT_APP_BACKEND_URL=/lotti` (`.env.production`,
  tracciato apposta); le foto SAIMA sono referenziate dai dati come
  `/saima/...` e vengono servite dall'host da `frontend_lotti/build/saima`.
  Voce "HACCP Lotti" nel menu Altro (link a pagina intera). I test originali
  vivono in `app/lotti/tests` (`AUTH_SECRET=test python -m pytest app/lotti/tests`).
  La guardia `tests/test_drive_only_architecture.py` esclude `app/lotti`
  (usa l'API Mongo in memoria per progetto, non è l'archivio dell'ERP).
- **Menu e HR: fatto (03/09/2026)**, vedi le due sezioni qui sopra. I moduli
  riscritti `app/menu`, `frontend/src/menu`, `app/hr`, `frontend/src/hr`
  non esistono più (con i loro test, le pagine 67-76 di `page_catalog.json`
  e le voci `/hr`, `/portale`, `/menu*` del router React). Le guardie
  `tests/test_drive_only_architecture.py`, `tests/test_csrf_cookie_guard.py` e
  `tests/test_no_hardcoded_deprecated_collections.py` escludono `app/lotti`,
  `app/menu`, `app/hr` (codice di app esterne, non dell'ERP); i test delle
  app restano quelli originali (`app/lotti/tests`, `app/hr/tests`).
  `render.yaml` compila anche `frontend_menu` e `frontend_hr` e dichiara le
  env `LOTTI_*`, `MENU_*`, `HR_*` (`sync: false`).
- Fase successiva: consolidare i dati delle app nel progetto Supabase
  `GestionaleCloud`.

## Doppioni rimossi il 03/09/2026: HACCP nativo e pagina «Cedolini paga»

- **Ordine del titolare** («elimina bottone Tracciabilità e codice associato,
  `/salari` e `/tracciabilita`»), regola «un solo sistema per funzione».
- **HACCP nativo eliminato**: voce «Tracciabilità» della TopNav, route
  `/tracciabilita` + `frontend/src/pages/TracciabilitaHACCP.jsx`, router
  `app/routers/haccp.py` (`/api/haccp/*`), servizi
  `app/services/haccp_traceability.py` e `haccp_operations.py`, costanti
  `COLL_HACCP_*` in `app/db_collections.py`, indici `haccp_*` in
  `app/database.py`, fogli `haccp_*` di `PROMPT_MASTER.md`, i test
  `tests/test_haccp_*.py` e la pagina 66 del catalogo. Al suo posto c'è l'app
  Lotti a `/lotti`. **Resta** `app/routers/lotti_integration.py`
  (`/api/integrations/lotti/*`): è il feed fatture letto da
  `app/lotti/routers/gestionale_fatture.py`. `docs/ADR-001-HACCP-LOTTI-DRIVE-
  SHEETS.md` è conservato come documento storico.
- **Pagina «Cedolini paga» eliminata**: voce nel menu Altro, route `/salari`,
  `frontend/src/pages/CedoliniSalari.jsx` (+ test), pagina 10 del catalogo;
  in `MappaGestionale.jsx` l'area «Cedolini» apre `/hr/`. Con lei sono spariti
  i soli endpoint che esistevano per quella pagina: `GET /api/prima-nota-salari/
  salari-ricostruiti`, `GET .../export-appdipendenti/preview` e `.../download`
  (+ `app/services/appdipendenti_export.py`). **Resta tutto il resto** del
  router `/api/prima-nota-salari` (Prima Nota salari, import paghe/bonifici,
  PDF cedolino/bonifico per riga, riconcilia — usati da `primaNotaStore.js`,
  dal MCP e dai test), l'ingestione cedolini (`drive_cedolini`,
  `email_download`, `sync_prima_nota_salari_da_cedolini` in `app/main.py`),
  F24, TFR e `app/routers/employees/dipendenti.py`.
- Il catalogo canonico conta ora **64** schermate (id contigui).

## Cedolini: un solo sistema (HR)

- **[03/09/2026, decisione del titolare]** «Il gestionale scarica i dati dalla
  posta … portare i cedolini in HR; niente ponte; a cosa serve una sezione
  cedolini nel gestionale e un'altra in HR?». L'archivio cedolini che gli
  utenti vedono è **solo l'app HR** (`/hr`, tabella `public.app_cedolini`
  del Postgres HR, DSN `HR_SUPABASE_DB_URL` → fallback `APPDIPENDENTI_DB_URL`,
  `SUPABASE_DB_URL`, già dichiarate in `render.yaml`).
- Il gestionale continua a **scaricare** le buste (Drive:
  `app/services/drive_cedolini_ingest.py`; email: `app/routers/email_download.py`
  → `processa_nuovi_documenti` → `cedolini_manager` → `salari_unificati_v2`)
  e a ricavarne la **Prima Nota salari**: per questo il registro interno
  `cedolini` resta scritto, ma non ha più una pagina propria.
- **Deposito in HR**: `app/services/hr_cedolini_deposito.py::
  deposita_cedolino_in_hr(cedolino)` è richiamato, protetto da try/except,
  subito dopo OGNI scrittura di un cedolino nel gestionale
  (`salari_unificati_v2.processa_cedolino_v2`, `cedolini_manager.
  processa_cedolino_completo`, `post_download_pipeline.processa_cedolini_da_email`,
  `upload_ai_processor.process_upload_cedolino`, `ai_integration_service`,
  `document_data_saver.save_busta_paga_to_gestionale`, `email_full_download.
  smart_auto_associate`, `POST /api/dipendenti/buste-paga`, `POST
  /api/prima-nota-salari/salari/{id}/cedolino-pdf`). Scrive con asyncpg
  direttamente in `app_cedolini` (`id text` + `doc jsonb`, stessa forma
  dell'adattatore `app/hr/db_supabase.py`) senza toccare `app/hr/**`.
- Forma del documento = quella dei 1291 cedolini già in HR: `mese`/`anno`
  interi, `competenza` `"YYYY-MM"`, `tipo_cedolino` `ordinario` (il "mensile"
  del gestionale) / `tredicesima` / `quattordicesima`, `netto`, `lordo`,
  `competenze`, `trattenute`, `nome_dipendente` = `dipendente_nome`,
  `filename`/`pdf_filename`, `pdf_data` base64, `fonte` = `gestionale_cloud`,
  `parser_template` solo se è un modello noto all'HR (`zucchetti_new`,
  `zucchetti_classic`, `csc_napoli`, `teamsystem`), `giorni_lavorati`,
  `livello`; `dipendente_id`/`nome` risolti da `app_dipendenti` per codice
  fiscale (mai gli id del gestionale). Provenienza conservata in
  `gestionale_cedolino_id`, `gestionale_source`, `cedolino_dedup_key`.
- **Dedup, mai sovrascrittura**: un cedolino HR esistente con la stessa
  `cedolino_dedup_key`, oppure stesso (CF maiuscolo, anno, mese, tipo), non
  viene toccato (`esito: gia_presente`); 13ª/14ª dello stesso mese restano
  buste distinte. Senza DSN il deposito è un no-op segnalato una volta nel
  log (`hr_non_configurato`); un errore di rete non ferma mai l'ingestione.
- **Backfill**: `POST /api/prima-nota-salari/deposita-cedolini-in-hr` (admin,
  `?dry_run=true` per contare senza scrivere) deposita tutto il registro
  `cedolini` e ritorna `inseriti`/`gia_presenti`/`errori`/`saltati`; da shell
  `python -m app.services.hr_cedolini_deposito --dry-run`. Test:
  `tests/test_hr_cedolini_deposito.py`.

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
