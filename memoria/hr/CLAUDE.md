# AppDipendenti — Ceraldi Group S.r.l.

App HR di **Ceraldi Group** (Napoli, titolare Enzo/Vincenzo Ceraldi). Attività:
**bar / pasticceria** (Ceraldi Caffè, Piazza Carità 14, Napoli).

> Questo file è la memoria di progetto: leggilo a inizio sessione per non perdere
> il focus. Aggiornalo quando aggiungi funzioni importanti.

## Stack & deploy
- Backend **FastAPI** in `backend/app`. Il cluster MongoDB **non esiste più**: il
  database vero è **Postgres/Supabase** (env `SUPABASE_DB_URL`, progetto condiviso
  anche con **GestionaleCloud/CeraldiFatture** — vedi sotto), con un adattatore
  Mongo→Postgres (`backend/app/db_supabase.py`) che riespone la stessa API di motor
  usata nei 269 punti che chiamano `Database.get_db()` — ogni collection di
  AppDipendenti è una tabella `app_<nome>` con colonna `doc jsonb`. Copre find/
  find_one/insert_one/update_one/**update_many**/delete_one/**delete_many**/
  **distinct**/count_documents (con upsert), `.sort()`/`.limit()`/`.to_list()`,
  operatori `$ne $exists $in $nin $gt $gte $lt $lte $or $and`, `$set $setOnInsert
  $unset $inc $push` (forma semplice `{campo: valore}`, no `$each`/`$slice`), e
  **`aggregate`** per il sottoinsieme realmente usato nel repo: stage `$match
  $group $addFields $sort $limit $skip`, accumulatori `$sum $avg $first $last
  $push`, espressioni `$ifNull $cond $toUpper $toLower $toDate $month`. Un
  operatore fuori da questo elenco solleva `NotImplementedError` (mai un
  risultato silenziosamente sbagliato) — se serve un operatore nuovo, aggiungilo
  nell'adattatore, non aggirarlo nel router. **NON copre**: indici veri,
  `find_one_and_*`, bulk write, altri stage/operatori aggregate. (`MONGO_URL`/
  Motor restano come fallback in `database.py` se `SUPABASE_DB_URL` non è
  impostata, ma in produzione oggi è sempre il ramo Supabase.)
  **[AUDIT 29/08/2026]** Prima di questo fix, `aggregate`/`update_many`/
  `delete_many`/`$push`/`distinct` non erano implementati affatto: oltre 40 punti
  del backend fallivano al 100% delle chiamate, non in casi limite — tra questi
  l'intera catena di **cessazione dipendente** (`services/handlers/
  dipendente_handlers.py`, ognuna delle 4 azioni avvolta nel proprio try/except
  che nascondeva l'errore), la feature **"limiti giustificativi"** (ferie/ROL/
  permessi), il **riepilogo TFR aziendale**, le **statistiche dashboard** per
  mansione, "**applica tutte le trattenute**" su una busta, l'aggiunta di un
  **acconto busta paga**. Verifica in produzione dopo il deploy di questo fix
  prima di darle per scontate di nuovo funzionanti.
- Frontend **React + Vite** in `frontend/src` (`App.jsx` = gestione desktop,
  `PortaleDipendente.jsx` = portale mobile dipendenti).
- Deploy su **Render** (`appdipendenti.onrender.com`), auto-deploy dal branch **`main`**.
- ⚠️ **Render NON builda il frontend**: serve `frontend/dist/` **committata in git**.
  Quindi ad ogni modifica frontend: `cd frontend && npm run build`, poi committa
  `dist/` + `src/`. Senza ricommittare `dist`, in produzione non cambia nulla.
- **🔒 REGOLA FISSA (decisa dal titolare): TUTTO va portato su `main`.** Si sviluppa e si
  pusha **DIRETTAMENTE su `main`**, niente branch. Se una sessione/agent lavora su un branch
  (es. Claude Code web), al termine **fai sempre il merge su `main` e pusha `main`** — il
  lavoro non è "consegnato" finché non è su `main` (Render fa deploy solo da `main`).
  Vale per ogni sessione e ogni agente, sempre.
- **🔒 REGOLA FISSA: a fine di OGNI sessione, manda sempre il link Render**
  → **https://appdipendenti.onrender.com** (così il titolare verifica subito in produzione).

## Regole canoniche del titolare (sempre valide)
- Niente doppioni / codice morto / sistemi paralleli: **un solo sistema per funzione**.
- Tutte le credenziali (token, PIN, password, chiavi) **SOLO nelle env di Render**,
  mai in codice/chat. (`render.yaml` le elenca con `sync: false`.)
- Design **sage** (`#5b7a6b`) su **cream** (`#faf7f0`); card `#fffefb`, sidebar
  `#3f5a4e`, ink `#2a3329`, bordi sand `#e6e0d4`. **Vietati blu/indigo/viola.**
