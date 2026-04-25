# Ceraldi ERP

Gestionale web interno di Ceraldi Group S.R.L. (Napoli).
Unifica contabilita', ciclo passivo, prima nota, HR, magazzino, noleggio auto,
riconciliazione bancaria e tracciabilita' HACCP — con acquisizione automatica
da PEC e Gmail e sistema relazionale a eventi.

Repository GitHub: `ceraldicontabilita/gestionale2`
Branch di riferimento: `main`

## Stack

- Frontend: React 18 + Vite (porta 3000) — design inline via `src/lib/utils.js`
- Backend: FastAPI + Motor async (porta 8001)
- Database: MongoDB Atlas, DB `Gestionale`, cluster `cluster0.vofh7iz`
- Scheduler: APScheduler (PEC orario, Gmail 10 min)
- Servizi core: `app/services/` — event bus, alert engine, riconciliazione, partite aperte

## Regola canonica fornitori

La collection MongoDB primaria dell'anagrafica fornitori e' **`fornitori`**.

`suppliers` resta solo nome tecnico/inglese per moduli, servizi, route API e retrocompatibilita'.
Non deve essere usato come collection Mongo separata.

Fonti di verita':

- `app/db_collections.py`: `COLL_SUPPLIERS = "fornitori"`, `COLL_FORNITORI = "fornitori"`
- `app/database/collections.py`: `Collections.FORNITORI = "fornitori"`, `Collections.SUPPLIERS = "fornitori"`
- `app/database.py`: `Collections.SUPPLIERS = "fornitori"`
- `memoria/FORNITORI_REGOLA_CANONICA.md`: regola operativa dettagliata

Le API frontend restano compatibili su `/api/suppliers`, ma leggono/scrivono la collection `fornitori` tramite costanti backend.

## Avvio rapido (ambiente Emergent)

I servizi sono gestiti da Supervisor e si avviano da soli:

```bash
sudo supervisorctl status
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
```

Frontend: http://localhost:3000 (esterno: valore di `REACT_APP_BACKEND_URL` in `frontend/.env`)
Backend API: http://localhost:8001/api
Health: `curl -s http://localhost:8001/api/health`

## Struttura

```text
/app
├── backend/            Entry point FastAPI (server.py) + .env
├── app/                Codice applicativo backend
│   ├── routers/        Router FastAPI organizzati per modulo
│   ├── services/       Servizi core condivisi
│   ├── models/         Modelli dati e stati
│   ├── parsers/        Parser XML, PDF
│   ├── database.py     Connessione MongoDB + indici
│   ├── db_collections.py        Costanti collection principali
│   └── database/collections.py  Costanti collection class-based
├── frontend/           React + Vite
├── memoria/            Documentazione viva
├── claude-patches/     Patch di sviluppo
├── PIANO_LAVORO_RELAZIONALE.md
├── DIARIO.md
└── README.md
```

## Dove leggere la documentazione

- `memoria/INDEX.md` — scheda rapida: stack, collections, route, regole critiche
- `memoria/FORNITORI_REGOLA_CANONICA.md` — regola definitiva `fornitori`/`suppliers`
- `memoria/PRD.md` — product requirements, stato implementazione, backlog
- `memoria/LOGICA_OPERATIVA.md` — funzionamento pagina per pagina
- `memoria/BACKLOG.md` — backlog operativo con priorita'
- `PIANO_LAVORO_RELAZIONALE.md` — architettura relazionale, catalogo alert, piano 8 fasi

## Architettura relazionale

Il gestionale usa un sistema a eventi sincroni per far comunicare i moduli.
Quando un'entita' cambia stato, il cambio si propaga automaticamente:

```text
Fattura XML -> crea/aggiorna Fornitore -> crea Partita Aperta -> genera Alert se incompleta
Movimento Banca -> cerca Match con Partite -> Riconcilia -> aggiorna Fattura/F24/Stipendio
Cedolino importato -> aggiorna Dipendente -> crea Prima Nota Salari -> crea Partita Stipendio
```

I servizi core in `app/services/`:

- `event_bus.py` — dispatcher eventi sincrono tra moduli
- `alert_engine.py` — codici alert standardizzati con trigger e chiusura
- `audit_logger.py` — log unificato di ogni cambio stato
- `deduplica.py` — verifica duplicati per tutte le entita'
- `partite_aperte_engine.py` — scadenziario materializzato
- `riconciliazione_engine.py` — scoring match a 4 livelli

## Principi

1. I ricavi arrivano solo da `corrispettivi`. Le `invoices` sono costi.
2. Il metodo di pagamento di una fattura viene sempre dall'anagrafica del fornitore, mai dall'XML SDI.
3. Collezioni canoniche: `fornitori`, `dipendenti`, `warehouse_inventory`.
4. `suppliers` e' alias tecnico/API, non collection primaria.
5. Design system: una sola fonte di verita' in `src/lib/utils.js`. Niente Tailwind, niente Shadcn.
6. Full-frame e responsive: layout 100% width, niente `max-width` fisso, tabelle con wrapper scrollabile.
7. Nomi collezioni: importare sempre da `app/db_collections.py` o `app/database/collections.py`, mai stringhe hardcoded.
8. Patch Claude: mai push diretto su main, sempre in `claude-patches/chat-N-descrizione/` con `ISTRUZIONI.md`.
9. Ogni operazione CRUD significativa chiama `propagate_event()` o pubblica evento quando previsto.

## Package management

- Python: `pip install <pkg> && pip freeze > /app/backend/requirements.txt`
- Node: `cd /app/frontend && yarn add <pkg>` (mai npm)

## Ambiente

- `frontend/.env`
  - `REACT_APP_BACKEND_URL`
  - `VITE_BACKEND_URL`
- `backend/.env`
  - `MONGO_URL`, `DB_NAME=Gestionale`
  - credenziali PEC / Gmail / OpenAPI

Non rimuovere le variabili protette (`MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL`).

## Log utili

```bash
tail -n 100 /var/log/supervisor/backend.err.log
tail -n 100 /var/log/supervisor/frontend.err.log
```

## Licenza

Uso interno Ceraldi Group S.R.L. Tutti i diritti riservati.

<!-- deploy trigger 10:38:38 -->
