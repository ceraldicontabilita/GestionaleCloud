# GestionaleCloud — Indice tecnico rapido

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

- Repository canonico: `ceraldicontabilita/GestionaleCloud`
- Produzione: `https://impresasemplice.online`
- Branch operativo: `main`

## Architettura

| Livello | Tecnologia/fonte |
|---|---|
| Frontend | React 18 + Vite 5 |
| Backend | FastAPI asincrono |
| Originali | Google Drive |
| Registro operativo di destinazione | Supabase (`gestionale.documents` + `gestionale.blobs`) |
| Fallback di sviluppo | Google Sheets/Excel collegato a Drive (non produzione) |
| Compatibilità transitoria | Nessuna — legacy DB rimosso |
| Deploy | Render, `render.yaml` |

Il backend di persistenza è selezionato da `DATA_BACKEND`. In produzione è
`supabase` (decisione del 03/09/2026); `sheets` resta il default del codice
solo per sviluppo/test. legacy DB non è più supportato e ogni variabile o
script legato a legacy DB è deprecato e non deve essere usato.

## Documenti correnti

| Documento | Scopo |
|---|---|
| `../README.md` | Installazione, architettura, test e deploy |
| `../CLAUDE.md` | Unico documento normativo (dal 17/09/2026): regole, prodotto, design, logica, regola delle attese, fornitori, mappa moduli, cedolini, policy fiscale, MCP, runbook Render/RT, disaster recovery |
| `../docs/MARKDOWN_INVENTORY.md` | Stato e autorità di tutti i Markdown residui |
| `DRIVE_ESTRATTI_CONTO.md` | Regole del canale estratti conto |
| `LOGICA_LIBRO_MASTRO.md` | Regole del libro mastro |
| `SPECIFICA_IVA.md` | Regole IVA |
| `SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` | Specifiche fiscali/personale di dettaglio |

## Artefatti generati

Non modificare manualmente:

- `MAPPA_ROUTER.md`
- `MAPPA_ENDPOINT_COMPLETA.md`
- `ENDPOINT_CLASSIFICAZIONE_FINALE.md`
- `AUDIT_FRONTEND_DEAD_CODE.md`
- `AUDIT_STATIC_REPORT.md`

Lo script di rigenerazione è indicato nell'header del relativo file. I report
datati sono prove storiche, non istruzioni correnti.

## Regole non negoziabili

- originali mai eliminati o spostati automaticamente;
- import idempotenti e deduplicazione prima della scrittura;
- progressivo per foglio, `canonical_id`, `operation_id`, hash e provenienza;
- fattura, quietanza, banca e Prima Nota restano fatti distinti;
- associazioni definitive automatiche solo quando univoche;
- importo uguale non prova identità;
- ogni alert apre la lista dei record;
- nessuna dismissione Drive/Supabase prima del cutover verificato.

## Verifica

Per una release documentare test, build, CI, commit pubblicato e prova live.
Un report statico o un HTTP 200 non sostituisce il controllo dei dati e delle
relazioni.
