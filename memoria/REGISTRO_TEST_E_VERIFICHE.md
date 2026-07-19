# Registro Test e Verifiche

## Baseline reale — 2026-07-19

- Data: 2026-07-19
- Branch: claude/test-coverage-analysis-co5wif
- Commit: f250f8cff1d1200bac85e5f3da85d2bfad8e920a
- Ambiente: sandbox Claude Code Remote (container isolato), Python 3.11.15, pytest 9.0.3
- Comando eseguito: `python -m pytest tests/ backend/tests/ -q --no-header`

### Risultato
- Raccolti: 633
- Passati: 618
- Falliti: 8
- Errori (in setup/collection): 7

### Classificazione

**Falliti (8)**:
- `tests/test_drive_cedolini_ingest.py::test_is_configured`
- `tests/test_quietanze_import.py::test_drive_quietanze_helpers`
- `backend/tests/test_fase2_fase3_fase4.py::TestPaypalRegression::test_paypal_status_ok`
- `backend/tests/test_fase2_fase3_fase4.py::TestPaypalRegression::test_paypal_sync_endpoint_accepts_body`
- `backend/tests/test_fase2_fase3_fase4.py::TestPaypalRiconcilia::test_riconcilia_shape`
- `backend/tests/test_fase2_fase3_fase4.py::TestPaypalRiconcilia::test_riconcilia_empty_body_ok`
- `backend/tests/test_fase2_fase3_fase4.py::TestPaypalRicevutaPdf::test_ricevuta_pdf_404_per_tx_inesistente`
- `backend/tests/test_fase2_fase3_fase4.py::TestPaypalRicevutaPdf::test_ricevuta_pdf_tx_reale`

**Errori in setup (7)**: tutti in `backend/tests/test_corrispettivi_ingest.py` (fixture `cleanup_before_and_after`) — `pymongo.errors.ServerSelectionTimeoutError` verso il cluster MongoDB Atlas configurato.

**Integrazioni non verificate nell'ambiente corrente**:
- i 6 falliti di `test_fase2_fase3_fase4.py` (chiamata HTTP reale verso backend Render, bloccata dal proxy di rete del sandbox con 403);
- i 2 falliti Drive/Quietanze (dipendono da configurazione Drive/Gmail assente in sandbox);
- i 7 errori (richiedono raggiungibilità di rete verso MongoDB Atlas, non disponibile dal container).

Gli 8 fallimenti e i 7 errori risultano bloccati o condizionati dall'ambiente esterno. Non costituiscono prova di un bug applicativo, ma nemmeno prova di corretto funzionamento. Le relative integrazioni sono NON VERIFICATE nell'ambiente di test corrente.

### Note ambiente
- La variabile `MONGO_URL` risultava impostata nel container, ma la connessione verso Atlas ha restituito `ServerSelectionTimeoutError` per irraggiungibilità di rete dal sandbox — non per assenza di configurazione.
- Installazione locale non versionata: `defusedxml==0.7.1` (già dichiarato in `backend/requirements.txt` ma assente nel venv del container) — installata solo per permettere la raccolta di 84 file di test altrimenti in errore di import; nessuna modifica a `requirements.txt` o ad altro file versionato.
- Incidente di sicurezza separato (SEC-001, censimento in SEC-001A completato): una credenziale MongoDB è comparsa nei log di questa sessione durante l'analisi. Nessun valore sensibile è riportato in questo registro. Decisione esplicita dell'utente (19/07/2026): **non ruotare la credenziale** — accesso alla chat e al dispositivo riservato esclusivamente all'utente, nessuna terza parte con visibilità sulla cronologia. SEC-001B (creazione nuovo utente Atlas) resta quindi **non eseguito, chiuso su decisione dell'utente**, non più in sospeso in attesa di autorizzazione.

