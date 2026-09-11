# GestionaleCloud — Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-11
storage_architecture: supabase-runtime-drive-originals
-->

ERP interno di Ceraldi Group S.R.L. per documenti, fatture, fornitori, Prima
Nota, riconciliazioni, fisco, personale e flotta.

La specifica normativa unica, completa e atomica è [`PROMPT_MASTER.md`](PROMPT_MASTER.md).
Gli altri documenti sono guide di lettura, riferimenti di dominio o mappe generate.

- Produzione: [impresasemplice.online](https://impresasemplice.online)
- Repository: `ceraldicontabilita/GestionaleCloud`
- Branch operativo: `main`
- Catalogo UI: 65 schermate in `page_catalog.json`

## Stato aggiornato all'11/09/2026

La produzione usa `DATA_BACKEND=supabase`: Supabase è il registro operativo
strutturato e Google Drive conserva gli originali documentali. Il runtime
Google Sheets resta nel repository esclusivamente come percorso transitorio di
rollback/test durante il completamento del cutover e non deve essere esteso a
nuovi flussi applicativi.

Il passaggio dei dati storici si considera concluso soltanto dopo confronto di
conteggi e hash, ricostruzione completa e prova di scrittura. Fino a quella
verifica non cancellare dati storici senza autorizzazione e checklist di cutover approvata.

## Architettura

```text
Browser React/Vite
  -> API FastAPI same-origin
     -> servizi di dominio e motore unico Prima Nota
        -> registro operativo: Supabase

Google Drive / Gmail autorizzato / API esterne
  -> import, parser, deduplica, identità canonica
     -> Supabase (dati strutturati)
     -> Google Drive (originali documentali)
```

## Fonti dati operative

Le schermate e i servizi non leggono direttamente il repository o archivi
locali come fonte di verità. I dati arrivano da questi canali:

| Dominio | Fonti primarie | Regole di acquisizione |
|---|---|---|
| Documenti | upload manuale, cartelle Drive configurate, allegati email autorizzati, API dei gestori | conserva l'originale, calcola hash, deduplica per identità canonica, registra provenienza |
| Fatture e fornitori | XML/P7M da Drive/SDI, anagrafiche fornitore, alias normalizzati | la P.IVA o il codice fiscale identificano il fornitore; il nome da solo non crea duplicati |
| Prima Nota | import da fatture, corrispettivi, banca, versamenti contanti, POS, cedolini, F24 | una scrittura nasce solo da un fatto di dominio e mantiene il proprio `operation_id` |
| Banca e riconciliazioni | estratti conto, movimenti bancari, CRO/TRN, descrizioni normalizzate | i movimenti riconciliano prove esistenti; non sostituiscono i documenti originali |
| Fisco e quietanze | modelli F24, codici tributo, quietanze, dichiarazioni, archivi Drive dedicati | F24, quietanza e movimento bancario restano prove distinte |
| Flotta e verbali | email autorizzate, verbali PDF, ZIP, contratti, storico assegnazioni veicolo | la targa normalizzata e la data/ora guidano l'associazione; i casi ambigui restano manuali |
| Corrispettivi e POS | XML RT, chiusure terminale, accrediti gestore, commissioni | il ricavo nasce dal corrispettivo RT; l'accredito POS è un fatto successivo e separato |
| Amministrazione e audit | configurazione Render, cataloghi, log, inventory e report storici | usati per governo e tracciabilità, non come dato operativo primario |

### Stack

- Backend: Python 3.12, FastAPI, runtime documentale Supabase, APScheduler.
- Frontend: React 18, Vite 5, React Router 6, TanStack Query, Zustand.
- Persistenza: Supabase per i dati strutturati; Google Drive per gli originali.
- Compatibilità transitoria: runtime Google Sheets solo per rollback/test.
- Deploy: un servizio Render avviato con `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- CI: pytest, Vitest, build Vite, audit statici, runtime smoke ed E2E isolato.

## Avvio locale

Prerequisiti: Python 3.12, Node.js e Yarn.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
yarn --cwd frontend install --frozen-lockfile
```

Configurare le variabili in un ambiente locale non versionato. Per una prova
isolata non usare credenziali o dati di produzione.

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
yarn --cwd frontend dev
```

Se l'entrypoint applicativo cambia, il riferimento definitivo è il comando di
avvio in `render.yaml` e il lifecycle importato dai test correnti.

## Configurazione essenziale

### Applicazione

- `ENVIRONMENT`
- `SECRET_KEY`
- `CORS_ALLOWED_ORIGINS`
- `CREDENTIALS_ENCRYPTION_KEY`

### Registro Supabase

In produzione impostare esplicitamente:

- `DATA_BACKEND=supabase`
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_RUNTIME_SECRET`

La publishable key non è sufficiente ad accedere alle RPC privilegiate: il
runtime server-to-server usa anche `SUPABASE_RUNTIME_SECRET`, conservato nel
secret store e mai nel frontend.

### Google Drive

Google Drive conserva gli originali e le prove documentali. Le credenziali e
gli ID delle cartelle operative restano nelle variabili d'ambiente del deploy.
Una sola variabile canonica `GOOGLE_DRIVE_<AREA>_FOLDER_ID` deve rappresentare
ciascuna area documentale.

### Compatibilità Google Sheets

`GOOGLE_SHEETS_LEDGER_ID`, `GOOGLE_SHEETS_LEDGER_FOLDER_ID` e il runtime Sheets
sono mantenuti soltanto per rollback/test durante il cutover. Non introdurre
nuove dipendenze applicative da Sheets.

## Verifica cutover Supabase

La rimozione definitiva del fallback Sheets è ammessa soltanto dopo:

1. inventario delle collezioni;
2. deduplica per `canonical_id`, `_id` e chiavi idempotenti;
3. blocco dei conflitti ID uguale/payload diverso;
4. confronto dei conteggi tra sorgente e Supabase;
5. confronto dei digest per collezione;
6. prova di lettura e scrittura idempotente sul runtime Supabase;
7. verifica live del commit in produzione;
8. assenza dimostrata di chiamanti che richiedano ancora il runtime Sheets.

I documenti originali su Drive non vengono eliminati dalla migrazione del
registro.

## Albero del repository

```text
app/
├── routers/                    API FastAPI per dominio
├── services/                   logica condivisa e riconciliazioni
├── parsers/                    XML, PDF, CSV e formati fiscali
├── knowledge/                  base di conoscenza della chat
├── config.py                   configurazione e feature flag
└── database.py                 selezione runtime Supabase/compatibilità Sheets
backend/
└── requirements.txt
frontend/
├── src/main.jsx                router principale
├── src/pages/                  schermate
├── src/pages/hub/              alberi di navigazione per modulo
├── src/components/             modali e componenti condivisi
└── package.json
gestionale_mcp/                 gateway AI di sola lettura
prompts/                        contratti operativi versionati per l'AI
scripts/                        audit, mappe e manutenzione verificabile
tests/                          test backend e guardie architetturali
memoria/                        specifiche e mappe tecniche
page_catalog.json               catalogo macchina delle 65 pagine
CLAUDE.md                       istruzioni operative per gli agenti
PRODUCT.md                      obiettivi e confini del prodotto
```

## Moduli applicativi

- Dashboard e inserimento rapido
- Fatture, corrispettivi e fornitori
- Prima Nota Cassa/Banca, salari e ritenute
- Flotta, verbali e costi noleggio
- Contabilità, bilancio, IVA, F24 e situazione fiscale
- Riconciliazione banca, bonifici, assegni, PayPal, PagoPA e POS
- Import, archivio e indice documentale Drive
- Strumenti, integrazioni, agenti e amministrazione

Nel catalogo corrente la logica di coerenza POS vive nella pagina 40
(`Riconciliazione > Coerenza POS`); le elaborazioni amministrative e legacy
sono le pagine 56 e 57 nell'area Admin.

L'elenco completo e verificabile delle route è in `page_catalog.json`.

## Regole dati fondamentali

1. `canonical_id` identifica l'entità; `operation_id` collega le prove della
   stessa operazione.
2. Stesso hash/identità non crea un duplicato.
3. L'importo da solo non autorizza un'associazione.
4. Fattura, quietanza e movimento bancario restano entità distinte.
5. I ricavi provengono dai corrispettivi, non dagli accrediti POS.
6. Le scritture di Prima Nota passano da
   `app/services/scritture_contabili.py`.
7. I documenti originali sono immutabili e tracciati con fonte e hash.
8. Una proposta AI o una confidence elevata non sostituisce una prova di dominio.

## Test

```powershell
python -m pytest -q
yarn --cwd frontend test
yarn --cwd frontend build
python scripts\audit_static.py
git diff --check
```

Test mirati della persistenza:

```powershell
python -m pytest tests\test_startup_safety.py tests\test_storage_architecture_contract.py -q
```

I test del runtime Sheets restano test di compatibilità finché il percorso di
rollback non viene rimosso esplicitamente.

## Deploy

`render.yaml` documenta il servizio Render con auto-deploy da `main`. Prima
di considerare pubblicata una modifica:

1. CI verde;
2. `HEAD == origin/main`;
3. `/api/health` deve riportare il commit atteso;
4. controllo live del flusso interessato.

## Documentazione

- `PROMPT_MASTER.md` — autorità normativa di prodotto e dominio.
- `docs/AI_GOVERNANCE.md` — regole per AI, evidenze e automazioni.
- `AGENTS.md` — istruzioni repository per agenti di sviluppo.
- `CLAUDE.md` — regole operative storiche da mantenere allineate.
- `PRODUCT.md` — visione, flussi e albero funzionale.
- `LOGICA_FUNZIONAMENTO.md` — comportamento operativo per gli utenti.
- `page_catalog.json` — route/componenti/accessi/stato audit.

## Licenza

Uso interno Ceraldi Group S.R.L. Tutti i diritti riservati.
