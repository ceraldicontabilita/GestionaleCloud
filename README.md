# GestionaleCloud — Ceraldi ERP

Gestionale su misura di **Ceraldi Group S.r.l.** (bar e pasticceria, Napoli, P.IVA 04523831214): contabilità, fatture, F24, banca, personale, HACCP e menu digitale in un solo servizio.

Produzione: **https://gestionalecloud.onrender.com**

> Le regole di progetto stanno in **`CLAUDE.md`**, che è l'unica memoria del repository. Questo README spiega solo com'è fatto il servizio e come si lavora; se i due file si contraddicono, vince `CLAUDE.md`.

## Un solo servizio, quattro app

Un unico processo FastAPI (`app/main.py`) serve le API e i quattro frontend compilati, dallo stesso host:

| App | Rotte | Backend | Frontend | Accesso |
| --- | --- | --- | --- | --- |
| ERP (contabilità) | `/`, `/api/*` | `app/` | `frontend/` (Vite) | login ERP |
| HR / AppDipendenti | `/hr`, `/hr/portale`, `/hr/api/*` | `app/hr/` | `frontend_hr/` (Vite) | nome + PIN personale |
| Menu | `/menu`, `/menu/admin`, `/menu/api/*` | `app/menu/` | `frontend_menu/` (CRA) | utente e password admin |
| Lotti (HACCP) | `/lotti`, `/lotti/api/*` | `app/lotti/` | `frontend_lotti/` (CRA) | PIN operatore |

Il codice Python sta in **`app/`**. **`backend/`** contiene solo `requirements.txt` di produzione.

HR, Menu e Lotti sono montate in `app/main.py` **prima** del catch-all `/{full_path:path}` della SPA ERP, in quest'ordine: `/lotti`, `/saima`, `/menu`, `/hr`, `/assets`, poi la SPA. Controllato su `main`: l'ordine è quello.

## Dati

- **Supabase** è l'archivio unico (`DATA_BACKEND=supabase`): schemi `gestionale`, `hr`, `lotti`, `menu` e l'archivio in sola lettura `legacy_staging`.
- **Google Drive** conserva gli originali documentali (fatture, cedolini, F24, estratti conto) e li fa entrare dai canali `DA ELABORARE / ELABORATE / ERRORI`. Non è un database.

## Lavorare in locale

Il frontend ERP ha **`yarn.lock`**. Install e test come la CI (`.github/workflows/ci.yml`), non con npm.

```bash
pip install -r backend/requirements.txt
yarn --cwd frontend install --frozen-lockfile
yarn --cwd frontend build     # compila l'ERP e, via scripts/build_frontends.sh --apps,
                              # tutte le cartelle frontend_*/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Senza la build, `/hr`, `/menu` e `/lotti` rispondono solo con le API.

Test:

```bash
python -m pytest -q                 # suite backend, cartella tests/ per area
yarn --cwd frontend test            # test del frontend ERP
AUTH_SECRET=test python -m pytest app/lotti/tests
python -m pytest tests/hr           # HR nella suite principale; i fixture sono lì
```

I test sono raggruppati per area: `tests/banca`, `tests/contabilita`, `tests/documenti`, `tests/fatture`, `tests/fiscale`, `tests/frontend`, `tests/hr`, `tests/lotti`, `tests/menu`, `tests/noleggio`, `tests/runtime`.

## Configurazione e segreti

**Tutti i valori reali stanno nelle variabili d'ambiente di Render**, mai nel repository: `render.yaml` le dichiara con `sync: false`.

`render.yaml` è il contratto versionato. La dashboard Render non lo applica da sola: Build Command e Start Command si incollano una volta in Settings. Dopo #709 il job live usa yarn + cache, allineato al lockfile.

## Deploy

Render pubblica automaticamente da `main`. Health check: `/api/health`. Il workflow `.github/workflows/produzione.yml` attende che la produzione serva il bundle del commit, poi controlla salute e schermate; `ci.yml` esegue test backend e frontend su ogni push e pull request.

## Struttura

```
app/            codice Python: routers, services, engines + hr/ lotti/ menu/
frontend/       SPA ERP (React 18, Vite) — lockfile: yarn.lock
frontend_hr/    frontend_lotti/    frontend_menu/    frontend_shared/
backend/        solo requirements.txt di produzione
scripts/        build frontend, smoke, audit
supabase/       migrazioni SQL
tests/          suite backend per area
page_catalog.json
CLAUDE.md
```
