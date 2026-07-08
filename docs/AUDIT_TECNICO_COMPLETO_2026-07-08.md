# Audit Tecnico Completo - 2026-07-08

Branch di lavoro: `refactor/full-repo-audit-operativa`

## Sintesi esecutiva

Il repository e' funzionalmente ricco ma strutturalmente sovraccarico. Il progetto contiene una base operativa valida su FastAPI + MongoDB + React, ma anche:

- superfici API troppo ampie e parzialmente duplicate;
- pagine frontend monolitiche con UX non uniforme;
- test misti unit/integration non separati correttamente;
- presenza di entrypoint e file legacy non piu' usati;
- dipendenze e percorsi di deploy che aumentano il rischio di regressioni.

Il sistema non e' "rotto", ma oggi non e' ancora governabile come piattaforma modulare stabile.

## Stato verificato

### Frontend

- `npm run build` in `frontend/`: OK
- warning presente: import misto dinamico/statico di `frontend/src/api.js`

### Backend

- `python -m pytest tests`: `90 passed, 1 warning`
- `python -m pytest tests backend/tests`: dopo correzione del branch -> `90 passed, 2 skipped, 1 warning`

### Correzione gia' applicata nel branch

I test `backend/tests/test_corrispettivi_ingest.py` e `backend/tests/test_fase2_fase3_fase4.py` fallivano in collection se mancava `REACT_APP_BACKEND_URL`. Ora vanno in `skip` e non bloccano la suite locale.

## Deploy e ambienti

Dal repository risultano questi comportamenti:

- `main` -> produzione Render -> `https://impresasemplice.online`
- il frontend viene servito dallo static buildato in `frontend/dist`
- il dominio `https://contabilita-operativa-ceraldi.area-di-lavo-2011.chatgpt-team.site/` non e' la stessa pipeline di produzione Render

### Implicazione operativa

Salvare su `main` **non** aggiorna automaticamente anche il dominio `chatgpt-team.site`.

Per avere entrambi aggiornati servono due azioni separate:

1. push/merge su `main` per la produzione Render;
2. deploy dedicato Sites per l'ambiente `chatgpt-team.site`.

## Classificazione problemi

## P0 - Critici

### P0.1 Test integration non isolati dalla suite locale

File:

- `backend/tests/test_corrispettivi_ingest.py`
- `backend/tests/test_fase2_fase3_fase4.py`

Problema:

- i test dipendevano da `REACT_APP_BACKEND_URL` e fallivano in collection;
- la suite non era affidabile come guardrail CI o locale.

Stato:

- corretto nel branch con `pytest.skip(..., allow_module_level=True)`.

### P0.2 Configurazione sicurezza non fail-fast di default

File:

- `app/config.py`

Problema:

- `SECRET_KEY` viene generata dinamicamente se assente;
- `DB_NAME` di default e' `azienda_erp_db`, mentre la documentazione operativa parla di `Gestionale`;
- il sistema continua ad avviarsi anche in condizioni pericolose se `FAIL_FAST_SECRETS` non e' attivo.

Rischio:

- JWT invalidati a ogni riavvio;
- puntamento accidentale al database sbagliato;
- comportamento diverso tra locale, preview e produzione.

### P0.3 Pipeline di deploy frontend fragile

Evidenze:

- `app/main.py` serve `frontend/dist`
- `memoria/PROMPT_SESSIONE.md` indica che `frontend/dist` deve essere committato

Problema:

- se il codice sorgente cambia ma `dist` non viene ricostruito e committato, la produzione serve frontend stale.

Rischio:

- mismatch tra sorgente e produzione;
- bug "fantasma" non riproducibili leggendo solo `src/`.

### P0.4 Superficie API eccessiva e parzialmente duplicata

File principali:

- `app/router_registry.py`
- numerosi moduli in `app/routers/`

Problema:

- il registry monta un numero molto elevato di router;
- esistono moduli quasi sovrapposti su documenti, email, verbali, riconciliazione, PayPal, configurazioni.

Rischio:

- difficile capire la rotta canonica;
- rischio alto di endpoint vivi ma non presidiati da UI;
- manutenzione costosa e regressioni trasversali.

## P1 - Alti