### Gap di copertura individuati (conteggi reali sulla suite)
- **Frontend**: 0 test automatici su 129 componenti `.jsx`/`.tsx`; nessun tool (Vitest/Jest) configurato in `frontend/package.json`.
- **Sicurezza**: nessun test su rate limiting, CSRF, revoca/blacklist JWT; RBAC coperto solo da `test_sicurezza_auth.py` e `test_p2_admin_guards.py`.
- **Upload**: controllo "magic bytes" presente solo come fixture in `tests/conftest.py`, nessuna asserzione dedicata.
- **AI/LLM**: nessun test su fallimento/timeout/retry di Anthropic né su prompt injection nei documenti (richiesto da CLAUDE.md §20); `app/agents/` (`fiscale_sentinella.py`, `learning_brain.py`, `orchestrator.py`, `notifier.py`) senza test dedicati.
- **WebSocket**: 0 test, inclusa l'autenticazione WebSocket.
- **Concorrenza**: un solo riferimento esplicito in tutta la suite (`tests/test_p1_iva_scenari.py`).
- **Scheduler**: 4 riferimenti ad APScheduler, nessun test sistematico di "servizio esterno indisponibile" per Drive/Gmail/PayPal.
- **Integrazioni reali isolate**: `backend/tests/` richiede MongoDB Atlas raggiungibile; nessuna alternativa isolata (es. `mongomock`) per l'esecuzione in CI/sandbox senza rete.

Questa baseline non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.

## Aggiornamento — 2026-07-19 (stessa giornata, dopo ERP-001 e copertura test)

- Branch: claude/test-coverage-analysis-co5wif
- Commit: 60bdb07b310635471c785a5a66247e0e85cf4079
- Comando eseguito: `python -m pytest tests/ backend/tests/ -q --no-header`

### Risultato
- Raccolti: 649
- Passati: 642
- Falliti: 8
- Errori (in setup/collection): 7

Stessi identici 8 falliti e 7 errori della baseline del 2026-07-19 (stesse cause: Drive/Gmail non configurati in sandbox, chiamate HTTP reali verso Render bloccate dal proxy, MongoDB Atlas non raggiungibile dal container) — nessuna nuova integrazione non verificata, nessuna regressione.

### ERP-001 completato (non solo la protezione minima)
- Soglia di confidenza minima assoluta (0.7) non aggirabile dal chiamante in `apply-suggestions`.
- `suggestion_ids` ora limita realmente l'applicazione ai suggerimenti scelti (prima letto e mai usato).
- Audit strutturato su ogni chiamata (best-effort, non bloccante).
- Endpoint riservato agli amministratori, verificato anche a livello di routing reale (non solo unitario).

### Bug reale trovato e corretto durante la scrittura dei test di concorrenza
Un test di concorrenza reale (`asyncio.gather`, non solo chiamate sequenziali) su `registra_corrispettivo` (motore unico, regola canonica POS) ha rivelato che la guardia di idempotenza (find_one poi insert_one, due operazioni separate) poteva produrre un doppio movimento in Prima Nota Cassa per lo stesso corrispettivo sotto richieste concorrenti. Corretto sostituendo le due operazioni con un'unica `find_one_and_update` atomica lato MongoDB. Verificato su tutta la suite del motore contabile: nessuna regressione.

**Follow-up segnalato, non affrontato in questo step**: `_find_existing_corrispettivo` (collection `corrispettivi`, in `app/routers/invoices/corrispettivi_helpers.py`) ha lo stesso pattern find_one-poi-insert, non ancora verificato né corretto a questo livello.

**Raccomandazione non eseguita** (richiede accesso Atlas e autorizzazione separata per modifica di indici, §15 CLAUDE.md): aggiungere un indice univoco su `prima_nota_cassa` (data, matricola_rt, categoria, source) come seconda barriera lato database.

### Gap di copertura chiusi in questo aggiornamento
- **Sicurezza**: aggiunta copertura su revoca/blacklist JWT (`tests/test_token_blacklist.py`) e su rate limiting reale, non solo montato (`tests/test_rate_limiting.py`).
- **Upload**: aggiunta copertura dedicata al controllo magic bytes (`tests/test_upload_magic_bytes.py`).
- **Concorrenza**: aggiunto un secondo caso reale oltre a quello preesistente (`tests/test_concorrenza_registra_corrispettivo.py`).
- **Integrazioni reali isolate**: aggiunta una suite isolata con `mongomock`/`mongomock-motor` (`backend/tests/test_corrispettivi_ingest_isolato.py`) che affianca, senza sostituire, il test end-to-end reale contro backend live + Atlas.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.