- Rispondere e ragionare in **italiano**, stile risultati-prima.
- Importi/dati reali: non inventare numeri tabellari (CCNL, prezzi) — vanno validati.

## CCNL
**Pubblici Esercizi, Ristorazione Collettiva e Commerciale e Turismo**
(Confcommercio-FIPE), codice CNEL **H05Y**, rinnovo 5/6/2024. NON è il Terziario.
40 ore/sett, 14 mensilità (13ª dic, 14ª lug), 26 gg ferie, enti EBNT/EBT,
Fondo EST (sanitario), Fon.Te. (previdenza compl.).

## Autenticazione
- Ingresso da `/portale` con **PIN** → JWT in `localStorage.pt_token` (+ `pt_role`,
  `pt_name`). Header `Authorization: Bearer`.
- **Login dipendente = tocca il tuo nome + PIN** (decisione esplicita del titolare,
  28/08/2026: reintrodotto l'elenco nomi in login, prima rimosso per non esporlo
  pre-autenticazione — su un dispositivo condiviso in negozio la digitazione ad
  ogni apertura era scomodissima, e i nomi non sono comunque un segreto).
  GET pubblico `/api/auth/dipendenti-attivi` (solo id+nome, dipendenti attivi
  con PIN impostato) → tocco sul nome → PIN pad → POST `/api/auth/pin-login` con
  `{dipendente_id, pin}` (niente più ambiguità da omonimi: si sceglie l'id, non
  il nome). Il vecchio flusso a testo `{nome, pin}` resta supportato lato backend
  per compatibilità ma il portale non lo usa più.
- Login admin: dalla schermata PIN → **"Accesso amministratore"** (PIN = env `PIN_CODE`),
  NON dalla scheda di un dipendente.
- Sessione admin **2 ore** (`ADMIN_TOKEN_EXPIRE_MINUTES`). Sessione dipendente/portale
  **7 giorni** (`ACCESS_TOKEN_EXPIRE_MINUTES` in `backend/app/config.py`), e **persistente**:
  il portale riapre direttamente senza richiedere di nuovo il PIN finché il token
  non scade (controllo `exp` lato client in `PortaleDipendente.jsx`, verifica vera
  sempre lato server) — anche questo su richiesta esplicita del titolare per
  cucina/pasticceria (dispositivo condiviso, PIN ad ogni apertura era scomodissimo).
  "Esci" nella testata chiude comunque la sessione subito.
- Backend strict: `require_admin` / `require_staff` in `utils/dependencies.py`
  (fail-closed: senza token valido → 401, nessun "admin di default"). Protetti:
  `/api/contracts`, `/api/cedolini`, `/api/tfr`, `/api/paghe`, `/api/bonifici`,
  `/api/salari-v2`, `/api/dimissioni` = admin; `/api/dipendenti-cloud`,
  `/api/dipendenti`, `/api/fascicolo`, `/api/giustificativi`, `/api/shifts`,
  `/api/attendance` = staff (admin o responsabile_turni). Portale: `get_identity`/
  `require_roles` per-endpoint. CORS senza wildcard; segreto JWT mai literal.
- Frontend: `App.jsx` allega il token e su 401/403 riporta al PIN; `main.jsx`
  `RequireRole` valida ruolo + scadenza token.