### P1.1 Frontend con UX non uniforme e forte uso di browser primitives

Ricerca in `frontend/src`:

- numerosissimi `alert(...)`
- molti `window.confirm(...)`
- molti `window.open(...)`

Problema:

- UX incoerente rispetto ai modali/confirm dialog introdotti nelle pagine piu' recenti;
- comportamento poco controllabile su mobile e in ambienti embedded;
- scarsa tracciabilita' degli errori lato utente.

### P1.2 Duplicazione della navigazione

File:

- `frontend/src/App.jsx`
- `frontend/src/components/layout/TopNav.jsx`

Problema:

- menu desktop e menu mobile sono mantenuti a mano in strutture diverse (`NAV_ITEMS`, `ALTRO_ITEMS`, `MOBILE_NAV`, `ALL_NAV_ITEMS`);
- rischio elevato di incoerenza tra desktop e mobile.

### P1.3 Entry point React legacy inutilizzati

File:

- `frontend/src/App.js`
- `frontend/src/index.js`

Problema:

- sono residui del template iniziale;
- l'app reale usa `frontend/src/main.jsx` + `frontend/src/App.jsx`.

Rischio:

- confusione per nuovi sviluppi;
- possibile tooling che aggancia file sbagliati;
- documentazione non allineata.

### P1.4 Pagine hub corrette come visione, ma troppo accoppiate

File:

- `frontend/src/pages/hub/*.jsx`

Problema:

- gli hub consolidano bene le aree funzionali, ma caricano componenti molto grandi e spesso monolitici;
- mancano boundary modulari forti tra dati, stato UI e logica operativa.

### P1.5 `api.js` importato sia staticamente sia dinamicamente

Build warning:

- Vite segnala che `frontend/src/api.js` non puo' essere estratto in chunk separato.

Impatto:

- non e' un blocker, ma indica una strategia di caricamento non coerente.

### P1.6 Router e responsabilita' mescolate

Esempi:

- `settings.py` + `settings_router.py`
- `verbali_noleggio.py` + `verbali_noleggio_api.py`
- molte rotte `documenti`, `email_download`, `email_scanner`, `document_ai`, `ai_parser`

Problema:

- naming e ownership non sono canonici;
- stesso dominio applicativo distribuito su piu' router e servizi.

## P2 - Medi

### P2.1 Mojibake / encoding sporco

Evidente in vari file frontend/backend e commenti.

Impatto:

- peggiora manutenzione e credibilita' del codice;
- aumenta il rischio di patch sbagliate.

### P2.2 File legacy e artefatti da pulire

Esempi:

- `frontend/package.json.bak`
- `frontend/src/App.js`
- `frontend/src/index.js`
- `frontend/dist/*` come artefatto committato

### P2.3 Warning dipendenze Python

Test warning:

- `PendingDeprecationWarning` su `multipart` / `python_multipart`

Impatto:

- non blocca, ma indica debito tecnico nelle dipendenze.

## Analisi architetturale per area

## Backend

### Punti buoni

- `app/main.py` e `app/router_registry.py` centralizzano bootstrap e registrazione;
- `Database` singleton con indici e pooling;
- presenza di scheduler, middleware auth, handlers, servizi e repository;
- MongoDB resta una base coerente col target richiesto.

### Problemi

- troppo codice direttamente nei router;
- naming non uniforme tra modelli, servizi e collection;
- mancano boundary piu' netti per moduli target;
- persistenza e side effect talvolta avvengono in piu' posti.

## Frontend

### Punti buoni

- routing gia' riallineato a hub funzionali;
- anno globale centralizzato;
- design system embrionale presente (`styles/ds`, `components/ds`, `components/ui`);
- viewer fatture in-page ora coerente nelle aree contabili principali.

### Problemi

- molte pagine restano monoliti > difficile testarle o rifattorizzarle a pezzi;
- persistenza di pattern vecchi (alert, confirm, aperture esterne);
- navigazione duplicata;
- presenza contemporanea di stile inline, design system custom e componenti UI utility.

## Database / MongoDB

### Punti buoni

- strategia MongoDB mantenibile;
- molti indici gia' presenti in `app/database.py`.

### Problemi

