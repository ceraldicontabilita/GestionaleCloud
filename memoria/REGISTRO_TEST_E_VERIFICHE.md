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