## Architettura automazioni (event-driven)
- `services/event_bus.py` (propagate_event + EventTypes), `services/alert_engine.py`
  (genera_alert/risolvi_alert, catalogo `ALERT_CATALOG`), handler in
  `services/handlers/`. `APScheduler` per i job periodici.
- Catene A→B attive: ferie approvata→indisponibilità turni + record Ferie&Permessi
  (→ visibile in Presenze); acconto/anticipo→partita; contestazione→alert;
  cedolino→partita+notifica+TFR progressivi; missione→rimborso+notifica;
  contratto finalizzato→aggiorna anagrafica; cessazione (pulsante)→handler completo;
  scadenzario (contratti/prova)→alert; timbratura→presenze reali.
- Alert visibili nel **Pannello di controllo** (pannello "Avvisi & Scadenze").
- **Turni data-driven** (pagina Turni, modale "⚙️ Configura turni" = punto unico):
  per dipendente `turni_config` (collezione) = modalità Sala (cameriere: rotazione
  automatica 2 Lunga/2 Mattina/2 Pomeriggio/1 Riposo, riposi nei feriali per coprire il
  weekend) | turno abituale | rotazione bar (mattina↔pom); + giorno di riposo fisso +
  giorni di Lunga (Ven/Sab/Dom); + onomastico (`onomastici`). "Genera settimana"
  (`generaProduzione` in App.jsx) assegna: turno abituale, Lunga nei giorni spuntati,
  Riposo nel giorno fisso e nell'onomastico, Ferie nei giorni di ferie APPROVATE.
  Niente più nomi cablati. Celle sempre modificabili a mano.