- forte dipendenza da nomi collection legacy;
- rischio di doppie scritture logiche su collezioni condivise;
- gap tra nomi canonici documentati e default runtime (`DB_NAME`).

## Autenticazione e sicurezza

### Punti buoni

- middleware dedicato;
- provider React dedicato;
- esiste meccanismo di secret condiviso via DB.

### Problemi

- fallback automatico di `SECRET_KEY` non adatto a produzione se non presidiato;
- fail-fast opzionale invece che default;
- bisogna auditare sistematicamente gli endpoint `public` e i bridge esterni.

## Modello target e refactoring proposto

Obiettivo: trasformare il progetto in tre macro-moduli forti, condividendo auth, document ingestion, anagrafiche e motore contabile.

## 1. Modulo Contabilita'

Sottomoduli canonici:

- Fatture XML
- Corrispettivi XML
- Prima Nota Cassa
- Prima Nota Banca
- Incassi POS
- Riconciliazione bancaria
- Liquidazione IVA mensile
- Import F24
- Dashboard contabile

Refactoring:

- introdurre namespace backend canonici per dominio;
- consolidare i flussi documentali in una pipeline unica;
- unificare il motore anno/periodo su tutte le query;
- portare le schermate in componenti task-oriented e non pagine monolitiche.

## 2. Modulo HACCP

Sottomoduli:

- Ricettario
- Food Cost
- Magazzino
- Lotti
- Tracciabilita'
- Fornitori
- Storico prezzi
- Miglior fornitore
- Scadenze

Refactoring:

- separare nettamente il dominio HACCP dal dominio contabile;
- mantenere MongoDB ma con collection canoniche per magazzino/tracciabilita';
- evitare che UI contabili e HACCP condividano componenti monolitici senza boundary.

## 3. Modulo Dipendenti

Sottomoduli:

- Portale personale
- Login
- Buste paga PDF
- Riconciliazione pagamenti stipendi

Refactoring:

- chiarire il confine tra ERP e app esterna HR;
- mantenere nel gestionale solo cio' che serve alla contabilita' o alla riconciliazione;
- evitare link/deleghe deboli e definire contratti API espliciti.

## Roadmap di refactoring proposta

### Fase 1 - Stabilizzazione

- rendere tutti i test eseguibili localmente e in CI;
- bloccare la produzione se mancano secret/database corretti;
- mappare endpoint usati/non usati;
- congelare le rotte canoniche.

### Fase 2 - Consolidamento backend

- separare router, service, repository per dominio canonico;
- chiudere i duplicati documenti/email/verbali;
- creare un layer di validazione uniforme;
- catalogare le collection canoniche e quelle legacy.

### Fase 3 - Consolidamento frontend

- estrarre config unica di navigazione;
- sostituire alert/confirm/prompt con modali e toast;
- ridurre i monoliti di pagina in feature components;
- standardizzare design system e pattern azione/documento.

### Fase 4 - Nuovi moduli target

- completare Dashboard Contabile;
- aprire verticalizzazione HACCP;
- consolidare modulo Dipendenti / riconciliazione stipendi;
- razionalizzare import automatici documentali.

## Interventi immediati consigliati

1. Rendere `FAIL_FAST_SECRETS` il default in produzione.
2. Normalizzare `DB_NAME` al valore canonico realmente usato.
3. Centralizzare la navigazione frontend in una sola struttura dati.
4. Rimuovere o archiviare `frontend/src/App.js` e `frontend/src/index.js`.
5. Convertire le pagine con piu' alert/confirm:
   - `Admin.jsx`
   - `Documenti.jsx`
   - `Fornitori.jsx`
   - `GestioneAssegni.jsx`
   - `Scadenze.jsx`
   - `BatchReprocessing.jsx`
6. Separare i test integration pubblici dai test unit/logic.

## Conclusione

Il progetto puo' essere portato al gestionale desiderato senza cambiare stack:

- MongoDB: da mantenere
- FastAPI: da mantenere
- React: da mantenere

La priorita' non e' "rifare tutto", ma rendere canonici:

- i domini,
- le rotte,
- le collection,
- la navigazione,
- i pattern UI,
- i test.

Solo dopo questa normalizzazione conviene estendere in modo serio HACCP e Dipendenti.
