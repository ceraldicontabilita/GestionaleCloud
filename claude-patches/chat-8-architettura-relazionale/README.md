# Ceraldi ERP

Gestionale web interno di Ceraldi Group S.R.L. (Napoli).
Unifica contabilità, ciclo passivo, prima nota, HR, magazzino, noleggio auto,
riconciliazione bancaria e tracciabilità HACCP — con acquisizione automatica
da PEC e Gmail e sistema relazionale a eventi.

Repository GitHub: `ceraldicontabilita/gestionale2`
Branch di riferimento: `main`

## Stack

- Frontend: React 18 + Vite (porta 3000) — design inline via `src/lib/utils.js`
- Backend: FastAPI + Motor async (porta 8001)
- Database: MongoDB Atlas, DB `Gestionale`, cluster `cluster0.vofh7iz`
- Scheduler: APScheduler (PEC orario, Gmail 10 min)
- Servizi core: `app/services/` — event bus, alert engine, riconciliazione, partite aperte

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

```
/app
├── backend/            Entry point FastAPI (server.py) + .env
├── app/                Codice applicativo backend
│   ├── routers/        Router FastAPI organizzati per modulo
│   ├── services/       Servizi core condivisi (event bus, alert, audit, deduplica,
│   │                   partite aperte, riconciliazione engine)
│   ├── models/         Modelli dati e stati
│   ├── parsers/        Parser XML, PDF (Zucchetti, F24, verbali)
│   ├── database.py     Connessione MongoDB + indici
│   └── db_collections.py  Nomi collezioni (fonte di verità)
├── frontend/           React + Vite
│   └── src/
│       ├── lib/utils.js        Design system unico (colori, spazi, bottoni, formatter)
│       ├── index.css           Stile globale (reset, componenti, mobile-safe)
│       ├── styles/             topnav.css · common.css · utilities.css
│       ├── components/         layout, UI comune, widget
│       └── pages/
│           ├── hub/            Hub multi-tab (Contabilità, Magazzino, Strumenti...)
│           ├── hr/             HR: Dipendenti, Cedolini, Presenze, TFR
│           └── *.jsx           Pagine singole
├── memoria/            Documentazione viva: PRD · INDEX · LOGICA_OPERATIVA · BACKLOG
├── claude-patches/     Patch di sviluppo da Claude (chat-N-descrizione/)
├── PIANO_LAVORO_RELAZIONALE.md   Architettura relazionale completa
├── DIARIO.md           Cronologia sviluppo per chat
└── README.md           Questo file
```

## Dove leggere la documentazione

- `memoria/INDEX.md` — scheda rapida (stack, collections, route, regole critiche)
- `memoria/PRD.md` — product requirements, stato implementazione, backlog
- `memoria/LOGICA_OPERATIVA.md` — funzionamento pagina per pagina
- `memoria/BACKLOG.md` — backlog operativo con priorità
- `PIANO_LAVORO_RELAZIONALE.md` — architettura relazionale, catalogo alert, piano 8 fasi

## Architettura relazionale

Il gestionale usa un sistema a eventi sincroni per far comunicare i moduli.
Quando un'entità cambia stato, il cambio si propaga automaticamente:

```
Fattura XML → crea/aggiorna Fornitore → crea Partita Aperta → genera Alert se incompleta
Movimento Banca → cerca Match con Partite → Riconcilia → aggiorna Fattura/F24/Stipendio
Cedolino importato → aggiorna Dipendente → crea Prima Nota Salari → crea Partita Stipendio
```

I servizi core in `app/services/`:
- `event_bus.py` — dispatcher eventi sincrono tra moduli
- `alert_engine.py` — 48 codici alert standardizzati con trigger e chiusura
- `audit_logger.py` — log unificato di ogni cambio stato
- `deduplica.py` — verifica duplicati per tutte le entità
- `partite_aperte_engine.py` — scadenziario materializzato
- `riconciliazione_engine.py` — scoring match a 4 livelli

## Principi

1. I ricavi arrivano SOLO da `corrispettivi`. Le `invoices` sono costi.
2. Il metodo di pagamento di una fattura viene sempre dall'anagrafica del fornitore, mai dall'XML SDI.
3. Collezioni canoniche: `fornitori`, `dipendenti`, `warehouse_inventory` (non le controparti legacy).
4. Design system: una sola fonte di verità in `src/lib/utils.js`. Niente Tailwind, niente Shadcn.
5. Full-frame e responsive: layout 100% width, niente `max-width` fisso, tabelle con wrapper scrollabile.
6. Nomi collezioni: importare sempre da `app/db_collections.py`, mai stringhe hardcoded.
7. Patch Claude: mai push diretto su main, sempre in `claude-patches/chat-N-descrizione/` con `ISTRUZIONI.md`.
8. Ogni operazione CRUD significativa chiama `propagate_event()` per aggiornare i moduli collegati.

## Package management

- Python: `pip install <pkg> && pip freeze > /app/backend/requirements.txt`
- Node: `cd /app/frontend && yarn add <pkg>` (mai npm)

## Ambiente

- `frontend/.env`
  - `REACT_APP_BACKEND_URL` (URL pubblico di preview)
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