- **Turni — Vista semplice** (predefinita in pagina Turni, toggle "📋 Vista griglia"):
  una riga per dipendente, 7 caselle colorate; un click = turno successivo tra le
  "sponde" del dipendente (i soli turni che può fare dalla sua `turni_config`, poi
  Riposo, Ferie, vuoto). Intestazione con copertura giornaliera ☀️ mattina / 🌆
  pomeriggio (Lunga conta per entrambi, rosso = scoperto). Salvataggio ottimistico
  immediato. Pennello e riordino a trascinamento restano solo nella vista griglia.
  (Eliminato il vecchio doppione `impostazioni-turni` / checkbox "Bar chiuso la
  domenica pomeriggio": il sistema unico è `turni-chiusura-pomeridiana` nel modale.)
- **Turni nel portale + preferenze riposo**: il tab Turni del portale legge la STESSA
  settimana della gestione (GET `/api/turni/azienda/settimana`, sola lettura: i miei
  turni + tabella di tutti i colleghi; eliminata la vecchia "griglia pubblicata"
  `turni_griglia` con squadra cablata). Ogni dipendente imposta la **preferenza del
  giorno di riposo** per la prossima settimana (GET/POST `/api/turni/preferenza-riposo`,
  collezione `turni_preferenze_riposo`); il responsabile turni riceve una notifica e
  le vede in pagina Turni (pannello 💤 + marcatore sulle caselle, GET staff
  `/api/dipendenti-cloud/turni-preferenze?settimana=`). "Genera settimana" usa la
  preferenza come giorno di riposo (vince sul riposo fisso per quella settimana).
- **Sostituzioni bar**: flag `sostituto_bar` in `turni_config` (spunta "🆘 può coprire
  il bar" nel modale, pensata per Taiano e Russo ma senza nomi cablati). Chi ha il
  flag vede nel portale il riquadro "🆘 Copro il bar" (dal/al + fascia mattina o
  pomeriggio + "al posto di" = barista assente → POST `/api/turni/disponibilita-bar`,
  collezione `turni_disponibilita_bar`, notifica al responsabile; se indicato,
  "Genera settimana" svuota le celle dell'assente nei giorni coperti → la coppia
  diventa es. Vespa+Taiano). Modale a card RAGGRUPPATE per ruolo (sezioni ☕ Baristi /
  🍽 Camerieri / 🕐 Turno fisso, badge ruolo in card, pillole modalità dentro
  "cambia modalità"). In gestione: pannello 🆘 in
  pagina Turni (GET staff `/turni-disponibilita-bar?settimana=`) e "Genera settimana"
  mette il sostituto al bar nella fascia scelta; se era in squadra sala copre il buco
  con una Lunga al cameriere con meno Lunghe (conferma via window.confirm prima di
  annullare un riposo). Card del modale per ruolo: barista (rotazione) senza
  Lunga/flag; la rotazione bar è ancorata (`rotazione_ancora` = lunedì della
  settimana in cui si imposta "ora mattina/pomeriggio", inversione automatica ogni
  lunedì, per dipendente).
- **Onomastici** (`dipendenti_cloud`: ONOMASTICI_DEFAULT + collezione `onomastici`):
  gestiti nel modale "Configura turni"; nella pagina Turni un pannello mostra gli
  onomastici della settimana (solo giorni lavorativi, esclusi stranieri/disattivati e
  i non-turnisti). Date prefillate e modificabili.

## Integrazione GestionaleCloud & cartelle Google Drive
**[AUDIT 29/08/2026]** Risposta a "fatture/foto hanno un router proprio o fanno
ponte con GestionaleCloud?":
- **Fatture/fornitori**: router dedicato `backend/app/routers/contabilita.py`
  (prefix `/api/contabilita`), ma è un **bridge di sola lettura/import-snapshot**
  da un'altra app (`https://ceraldi-gestione.onrender.com`, il GestionaleCloud/
  CeraldiFatture del titolare) — collezioni `invoices`, `fornitori`,
  `documents_inbox`, `riconciliazioni_match`, popolate da
  `POST /contabilita/importa-snapshot` (seed `backend/app/data/
  contabilita_seed.json`) o da `POST /fatture/importa-xml`. **Nessuna pagina
  frontend** mostra fatture o fornitori (solo diagnostica) — l'unica UI
  collegata è "Bonifici effettuati" (`BonificiContabPage` in App.jsx), che legge
  `GET /contabilita/bonifici`.
- **Magazzino/prodotti**: solo un handler evento interno
  (`services/handlers/magazzino_handlers.py`, si attiva su `FATTURA_CREATED`),
  scrive `warehouse_inventory`/`dizionario_prodotti`/`acquisti_prodotti` — **nessun
  endpoint REST, nessuna UI**. **Foto/immagini prodotto: nessun riferimento nel
  codice**, non esiste alcuna funzionalità di questo tipo in AppDipendenti oggi.
- **Database fisico condiviso**: stesso progetto Supabase di GestionaleCloud —
  tabelle come `fatture` (non-prefissata `app_`... la voce Supabase vera si
  chiama solo `fatture`/`fornitori`/`incassi`/`movimenti_banca`/`prezzi_ceraldi`/
  `catalogo_ceraldi`/`chiusure_giornaliere`/`prima_nota_movimenti`/`versamenti`
  ecc.) sono di GestionaleCloud, mai referenziate da questo repo. Il fascicolo
  dipendente (`routers/employees/fascicolo_dipendente.py`) legge in più, con
  fallback silenzioso via try/except, `bonifici_transfers`/`verbali_autovelox`/
  `presenze_giornaliere`/`tfr_acconti` — tabelle non garantite esistere nello
  schema di AppDipendenti, lette "a bonus" dal DB condiviso.
- **Cartelle Google Drive** (service account `gestionale@ceraldi-gestionale.iam.
  gserviceaccount.com`, stesse env del GestionaleCloud — vedi Autenticazione
  sotto per i nomi): SOLO DUE, nessuna per fatture/foto/documenti generici:
  - **Cedolini**: env `DRIVE_CEDOLINI_FOLDER_ID`, default
    `1XVdbMzz145N5p8jn4XXSt8YkYtsPOT15` — bottone "📥 Importa cedolini da Drive"
    in Buste Paga → `POST /api/cedolini/import-drive`.
  - **Bonifici**: env `DRIVE_BONIFICI_FOLDER_ID`, default
    `1yl55742cu9i-AFLxu2s0QnMvXG6kVkJC` (è l'estratto conto aziendale generico,
    non solo stipendi — i movimenti non salariali vengono scartati, vedi sotto)
    — link "📁 Cartella Drive bonifici" e bottone "📥 Importa bonifici da Drive"
    in Cedolini & Bonifici (`DRIVE_BONIFICI_URL` in App.jsx) →
    `POST /api/paghe/importa-bonifici-drive`. **Attenzione**: il 29/08/2026
    questa cartella risultava nel Cestino di Drive (ancora funzionante via API
    finché non viene svuotato il cestino, ma a rischio di cancellazione
    automatica) — verificare che il titolare l'abbia ripristinata.
  - Se il titolare fornisce nuovi ID cartella, aggiornare **entrambi** i punti
    per ciascuna cartella: l'env var di default nel codice backend (o l'env
    Render se preferisce non toccare il codice) e la costante frontend
    corrispondente (`DRIVE_BONIFICI_URL` in App.jsx per i bonifici).

