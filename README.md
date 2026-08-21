# GestionaleCloud — Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

ERP interno di Ceraldi Group S.R.L. per documenti, fatture, fornitori, Prima
Nota, riconciliazioni, fisco, personale e flotta.

La specifica normativa unica, completa e atomica è [`PROMPT_MASTER.md`](PROMPT_MASTER.md).
Gli altri documenti sono guide di lettura, riferimenti di dominio o mappe generate.

- Produzione: [impresasemplice.online](https://impresasemplice.online)
- Repository: `ceraldicontabilita/GestionaleCloud`
- Branch operativo: `main`
- Catalogo UI: 65 schermate in `page_catalog.json`

## Stato aggiornato al 20/08/2026

Il repository usa `DATA_BACKEND=sheets` come backend operativo: Google Sheets è il registro operativo e Drive conserva gli originali. In produzione configurare esplicitamente il registro o la cartella Drive del ledger.
Non esiste fallback di persistenza: Drive/Sheets è l'unico archivio operativo.

Il passaggio dei dati storici si considera concluso soltanto dopo confronto di
conteggi e hash, ricostruzione completa e prova di scrittura. Fino a quella
verifica non cancellare dati storici senza autorizzazione e checklist di cutover approvata.

Il registro Drive crea questa struttura:

```text
REGISTRO DATI/
PARTENOPAY/
CODICI TRIBUTO/
QUIETANZE/
DICHIARAZIONI/
```

## Architettura

```text
Browser React/Vite
  -> API FastAPI same-origin
     -> servizi di dominio e motore unico Prima Nota
        -> backend dati: Google Sheets/Drive (registri operativi)

Google Drive / Gmail autorizzato / API esterne
  -> import, parser, deduplica, identità canonica
     -> fatture, F24, quietanze, banca, PartenoPay, cedolini
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

- Backend: Python 3.12, FastAPI, archivio asincrono Sheets, APScheduler.
- Frontend: React 18, Vite 5, React Router 6, TanStack Query, Zustand.
- Persistenza: Google Sheets per i registri e Google Drive per gli originali.
- Deploy: un servizio Render avviato con `python -m app.process_supervisor`.
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
- `SHEETS_REGISTRY_NAME`
- `CREDENTIALS_ENCRYPTION_KEY`

### Registro Google Sheets/Drive

- `GOOGLE_SHEETS_LEDGER_ID` oppure `GOOGLE_SHEETS_LEDGER_FOLDER_ID`
- Le collezioni operative non ancora presenti nel manifest iniziale ricevono
  al primo inserimento un foglio privato `DB_*`.
- L'import fatture usa `DRIVE_FATTURE_BATCH_SIZE` (default 1) e viene eseguito
  ogni 15 minuti, così l'arretrato non satura la memoria del servizio web.
- `GOOGLE_DRIVE_SA_JSON` / `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
- una sola variabile canonica `GOOGLE_DRIVE_<AREA>_FOLDER_ID` per ciascuna
  area documentale; non creare alias Render diversi per lo stesso folder ID

Il foglio privato `_INDICE_DRIVE` del registro elenca le cartelle canoniche e,
per le aree operative, i tre stati `Da elaborare`, `Elaborate` ed `Errori`.
Codice e automazioni consultano quell'indice e `DRIVE_FOLDER_REGISTRY_JSON`;
gli ID aziendali non devono essere copiati nella documentazione pubblica.

Le credenziali restano nel secret store di Render. Non inserire JSON di
service account, token o password nel repository.

## Verifica Drive/Sheets

La procedura amministrativa deve essere eseguita in quest'ordine:

1. inventario dei registri;
2. deduplica per `canonical_id` e hash del payload;
3. blocco dei conflitti ID uguale/payload diverso;
4. sincronizzazione completa nel registro Sheets;
5. confronto di conteggi e digest per ogni foglio;
6. ricostruzione del runtime dai fogli e prova di scrittura;
7. verifica live del commit in produzione;
8. conferma dell'assenza di backend alternativi e variabili obsolete.

I documenti originali su Drive non vengono spostati o eliminati dalla
migrazione del registro.

## Albero del repository

```text
app/
├── routers/                    API FastAPI per dominio
├── services/                   logica condivisa e riconciliazioni
├── parsers/                    XML, PDF, CSV e formati fiscali
├── knowledge/                  base di conoscenza della chat
├── config.py                   configurazione e feature flag
└── database.py                 inizializzazione archivio Drive/Sheets
backend/
└── requirements.txt
frontend/
├── src/main.jsx                router principale
├── src/pages/                  schermate
├── src/pages/hub/              alberi di navigazione per modulo
├── src/components/             modali e componenti condivisi
└── package.json
gestionale_mcp/                 gateway AI di sola lettura
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

## Test

```powershell
python -m pytest -q
yarn --cwd frontend test
yarn --cwd frontend build
python scripts\audit_static.py
git diff --check
```

Test mirati del catalogo e del registro Drive:

```powershell
python -m pytest tests\test_page_catalog.py -q
python -m pytest tests\test_google_sheets_ledger.py tests\test_sheets_runtime_database.py -q
```

## Deploy

`render.yaml` documenta il servizio Render con auto-deploy da `main`. Prima
di considerare pubblicata una modifica:

1. CI verde;
2. `HEAD == origin/main`;
3. `/api/health` deve riportare il commit atteso;
4. controllo live del flusso interessato.

## Documentazione

- `PROMPT_MASTER.md` — unica autorità normativa: prodotto, dati, Gmail, Drive,
  variabili, pagine, router, endpoint, divieti e gate.
- `CLAUDE.md` — regole vincolanti per lavorare nel repository.
- `PRODUCT.md` — visione, flussi e albero funzionale.
- `LOGICA_FUNZIONAMENTO.md` — comportamento operativo per gli utenti.
- `page_catalog.json` — route/componenti/accessi/stato audit.
- `memoria/JSON_INVENTORY.json` — inventario e politica dei file JSON.
- `memoria/pagine/*.json` — mappe tecniche delle pagine.
- `memoria/popup/*.json` — mappe tecniche dei popup.

### Kit completo per la ricostruzione pulita

Per generare un unico ZIP autosufficiente con Prompt Master, architettura,
65 schede Markdown e 65 contratti JSON con la logica specifica di ogni pagina,
36 popup, contratti API, variabili senza segreti,
modello Drive/Sheets e matrice di accettazione:

```powershell
python scripts\genera_kit_ricostruzione.py
```

Il comando crea in `Documents`:

- `GestionaleCloud_REBUILD_KIT_2026-08-20.zip`;
- `GestionaleCloud_REBUILD_KIT_2026-08-20.zip.sha256`.

Il generatore verifica una sola cartella radice, manifest e hash interni,
conteggi canonici e firme compatibili con credenziali. Lo ZIP non viene
versionato: non contiene dati aziendali, allegati, segreti o una copia del
codice applicativo; viene rigenerato dalle fonti correnti del repository.

## Licenza

Uso interno Ceraldi Group S.R.L. Tutti i diritti riservati.
