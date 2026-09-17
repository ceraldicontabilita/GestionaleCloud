# GestionaleCloud — Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-18
storage_architecture: supabase
-->

Gestionale su misura di **Ceraldi Group S.r.l.** (bar e pasticceria, Napoli,
P.IVA 04523831214): contabilità, fatture, F24, banca, personale, HACCP e menu
digitale in un solo servizio.

Produzione: **https://gestionalecloud.onrender.com**

> Le regole di progetto stanno in **`CLAUDE.md`**, che è l'unica memoria del
> repository. Questo README spiega solo com'è fatto il servizio e come si
> lavora; se i due file si contraddicono, vince `CLAUDE.md`.

## Un solo servizio, quattro app

Un unico processo FastAPI (`app/main.py`) serve le API e i quattro frontend
compilati, dallo stesso host:

| App | Rotte | Backend | Frontend | Accesso |
| --- | --- | --- | --- | --- |
| ERP (contabilità) | `/`, `/api/*` | `app/` | `frontend/` (Vite) | login ERP |
| HR / AppDipendenti | `/hr`, `/hr/portale`, `/hr/api/*` | `app/hr/` | `frontend_hr/` (Vite) | nome + PIN personale |
| Menu | `/menu`, `/menu/admin`, `/menu/api/*` | `app/menu/` | `frontend_menu/` (CRA) | utente e password admin |
| Lotti (HACCP) | `/lotti`, `/lotti/api/*` | `app/lotti/` | `frontend_lotti/` (CRA) | PIN operatore |

HR, Menu e Lotti sono le app originali del gruppo **portate dentro così
com'erano**: ognuna con il proprio login, il proprio aspetto e i propri test.
Sono montate come sub-app FastAPI **prima** del catch-all della SPA dell'ERP,
altrimenti `/lotti/...` finirebbe nella SPA sbagliata.

## Dati

- **Supabase** è l'archivio unico (`DATA_BACKEND=supabase`): schemi
  `gestionale`, `hr`, `lotti`, `menu` e l'archivio in sola lettura
  `legacy_staging`.
- **Google Drive** conserva gli originali documentali (fatture, cedolini, F24,
  estratti conto) e li fa entrare dai canali `DA ELABORARE / ELABORATE /
  ERRORI`. Non è un database.
- Il runtime su Google Sheets esiste ancora nel codice solo come fallback di
  sviluppo.

## Lavorare in locale

```bash
pip install -r backend/requirements.txt
npm --prefix frontend install --include=dev --legacy-peer-deps
npm --prefix frontend run build     # compila l'ERP e, via scripts/build_frontends.sh --apps,
                                    # tutte le cartelle frontend_*/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Senza la build, `/hr`, `/menu` e `/lotti` rispondono solo con le API.

Test:

```bash
python -m pytest -q                 # suite backend, cartella tests/ per area
yarn --cwd frontend test            # test del frontend ERP
yarn --cwd frontend build
AUTH_SECRET=test python -m pytest app/lotti/tests   # test originali di Lotti
python -m pytest app/hr/tests                       # test originali di HR
```

I test sono raggruppati per area: `tests/banca`, `tests/contabilita`,
`tests/documenti`, `tests/fatture`, `tests/fiscale`, `tests/frontend`,
`tests/hr`, `tests/lotti`, `tests/menu`, `tests/noleggio`, `tests/runtime`.

## Configurazione e segreti

**Tutti i valori reali stanno nelle variabili d'ambiente di Render**, mai nel
repository: `render.yaml` le dichiara con `sync: false`. Le famiglie sono:

- archivio: `DATA_BACKEND`, `SUPABASE_URL` e il segreto runtime;
- sub-app: `LOTTI_*`, `MENU_*`, `HR_*` (ognuna ha il proprio progetto o schema,
  la propria chiave JWT e il proprio login);
- Drive: `GOOGLE_DRIVE_*_FOLDER_ID` per ogni canale, più le credenziali del
  service account;
- accessi: `PIN_HASH_ADMIN` (PIN amministratore unico delle quattro app),
  `CREDENTIALS_ENCRYPTION_KEY`;
- integrazioni: PayPal, SumUp, Telegram, posta.

`render.yaml` è il contratto versionato del servizio. La dashboard Render non
lo recepisce da sola: Build Command e Start Command vanno incollati a mano una
volta sola in Settings.

## Deploy

Render pubblica automaticamente da `main`. Health check: `/api/health`.
Il workflow `.github/workflows/produzione.yml` attende che la produzione serva
il bundle del commit, poi controlla salute e schermate; `ci.yml` esegue test
backend e frontend su ogni push e pull request.

## Struttura

```
app/            ERP: routers, services, engines, parsers   (+ hr/ lotti/ menu/)
frontend/       SPA dell'ERP (React 18, Vite, TanStack Query, Zustand, Radix)
frontend_hr/    frontend_lotti/    frontend_menu/    frontend_shared/
backend/        requirements.txt di produzione
scripts/        build dei frontend, smoke, audit, sincronizzazione RT locale
supabase/       migrazioni SQL applicate al progetto
tests/          suite backend, una cartella per area
page_catalog.json   catalogo delle 64 schermate dell'ERP, usato dai collaudi
CLAUDE.md       regole di progetto e stato attuale
```