## Moduli chiave
- **Assunzione & Contratti** (`App.jsx` AssunzionePage + `routers/employees/employee_contracts.py`):
  template .docx su MongoDB (collezione `contract_templates`), segnaposto nominali
  `{{chiave}}` + puntini legacy compilati da `fill_contract_template`. Genera contratto
  + accessori (regolamento/privacy/informativa 152). Pulsante "Assumi dipendente"
  (crea anagrafica + genera) e generazione massiva (dati da buste paga).
  **Iter firma**: bozza → invia bozza → carica firmato dal dipendente → controfirma
  e invia definitivo → archiviazione nel fascicolo (`contratti_dipendenti`).
  Firma digitale OpenAPI.com (OAuth V2 + marca temporale + eSignature + PEC) in
  `services/openapi_signature.py` (env `OPENAPI_CLIENT_ID/SECRET`, `OPENAPI_ENV`).
  docx→PDF: servizio unico `services/docx_converter.py` → **ConvertAPI** in produzione
  (env `CONVERTAPI_TOKEN`; OpenAPI.com non offre docx→PDF), **LibreOffice** come
  fallback solo in locale. L'iter manuale via upload PDF non richiede conversione.
- **Timbrature** (`routers/timbrature.py` + portale tab "Timbra" + gestione "Timbrature"):
  entrata/uscita geolocalizzata, **solo in sede** (geofencing, sede in `impostazioni`/
  `sede_lavoro`: Ceraldi Caffè, Piazza Carità 14 ≈ 40.842949, 14.2489, raggio 200m).
  Alimenta `presenze_cloud`. Vista admin: atteso (turno) vs effettivo + riepilogo ore mensile.
- **Modelli documenti**: `modelli/` (script generatori .docx corretti CCNL Turismo:
  4 contratti + informativa 152). Da caricare in Assunzione → Modelli.

## File chiave
- `frontend/src/App.jsx` — gestione (Dashboard, Anagrafica, Presenze, Ferie, Turni,
  Timbrature, Buste, Documenti, Assunzione, Missioni).
- `frontend/src/PortaleDipendente.jsx` — portale mobile (Timbra, Turni, Buste,
  Documenti, Richieste, Avvisi, Gestione).
- `backend/app/main.py` — registrazione router + lifespan (scheduler).
- `backend/app/routers/dipendenti_cloud/__init__.py` — CRUD HR (prefix `/api/dipendenti-cloud`),
  cessa dipendente, alerts, dashboard stats.
- `render.yaml` — config deploy + env (`sync: false`).

