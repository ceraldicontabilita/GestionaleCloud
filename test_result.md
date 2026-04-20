# Ceraldi ERP — Test result log

Ultima sessione: Apr 2026 — refactoring grafico + mobile-safe.

## Ambiente al momento del test

- Backend: FastAPI su porta 8001 (Supervisor RUNNING)
- Frontend: Vite su porta 3000 (Supervisor RUNNING)
- DB: MongoDB Atlas `Gestionale` (connesso)
- Backend health: `GET /api/health` → 200

## Verifiche eseguite in questa sessione

### Setup backend
- Installati i pacchetti Python mancanti: `lxml`, `primp`
- Supervisor `restart backend` → avvio pulito, "Application startup complete"
- `curl http://localhost:8001/api/health` → 200

### Refactoring grafico
Pagine verificate visivamente (desktop 1920×900):
- `/` Dashboard → OK, stile uniforme, dati coerenti
- `/fatture` → OK, 372 fatture, filtri compatti, tabella leggibile
- `/prima-nota` → OK, bordo giallo warning provvisori
- `/fornitori` → OK, card grid responsive
- `/contabilita` → OK, 11 tab in barra uniforme
- `/strumenti` → OK, 4 tab, sub-tab leggibili
- `/riconciliazione/assegni` → OK, 220 assegni per carnet
- `/dati-provvisori` → OK, utility CSS vanilla funziona
- `/magazzino` → OK

### Mobile responsiveness (viewport 390×844)
- Overflow orizzontale: verificato con `document.body.scrollWidth === window.innerWidth`
- Dashboard → nessun overflow ✓
- Fatture → nessun overflow ✓ (filtri e select full-width)
- Prima Nota → nessun overflow ✓
- Contabilità → nessun overflow ✓ (tab bar con scroll orizzontale interno)
- Fornitori → nessun overflow ✓ (KPI a 1 colonna)
- Assegni → nessun overflow ✓
- Magazzino → nessun overflow ✓
- TopNav su mobile: link principali nascosti, resta brand + anno + notifiche + avatar
- Mobile bottom nav (Home / Fatture / Banca / HR / Menu) visibile solo <768px

### Lint
- `src/lib/utils.js` → ESLint OK
- `src/pages/hub/*.jsx` → ESLint OK
- `src/components/layout/TopNav.jsx` → ESLint OK

## Azioni pianificate

Nessuna azione pendente bloccante. Possibili miglioramenti futuri:
- Tema scuro opzionale (CSS variables già pronte in index.css)
- Rimozione fisica dei pacchetti `tailwindcss`, `@tailwindcss/postcss`, `tailwindcss-animate` dal `package.json` (oggi presenti ma inerti)
- Ulteriore consolidamento di `src/styles.css` e `styles/common.css` in un unico file

## Note

Nessuna verifica automatizzata via testing agent in questa sessione: il refactoring
è stato solo grafico/CSS. Tutte le funzionalità backend/business non sono state
toccate; verifica visuale page-per-page considerata sufficiente.
