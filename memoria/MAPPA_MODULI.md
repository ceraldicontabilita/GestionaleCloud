# GestionaleCloud — Mappa dei moduli

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Mappa narrativa del repository canonico. Per l'elenco meccanico dei router e
degli endpoint usare `MAPPA_ROUTER.md`, `MAPPA_ENDPOINT_COMPLETA.md` e
`ENDPOINT_CLASSIFICAZIONE_FINALE.md`, rigenerati dagli script in `scripts/`.

Non esiste più una mappa delle collezioni come documento operativo: il
contratto dati è il registro Drive/Sheets definito in
`app/services/google_sheets_ledger.py`.

## Albero applicativo

```text
GestionaleCloud
├── Dashboard
├── Documenti
│   ├── Import manuale
│   ├── Drive e indice documentale
│   ├── Email/Gmail
│   └── Elaborazioni e anomalie
├── Fatture
│   ├── Ricevute/emesse
│   ├── Fornitori
│   ├── Scadenze e pagamenti
│   └── Documenti e associazioni
├── Prima Nota
│   ├── Cassa
│   ├── Banca
│   ├── Corrispettivi/POS/SumUp
│   └── Pulizia e controllo coerenza
├── Riconciliazione
│   ├── Estratti conto
│   ├── Bonifici e assegni
│   ├── PayPal
│   ├── F24/quietanze
│   └── Registro relazioni
├── Fisco e contabilità
│   ├── IVA, ritenute e calendario fiscale
│   ├── Libro giornale/mastro
│   ├── Bilancio, cespiti e chiusura
│   └── Dichiarazioni e codici tributo
├── Personale
│   ├── Dipendenti
│   ├── Cedolini
│   └── Associazione bonifici/periodi
├── Flotta e PartenoPay
│   ├── Veicoli e contratti
│   ├── Targa ↔ driver
│   ├── Verbali e quietanze
│   └── Riepilogo costi
└── Amministrazione
    ├── Utenti e sicurezza
    ├── Configurazione Drive/Sheets
    ├── Integrazioni e scheduler
    └── Audit e diagnostica
```

## Backend

```text
app/
├── main.py                         bootstrap FastAPI
├── config.py                       configurazione ambiente
├── database.py                     selezione runtime dati
├── routers/                        API per dominio
├── services/                       logica, import, matching e integrazioni
│   ├── google_sheets_ledger.py     contratto registro Drive/Sheets
│   └── sheets_runtime_database.py  adapter asincrono del registro
├── models/                         modelli dati
└── middleware/                     sessione, sicurezza e osservabilità
```

I router non devono conoscere il supporto fisico. Accedono all'interfaccia del
database e ai servizi di dominio; nuovi flussi persistenti devono funzionare
con `DATA_BACKEND=sheets`.

## Frontend

```text
frontend/src/
├── App.jsx
├── components/
├── hooks/
├── lib/
└── pages/
```

Il catalogo delle schermate è `page_catalog.json`. Il design system è descritto
in `DESIGN.md` e implementato in `frontend/src/lib/utils.js`.

## Registro Drive/Sheets

Il workbook canonico ha un foglio per entità. Le righe condividono campi base
per progressivo, identità, relazione, provenienza, hash e payload. Le cartelle
Drive canoniche sono:

```text
REGISTRO DATI
PARTENOPAY
CODICI TRIBUTO
QUIETANZE
DICHIARAZIONI
```

L'elenco dei fogli e la loro corrispondenza col dominio sono versionati nel
codice, non duplicati in una mappa manuale soggetta a divergenza.

## Flussi trasversali

### Import

`fonte → hash/ID → deduplica → estrazione → fatto → relazioni → riepilogo`

### Riconciliazione

`documento/fattura ↔ gestore pagamento ↔ banca ↔ Prima Nota ↔ prova`

### Ambiguità

`più candidati → nessun collegamento definitivo → lista + scelta manuale`

### Pubblicazione

`test → diff/staging mirato → main → CI → deploy Render → verifica live`

## Fonti di dettaglio

- API: mappe generate in questa cartella.
- Regole di dominio: `../LOGICA_FUNZIONAMENTO.md`.
- Architettura/prodotto: `../README.md` e `../PRODUCT.md`.
- Stato dei documenti: `../docs/MARKDOWN_INVENTORY.md`.
