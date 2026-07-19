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
- Incidente di sicurezza separato: è richiesta la rotazione preventiva di una credenziale esterna potenzialmente esposta. Nessun valore sensibile è riportato in questo registro. La rotazione richiede uno step dedicato e l'autorizzazione esplicita dell'utente.

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

### Gap di copertura ancora aperti (invariati rispetto alla baseline)
- **Frontend**: 0 test automatici, nessun tool (Vitest/Jest) configurato.
- **Sicurezza**: CSRF non testato; RBAC coperto solo per gli endpoint già censiti in `test_p2_admin_guards.py`.
- **AI/LLM**: nessun test su fallimento/timeout/retry di Anthropic né su prompt injection nei documenti; `app/agents/` senza test dedicati.
- **WebSocket**: 0 test, inclusa l'autenticazione WebSocket.
- **Scheduler**: nessun test sistematico di "servizio esterno indisponibile" per Drive/Gmail/PayPal.

Questo aggiornamento non modifica `PROGRAMMA_IMPLEMENTAZIONE_CANONICO.md` né `STATO_IMPLEMENTAZIONE_CANONICO.md`.