## Collezioni MongoDB principali
`dipendenti` (anagrafica), `cedolini` (buste), `presenze_cloud` (presenze manuali/
timbrature), `presenze` (LUL), `ferie_cloud`, `turni_settimane` + assegnazioni,
`turni_indisponibilita`, `richieste`, `notifiche`, `timbrature`, `impostazioni`,
`employee_contracts`, `contratti_dipendenti` (fascicolo), `alerts`, `partite_aperte`,
`missioni_cloud`, `assegnazioni_turni_cloud`, `turni_config` (turno/riposo/Lunga per
dipendente), `onomastici`.
- `documenti_cloud`: archivio documenti dipendente. Upload massivo POST `/api/dipendenti-cloud/documenti/upload-massivo`: classifica il tipo (UNILAV/CERTIFICAZIONE_UNICA/CONTRATTO/BONIFICO/CODICE_FISCALE/BUSTA_PAGA/ALTRO) da regole sul testo, trova il dipendente dal codice fiscale/nome nel PDF, dedup per hash, salva file_data. Pagina Documenti = vista a cartelle per tipo + download (`/documenti/{id}/file`).
- Import: anagrafica da Excel (`POST /dipendenti/importa-anagrafica`); pagamenti bonifici
  da CSV banca (`POST /paghe/importa-pagamenti` → collezione `pagamenti_esiti`, ricalcola
  bonifico mese); Prima Nota Excel (`/paghe/importa-prima-nota`); bonifici stipendi da PDF
  su Google Drive (`POST /paghe/importa-bonifici-drive`, service account già usato per i
  cedolini — cartella linkata nel bottone "📁 Cartella Drive bonifici" in Cedolini &
  Bonifici, stessa del link in `DRIVE_BONIFICI_URL` in App.jsx): legge beneficiario/
  importo/mese dal PDF, entra in `pagamenti_esiti` se il dipendente è univoco, altrimenti
  coda "Bonifici da associare" (mai indovinato). Export Excel (dipendente, periodo
  cedolino, importo cedolino, importo bonifico, stato): `GET
  /paghe/associazioni-bonifici/export-excel`. Prima nota con saldo
  progressivo: `GET /paghe/prima-nota?dipendente_id=` (cumulato busta − erogato). Upload
  massivo documenti accetta anche ZIP (estrae) e categoria RIDUZIONE_ORARIO.
- `cedolini`: oltre a netto/pdf salva `voci` (tutti i codici busta) + dati chiave
  (rateo 13ª/14ª, Indennità L.207/24 + cng ann, Trattam. integ. L.21/2020, Rimborso 730,
  ore/giorni lavorati). Motore ricerca: GET `/api/dipendenti-cloud/cedolini/cerca-voce`
  (codice/testo); backfill storico: POST `/cedolini/riscansiona` (riusa il PDF salvato).

