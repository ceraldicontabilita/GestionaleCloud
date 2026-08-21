# Frontend GestionaleCloud / Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

Single-page application del repository
`ceraldicontabilita/GestionaleCloud`. In produzione viene compilata da Render
e servita dallo stesso servizio FastAPI di `impresasemplice.online`.

## Stack effettivo

- React 18 e React Router 6
- Vite 5
- TanStack Query 5
- Zustand per lo stato leggero
- Radix UI per i primitivi accessibili
- Recharts per i grafici
- Vitest e Testing Library

La lista completa e le versioni sono in `frontend/package.json`.

## Comandi

Da radice repository:

```powershell
npm --prefix frontend install --include=dev --legacy-peer-deps
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run build
```

Il deploy usa la stessa build definita in `render.yaml`. Gli artefatti vengono
scritti in `frontend/dist`.

## Struttura essenziale

```text
frontend/src/
├── components/       componenti condivisi e navigazione
├── hooks/            hook di dominio e stato URL
├── lib/              client API, utilità e design token
├── pages/            schermate applicative
├── App.jsx            routing principale
└── main.jsx           bootstrap React
```

Il catalogo delle schermate è `page_catalog.json`. Le pagine legacy devono
essere ricondotte ai componenti condivisi, non replicate.

## Regole UI

- Seguire `DESIGN.md`; la fonte dei token è `src/lib/utils.js`.
- Non introdurre Tailwind né un secondo tema.
- Stato globale anno, filtri e selezione devono sopravvivere a refresh e link
  condivisi quando previsto.
- Alert e contatori devono mostrare i record che li generano.
- Le modali documento/fattura devono essere chiudibili, responsivi e sopra
  ogni altro overlay.
- Mostrare origine, ID operazione e prove collegate per riconciliazioni e
  scritture contabili.

## Dati

Il frontend non accede direttamente ad archivi. Interroga le API FastAPI, che
espongono il dominio senza accesso diretto alla persistenza. L'archivio
operativo è Drive/Sheets: originali in Google Drive e registri strutturati in
Google Sheets/Excel collegati a Drive. Non esistono fallback nei componenti.

Le informazioni mostrate nella UI derivano quindi da queste fonti:

- documenti e allegati indicizzati in Drive;
- email e allegati acquisiti dai mittenti autorizzati;
- importazioni di fatture, F24, quietanze, corrispettivi e movimenti bancari;
- anagrafiche, relazioni e stati calcolati dal backend;
- configurazione e cataloghi applicativi pubblicati dal repository.

Quando una vista mostra un alert, un contatore o una riconciliazione, deve
aprire i record che la compongono oppure esporre il collegamento alla prova
originaria.

## Verifica prima del commit

1. `npm --prefix frontend test`
2. `npm --prefix frontend run build`
3. prova dei flussi modificati con caricamento, vuoto, errore e dati reali
4. controllo responsive, tastiera, focus e chiusura modali
5. controllo del diff: non includere artefatti `dist` estranei alla modifica
