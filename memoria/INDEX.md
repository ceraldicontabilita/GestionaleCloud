# GestionaleCloud — Indice tecnico rapido

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
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
| Registro operativo di destinazione | Google Sheets/Excel collegato a Drive |
| Compatibilità transitoria | MongoDB, solo fino al cutover Drive/Sheets verificato |
| Deploy | Render, `render.yaml` |

Il backend di persistenza è selezionato da `DATA_BACKEND`. La destinazione è
`sheets`; il default del codice resta temporaneamente `mongodb` finché copia,
ricostruzione, scrittura e verifica end-to-end non sono concluse.

## Documenti correnti

| Documento | Scopo |
|---|---|
| `../README.md` | Installazione, architettura, test e deploy |
| `../PRODUCT.md` | Prodotto e albero funzionale |
| `../CLAUDE.md` | Regole operative per gli agenti |
| `../DESIGN.md` | Design system UI |
| `../LOGICA_FUNZIONAMENTO.md` | Regole di dominio e flussi end-to-end |
| `../docs/MARKDOWN_INVENTORY.md` | Stato e autorità di tutti i Markdown |
| `MAPPA_MODULI.md` | Mappa dei moduli applicativi |
| `DISASTER_RECOVERY_DRIVE.md` | Backup, ricostruzione e ripristino Drive-only |
| `DRIVE_ESTRATTI_CONTO.md` | Regole del canale estratti conto |
| `FORNITORI_REGOLA_CANONICA.md` | Identità anagrafica fornitori |
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
- nessuna dismissione MongoDB prima del cutover Drive/Sheets verificato.

## Verifica

Per una release documentare test, build, CI, commit pubblicato e prova live.
Un report statico o un HTTP 200 non sostituisce il controllo dei dati e delle
relazioni.