## Bug noti / da fare
- **[FIX 29/08/2026]** `backend/app/services/paghe_scheduler.py`: "🔄 Sincronizza
  da cedolini" e "🔗 Recupera bonifici storici" (pagina Cedolini & Bonifici) non
  erano mai stati eseguiti con successo in produzione — trovato controllando i
  dati reali: 333 buste su 1202 avevano già il bonifico corrispondente in
  archivio ma mai agganciato. Ora un job periodico (ogni 6h, primo giro 60s
  dopo l'avvio) richiama gli stessi due endpoint da solo. Trovati e corretti
  nello stesso giro tre bug che l'avrebbero reso inaffidabile: (1) `sincronizza()`
  sovrascriveva lo stato pagamento usando solo `bonifici.cedolino_id` (vista
  incompleta, 142 bonifici su 887), annullando le riconciliazioni fatte dal
  ponte storico ad ogni giro successivo — ora `pagamenti_esiti` vince quando
  presente; (2) `datetime.now()` naive nel fuso del processo (UTC su Render)
  interpretato da APScheduler nel fuso dello scheduler (Rome) — il primo giro
  finiva nel passato e veniva saltato; (3) `KeyError 'cedolino_id'` per
  `$ne:None` che matcha anche i documenti senza quel campo (745 bonifici su 887)
  — `sincronizza()` falliva SEMPRE, da sempre, anche sui vecchi click manuali.
- **[AUDIT 29/08/2026]** Portale mobile (`PortaleDipendente.jsx`): login
  richiedeva di ridigitare il cognome su tastiera ad ogni riapertura — ora il
  cognome dell'ultimo login riuscito è ricordato sul telefono (non il PIN):
  bottone "Continua come [Nome]" salta dritto al tastierino. Aggiunto anche
  `timeout: 15000` su axios + banner "Connessione assente — riprova" (prima,
  errore di rete e "nessun dato" mostravano la stessa schermata vuota). Restano
  da fare (priorità media/bassa, vedi audit completo): bottoni giorno turni
  troppo piccoli (~32px, target consigliato ~44px), nessun evidenziatore "OGGI"
  nella lista turni, feedback timbratura poco visibile (testo grigio invece di
  banner), conferma mancante su "annulla disponibilità bar".
- **[AUDIT 29/08/2026 — residuo, priorità media/bassa]** Altri N+1 (query dentro
  un ciclo) non ancora corretti: `tfr.py` (calcolo TFR per dipendente),
  `employee_contracts.py` (generazione massiva contratti), `dipendenti.py`
  (provisioning libretti sanitari), `dipendenti_cloud/__init__.py` (presenze
  storiche LUL). Stesso pattern già risolto più volte altrove in questo file:
  prefetch in blocco della collezione referenziata + lookup in memoria nel
  ciclo, zero query aggiuntive.
- Buste paga "foglio bianco": `portale_buste.py::scarica_pdf` genera un riepilogo se
  il cedolino non ha `pdf_data` (buste da Libro Unico senza PDF).
- OpenAPI: il token esposto in chat va rigenerato; testare in sandbox prima della prod.
  I payload eSignature/marca temporale/PEC vanno validati contro console.openapi.com.
- docx→PDF firma automatica: serve `CONVERTAPI_TOKEN` nelle env di Render (ConvertAPI);
  senza token l'endpoint risponde 503. LibreOffice resta solo come fallback locale.
- **[REFACTOR 28/08/2026, branch `claude/cedolini-refactor-debug-08k03g`]** Rimosso
  `backend/app/routers/bonifici_stipendi.py` (email IMAP + `prima_nota_salari` +
  `estratto_conto_movimenti`): era un sistema di riconciliazione bonifici↔stipendi
  parallelo a quello vivo (`paghe_mensili` + `pagamenti_esiti` in
  `dipendenti_cloud/__init__.py`), montato in `main.py` ma **nessuna pagina frontend
  lo chiamava mai** — codice morto, in violazione della regola "un solo sistema per
  funzione". Le note sui bug di omonimia in quel file (fix del 29/07/2026) non si
  applicano più: sono andate via col file. Il match per nome del sistema vivo
  (`_indici_dipendenti`, riusato ovunque: import CSV/Drive, upload documenti) ha
  sempre avuto la stessa protezione (match univoco o nessun match, mai indovinato).
- **[FIX 28/08/2026]** `POST /bonifici-da-associare/{id}/associa` (coda manuale
  "Bonifici da associare"): scriveva il bonifico assegnato solo nella collezione
  `bonifici`, ma la pagina "Cedolini & Bonifici" e lo stato paga (`stato_pagamento`
  sulla busta) leggono `pagamenti_esiti`/`paghe_mensili` — un bonifico confermato a
  mano da quella coda non risultava mai pagato da nessun'altra parte dell'app. Ora
  l'associazione manuale scrive anche in `pagamenti_esiti` e ricalcola lo stato con
  `_ricalcola_stato_paga` (lo stesso motore unico di tutti gli altri ingressi).
- **[NUOVO 28/08/2026]** `POST /paghe/importa-bonifici-drive`: prima la cartella Drive
  "Bonifici" (linkata da tempo nel bottone "📁 Cartella Drive bonifici", mai letta da
  nessun codice) non alimentava nulla — i bonifici bancari andavano importati a mano
  via CSV/Prima Nota. Ora un PDF nuovo nella cartella viene letto ed entra da solo
  nei pagamenti reali, se il dipendente è univoco; altrimenti finisce nella coda
  "Bonifici da associare" già esistente (mai indovinato). Va testato con l'archivio
  reale di bonifici (~44 PDF "Distinta Stipendi" più vecchi bonifici in formato
  diverso) per verificare la qualità dell'estrazione automatica prima di fidarsene
  senza controllare la coda dopo ogni import.
