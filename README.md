# Ceraldi ERP

Gestionale web interno di Ceraldi Group S.R.L. (Napoli).
Unifica contabilità, ciclo passivo, prima nota, HR, magazzino, noleggio auto e
riconciliazione bancaria — con acquisizione automatica da PEC e Gmail.

Repository GitHub: `ceraldicontabilita/gestionale2`
Branch di riferimento: `main`

## Stack

- Frontend: React 18 + Vite (porta 3000) — design inline via `src/lib/utils.js`
- Backend: FastAPI + Motor async (porta 8001)
- Database: MongoDB Atlas, DB `Gestionale`
- Scheduler: APScheduler (PEC orario, Gmail 10 min)

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
├── app/                Codice applicativo backend (routers, services, models, parsers...)
├── frontend/           React + Vite
│   └── src/
│       ├── lib/utils.js        Design system unico (colori, spazi, bottoni, formatter)
│       ├── index.css           Stile globale (reset, componenti, mobile-safe)
│       ├── styles/             topnav.css · common.css · utilities.css
│       ├── components/         layout, UI comune, widget
│       └── pages/
│           ├── hub/            Hub multi-tab (Contabilità, Magazzino, Strumenti...)
│           └── *.jsx           Pagine singole
├── memoria/            Documentazione viva: PRD · INDEX · LOGICA_OPERATIVA
├── tests/              Test manuali e script di appoggio
├── uploads/            Cache allegati (XML, PDF) in fase di processing
└── README.md           Questo file
```

## Dove leggere la documentazione

- `memoria/PRD.md` — product requirements, stato implementazione, backlog
- `memoria/INDEX.md` — scheda rapida (stack, collection, route, regole critiche)
- `memoria/LOGICA_OPERATIVA.md` — funzionamento pagina per pagina

## Principi

1. I ricavi arrivano SOLO da `corrispettivi`. Le `invoices` sono costi.
2. Il metodo di pagamento di una fattura viene sempre dall'anagrafica del fornitore, mai dall'XML SDI.
3. Collezioni canoniche: `fornitori`, `dipendenti`, `warehouse_stocks` (non le loro controparti in inglese/legacy).
4. Design system: una sola fonte di verità in `src/lib/utils.js`. Niente Tailwind, niente Shadcn.
5. Full-frame e responsive: layout 100% width, niente `max-width` fisso, tabelle con wrapper scrollabile.

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