## Aggiornamento — 2026-07-19 (chiusura gap CSRF/WebSocket/scheduler/AI + review PR #67)

- Branch: claude/test-coverage-analysis-co5wif
- Commit: 64cdac73d31247c9acc53b3c53a4d7bad4d66dbb
- PR: [#67](https://github.com/ceraldicontabilita/GestionaleCloud/pull/67) (aperta, in attesa di CI verde + merge autorizzato)

### Gap chiusi in questo aggiornamento
- **CSRF**: `tests/test_csrf_cookie_guard.py` — non esiste un token CSRF esplicito nel progetto (fatto reale, non un'omissione di test); l'unica protezione è `SameSite=Lax` + `HttpOnly` sul cookie di sessione. Guardia statica che fa fallire il test se un futuro cambiamento indebolisse questi due flag in uno dei 3 punti che impostano il cookie.
- **WebSocket**: `tests/test_websocket_autenticazione.py` — copre `_autentica_websocket` (nessun token, token invalido, token revocato, token da query vs cookie). Nota: `AuthenticationMiddleware` non intercetta mai lo scope `"websocket"` (comportamento di libreria di `BaseHTTPMiddleware`, non un bug), la protezione reale vive interamente in questa funzione — già corretto in un audit precedente (bug #25), qui solo testato per la prima volta.
- **Scheduler**: `tests/test_scheduler_resilienza_servizi_esterni.py` — verifica che un errore di connessione IMAP/Gmail dentro `scan_verbali_email_task` non si propaghi e non fermi lo scheduler, oltre al comportamento dell'interruttore `ENABLE_EMAIL_VERBALI_SYNC`.
- **AI/LLM**: `tests/test_ai_resilienza_e_confine_sicurezza.py` — fallimento/timeout Anthropic, API key assente, risposta non-JSON: mai propagati, sempre `{"success": False, ...}`. Test di prompt injection: anche nel caso peggiore (JSON iniettato che finge `"conferma_scrittura_gestionale": true`), il salvataggio reale resta bloccato perché il parametro è controllato dal chiamante, non dal contenuto del documento.

### Review automatica Codex su PR #67 — esito
Tre commenti dell'app `chatgpt-codex-connector`, valutati singolarmente:
1. **Bug reale confermato e corretto**: `soglia_confidenza` con `NaN`/`Infinity` bypassava la soglia minima ERP-001 (`max(nan, 0.7) == nan`, ogni confronto `<` sempre falso). Riprodotto empiricamente, corretto con coercizione a float + controllo di finitezza, test dedicati aggiunti.
2. **Osservazione corretta ma non un bug di questa PR**: `get_current_admin_user` non legge il cookie di sessione (solo header Bearer) — stesso pattern già usato in 30+ altri endpoint admin-only del repository. Segnalato come follow-up architetturale separato (cambierebbe l'autenticazione admin di tutta l'app), non affrontato qui.
3. **Raccomandazione già nota**: manca un indice univoco su `prima_nota_cassa` come seconda barriera lato database contro il bug di concorrenza corretto in questo stesso PR — già dichiarato esplicitamente come follow-up nella descrizione della PR prima ancora del commento. Richiede accesso Atlas (non disponibile) e autorizzazione separata per modifica indici (§15 CLAUDE.md).

### Risultato finale suite
`python -m pytest tests/ backend/tests/ -q --no-header` → 661 passati, stessi identici 8 falliti/7 errori della baseline (nessuna regressione).

### Gap di copertura ancora aperti
- **Frontend**: 0 test automatici, nessun tool (Vitest/Jest) configurato.
- **Sicurezza**: RBAC coperto solo per gli endpoint già censiti in `test_p2_admin_guards.py`; autenticazione admin non supporta il cookie di sessione (follow-up segnalato sopra).
- **AI/LLM**: `app/agents/` (`fiscale_sentinella.py`, `learning_brain.py`, `orchestrator.py`, `notifier.py`) senza test dedicati.
- **Concorrenza**: `_find_existing_corrispettivo` (collection `corrispettivi`) ha lo stesso pattern find_one-poi-insert del bug corretto in `registra_corrispettivo`, non ancora verificato a quel livello.
- **Indice univoco** su `prima_nota_cassa` lato Atlas — richiede accesso e autorizzazione separata.
- **Rotazione credenziale MongoDB** esposta durante l'analisi — step di sicurezza separato, sospeso in attesa di accesso alla dashboard Atlas.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.

## Aggiornamento — 2026-07-19 (secondo bug di concorrenza, dopo il merge di PR #67)

- Branch: claude/test-coverage-analysis-co5wif (nuovo lavoro dopo il merge)

### Bug reale trovato e corretto (follow-up dal fix in PR #67)
`_find_existing_corrispettivo` (`app/routers/invoices/corrispettivi_helpers.py`) ha lo stesso pattern find_one-poi-insert già corretto in `registra_corrispettivo`, ma su 3 livelli sequenziali (chiave XML, poi data+matricola, poi data+totale). Riprodotto con un test di interleaving reale (fake DB con `await asyncio.sleep(0)` su ogni operazione, non mongomock — che non cede mai il controllo e quindi NON avrebbe rivelato il problema): due upload quasi simultanei dello stesso corrispettivo creavano **due documenti "corrispettivi"** duplicati. Il movimento in Prima Nota Cassa non si duplicava (il fix di PR #67 teneva), ma il documento sorgente sì.

**Correzione applicata (parziale, deliberatamente)**: solo l'inserimento finale per un corrispettivo nuovo è stato reso atomico (`find_one_and_update` con upsert), e solo quando è disponibile la chiave naturale del file XML (`corrispettivo_key`) — il caso riprodotto nel test e quello a rischio reale per import automatici concorrenti. I due controlli più deboli (data+matricola, data+totale, usati per corrispettivi manuali/provvisori senza chiave XML) restano non atomici: rischio residuo noto e accettato, non coperto da questo fix mirato per non ampliare il cambiamento oltre lo scenario verificato.

### Nota sul metodo
Confermato che i test isolati con `mongomock` (introdotti in PR #67) non sono sufficienti a rivelare race condition: `mongomock` esegue le operazioni senza mai cedere il controllo all'event loop, quindi `asyncio.gather` non produce interleaving reale. Per testare la concorrenza serve un fake DB che ceda esplicitamente il controllo (`await asyncio.sleep(0)`) ad ogni operazione — tecnica già usata per il primo bug, riapplicata qui.

### Gap di copertura ancora aperti (aggiornato)
- **Concorrenza**: i due controlli più deboli di `_find_existing_corrispettivo` (data+matricola, data+totale) restano non atomici — rischio residuo noto.
- **Indice univoco** su `prima_nota_cassa` e su `corrispettivi.corrispettivo_key` lato Atlas — richiede accesso e autorizzazione separata.
- **Rotazione credenziale MongoDB**: decisione esplicita dell'utente (19/07/2026) di NON ruotarla — chat e dispositivo ad accesso esclusivo dell'utente. Chiuso, non più un'azione in sospeso.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.

## Aggiornamento — 2026-07-19 (review PR #68, app/agents/, chiusura backlog)

- Branch: claude/test-coverage-analysis-co5wif

### Review Codex su PR #68 — esito
1. **Bug reale confermato e corretto**: la guardia atomica sull'insert (`find_one_and_update` su `corrispettivo_key`) non escludeva i soft-delete come fa `_find_existing_corrispettivo` — un corrispettivo eliminato con la stessa chiave XML impediva di ricrearlo ricaricando lo stesso file. Corretto aggiungendo lo stesso filtro `entity_status`/`status`, test dedicato aggiunto.
2. **Raccomandazione confermata ma già nota**: manca un indice univoco su `corrispettivi.corrispettivo_key` (verificato in `app/database.py::_create_indexes` e `app/scripts/create_indexes.py`: solo indici su `data`) — stessa limitazione già dichiarata nella descrizione della PR, richiede accesso Atlas e autorizzazione separata.

### Bug reali trovati scrivendo i test per app/agents/ (mai testato prima)
- `fiscale_sentinella.py::_estrai_dati_avviso`: il regex dell'importo includeva "tributo" tra le parole-chiave, quindi "**Codice Tributo:** 9001" (il codice a 4 cifre) veniva scambiato per l'importo prima di arrivare al vero "Importo: €500,00" più avanti nel testo — un avviso fiscale reale avrebbe mostrato l'importo sbagliato in una segnalazione letta da una persona. Corretto rimuovendo "tributo" dalle parole-chiave dell'importo.
- `notifier.py::crea_segnalazione`: importava `invia_messaggio` da `telegram_notifications.py`, funzione mai esistita (quella reale è `send_notification`) — le notifiche Telegram per gli avvisi urgenti degli agenti non hanno **mai** funzionato, l'errore veniva inghiottito silenziosamente dal `except` generico. Corretto.

### Copertura test aggiunta
- `tests/test_agente_fiscale_sentinella.py`: estrazione regex (input normale, vuoto, ostile/malformato — mai deve sollevare), le tre decisioni sull'avviso bonario (già ravveduto / già pagato / da pagare urgente o no), idempotenza della segnalazione F24 in scadenza.
- `tests/test_agenti_orchestrator_notifier_learning.py`: isolamento tra agenti (uno che fallisce non blocca gli altri, stato di errore registrato), notifica Telegram best-effort (fallimento non blocca la segnalazione), calcolo confidenza e idempotenza in `learning_brain.py`.

### Risultato finale suite
`python -m pytest tests/ backend/tests/ -q --no-header` → 681 passati, stessi identici 8 falliti/7 errori della baseline nota — nessuna regressione.

### Gap di copertura ancora aperti
- **Concorrenza**: i due controlli più deboli di `_find_existing_corrispettivo` (data+matricola, data+totale) restano non atomici.
- **Indice univoco** su `prima_nota_cassa` e `corrispettivi.corrispettivo_key` lato Atlas — richiede accesso e autorizzazione separata.
- **Autenticazione admin** non supporta il cookie di sessione (solo Bearer) — pattern condiviso da 30+ endpoint, follow-up architetturale segnalato, non affrontato.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.

## Aggiornamento — 2026-07-19 (setup test frontend: Vitest)

- Branch: claude/test-coverage-analysis-co5wif

### Configurazione aggiunta
Il frontend non aveva alcun tool di test configurato (0 test su 129 componenti). Aggiunto Vitest + Testing Library:
- `frontend/package.json`: nuove devDependencies (`vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`), script `test` (`vitest run`) e `test:watch` (`vitest`).
- `frontend/vite.config.js`: blocco `test` (environment `jsdom`, `globals: true`, setup file).
- `frontend/src/test/setup.js`: import dei matcher `@testing-library/jest-dom`.
- `.github/workflows/frontend-build.yml`: nuovo step `yarn test` tra install e build, così la suite gira davvero in CI ad ogni push/PR, non solo in locale.

**Incidente evitato durante il setup**: `npm run build` (usato per verificare che il setup non rompesse nulla) ha sovrascritto `frontend/dist/`, che risulta **committato nel repository** (pubblicato da Render come static site) — non ignorato come mi aspettavo. Ripristinato subito con `git checkout` + `git clean` prima di qualunque commit; nessuna modifica a `dist/` è stata versionata. Da tenere a mente per futuri lavori sul frontend: non lanciare build di verifica senza controllare `git status` su `dist/` subito dopo.

**Nota gestori pacchetti**: il progetto usa `yarn.lock` come lockfile canonico (committato), `package-lock.json` è in `.gitignore`. L'ambiente sandbox ha `NODE_ENV=production`, che fa sì che sia `npm install` sia `yarn install` saltino le devDependencies per default — necessario forzare l'inclusione (`npm install --include=dev` / `yarn install --production=false`) per installare gli strumenti di test.

### Primo test reale: funzioni di formattazione (`frontend/src/lib/utils.js`)
Scelte come primo bersaglio perché usate in pressoché ogni pagina dell'app per mostrare importi e date — un bug qui è visibile ovunque (il file contiene già un commento su un bug reale corretto il 14/07/2026: "1119 €" invece di "€ 1.119,00"). `frontend/src/lib/utils.test.js`: 27 test su `formatEuro`, `formatEuroD`, `formatEuroShort`, `formatEuroStr`, `formatDateIT`, `formatDateGGMM`, `parseDateIT`, `formatDateTimeIT`, `formatDateShort` — input normali, null/undefined, non numerici/malformati, negativi, importi grandi con più separatori di migliaia. Tutti verdi, nessun bug trovato in queste funzioni specifiche.

### Risultato
`yarn test` (frontend) → 27 passati. `python -m pytest tests/ backend/tests/ -q` (backend, invariato) → 681 passati, stessa baseline nota.

### Gap di copertura ancora aperti
- **Frontend**: solo le funzioni pure di `lib/utils.js` sono coperte; 0 test sui componenti React (rendering, interazione utente, chiamate API) — il grosso dei 129 componenti resta non testato. Harness ora pronto per estendere la copertura in un prossimo giro.
- **Concorrenza**: i due controlli più deboli di `_find_existing_corrispettivo` (data+matricola, data+totale) restano non atomici.
- **Indice univoco** su `prima_nota_cassa` e `corrispettivi.corrispettivo_key` lato Atlas — richiede accesso e autorizzazione separata.
- **Autenticazione admin** non supporta il cookie di sessione (solo Bearer) — pattern condiviso da 30+ endpoint, follow-up architetturale segnalato, non affrontato.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.

## Aggiornamento — 2026-07-19 (bug reali segnalati dall'utente sulla Fattura 20 — DI MASSA DARIO & c. sas)

- Branch: claude/test-coverage-analysis-co5wif

### Contesto
L'utente ha segnalato "Incasso fattura 20 - DI MASSA" registrato erroneamente in Prima Nota Banca DARE, e poi un problema più grave sull'importo ("il sistema dovrebbe riportare l'importo a 12.000 più IVA... il file XML porta un importo diverso"), più la richiesta di poter sempre vedere l'XML originale della fattura nel modale "vedi fattura". Autorizzato dall'utente a correggere ("i ti autorizzo a correggere").

### Bug 1 — Classificazione TD24-27 come "Incasso" invece di pagamento fornitore
`app/routers/prima_nota_module/sync.py::determina_tipo_movimento_fattura` aveva un ramo `TIPI_FATTURA_ATTIVA = ["TD24","TD25","TD26","TD27"]` → `("entrata", "Incasso cliente", ...)`. Questo modulo gestisce ESCLUSIVAMENTE fatture passive (verificato via grep esaustivo di tutti i call site nella sessione precedente): il TipoDocumento FatturaPA è assegnato da chi EMETTE il documento, non indica la direzione per chi lo riceve. **Fix**: rimosso il ramo, TD24-27 restano sempre "uscita"/"Fatture" come ogni altra fattura passiva (nota di credito TD04/TD08 resta invariata, unico caso legittimo di "entrata"). Test: `tests/test_prima_nota_nota_credito.py` (nuovi: `test_determina_tipo_movimento_fattura_td24_resta_uscita`, `test_conferma_fattura_provvisoria_td24_resta_uscita`).

### Bug 2 — Il parser XML legge solo il PRIMO `<FatturaElettronicaBody>` del file
`app/parsers/fattura_elettronica_parser.py` usava `find_element(root, 'FatturaElettronicaBody')` (ritorna un solo elemento) invece di iterare su tutti i body. Un file FatturaPA può contenere più fatture raggruppate sotto lo stesso header/CedentePrestatore (caso reale per fatture differite spedite insieme): ogni fattura oltre la prima veniva **persa silenziosamente** (importo, righe, tutto), mentre il foglio XSLT usato per il rendering "originale" nel modale itera correttamente su tutti i body — spiegando un possibile disallineamento tra ciò che si vede nel modale e ciò che finisce in contabilità. **Fix**: il parser ora estrae tutte le fatture del file (`parse_fattura_xml_multi`); `parse_fattura_xml` (compatibilità) ritorna la prima e segnala le altre (`multi_body_count`, `_altri_body`); `app/routers/invoices/fatture_upload.py::process_xml_bytes` importa TUTTE le fatture trovate nello stesso file invece di scartare silenziosamente le successive. Non è stato possibile verificare se questo bug è la causa esatta dell'importo errato sulla Fattura 20 specifica (nessun accesso al file XML originale in questa sessione) — verifica puntuale rimandata a quando l'utente fornirà l'XML. **Nota**: nessuna logica di sottrazione acconto è mai stata trovata nel codice (il campo `ImportoTotaleDocumento` viene sempre letto verbatim); se la causa sulla fattura specifica fosse un acconto da nettare e non un problema di multi-body, serve una correzione separata, puntuale, con l'XML alla mano. Test: `tests/test_fattura_elettronica_parser_multi_body.py` (4 test: singolo body invariato, multi-body con `parse_fattura_xml`/`parse_fattura_xml_multi`, import di tutte le fatture in `process_xml_bytes`).

### Bug 3 — Modale "vedi fattura" non permetteva mai di vedere l'XML originale grezzo
Anche quando l'XML originale era salvato (`xml_raw`/`xml_file_path`), non esisteva alcun endpoint per scaricarlo/vederlo come testo grezzo — solo un rendering HTML (via XSLT se disponibile, altrimenti un riepilogo ricostruito con pochi campi, **senza segnalarlo**). **Fix**: nuovo endpoint `GET /api/fatture-ricevute/fattura/{id}/xml-originale` (`app/routers/fatture_module/crud.py::download_xml_originale`, condivide la stessa logica di ricerca XML di `view_fattura_assoinvoice` tramite `_trova_fattura_e_xml_originale`) che scarica l'XML così com'è arrivato; pulsante "📥 Scarica" sempre presente in `ModalFattura.jsx` (usa il prop `onDownload` già supportato da `DocumentViewerModal`); banner di avviso giallo aggiunto in `generate_invoice_html` (il riepilogo di fallback) che dichiara esplicitamente "Questo NON è il documento XML originale" quando il rendering XSLT non è disponibile. Test: `tests/test_fattura_xml_originale_download.py` (4 test: 404 fattura assente, 404 XML non salvato, download bytes corretto, banner presente nel fallback).

### Verifica
`python -m pytest tests/ -q` → 686 passati, stessi 2 falliti preesistenti/ambientali (`test_drive_cedolini_ingest.py::test_is_configured`, `test_quietanze_import.py::test_drive_quietanze_helpers`, dipendono da env Drive assente in sandbox — confermato falliscono identicamente sul commit precedente, nessuna regressione). `yarn test` (frontend) → 27 passati, invariato. `yarn build` eseguita per verifica sintattica, `frontend/dist` ripristinato subito dopo (non modificato nel commit). Rigenerate le mappe endpoint (`genera_mappa.py`, `genera_classificazione_endpoint.py`) per il nuovo endpoint `/xml-originale`; rigenerato l'audit dead-code frontend.

### Ancora da fare (non affrontato in questo aggiornamento)
- Verifica puntuale della Fattura 20 specifica (numero esatto/importo/acconto) — richiede l'XML originale dall'utente.
- Eventuale logica di netting acconto, se la causa reale sulla fattura specifica risultasse diversa dal bug multi-body.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.
