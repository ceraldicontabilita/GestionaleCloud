# Inventario Markdown — GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Inventario rigenerato il 2026-08-20 da `scripts/refresh_markdown_docs.py`.
Classifica i documenti senza riscrivere gli artefatti prodotti da altri script.

## Significato degli stati

| Stato | Significato |
|---|---|
| `current` | Descrive il comportamento o le regole operative correnti. |
| `reference` | Approfondimento di dominio; l'architettura corrente prevale. |
| `generated` | Output di uno script, da non modificare manualmente. |

## Riepilogo

- Correnti: **17**
- Riferimento: **25**
- Generati: **5**
- Totale: **47**

## Elenco completo

| File | Stato | Uso |
|---|---|---|
| `.github/copilot-instructions.md` | `current` | Guida corrente subordinata al Prompt Master |
| `CLAUDE.md` | `current` | Guida corrente subordinata al Prompt Master |
| `DESIGN.md` | `current` | Guida corrente subordinata al Prompt Master |
| `LOGICA_FUNZIONAMENTO.md` | `current` | Guida corrente subordinata al Prompt Master |
| `PRODUCT.md` | `current` | Guida corrente subordinata al Prompt Master |
| `PROMPT_MASTER.md` | `current` | Unica specifica normativa e atomica |
| `README.md` | `current` | Guida corrente subordinata al Prompt Master |
| `docs/FISCAL_ACCOUNTING_POLICY.md` | `current` | Guida corrente subordinata al Prompt Master |
| `docs/MARKDOWN_INVENTORY.md` | `current` | Guida corrente subordinata al Prompt Master |
| `docs/MCP_GESTIONALE_RUNBOOK.md` | `current` | Guida corrente subordinata al Prompt Master |
| `docs/MCP_GESTIONALE_SPEC.md` | `current` | Guida corrente subordinata al Prompt Master |
| `docs/rt-locale-drive.md` | `current` | Guida corrente subordinata al Prompt Master |
| `frontend/README.md` | `current` | Guida corrente subordinata al Prompt Master |
| `memoria/AUDIT_FRONTEND_DEAD_CODE.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/AUDIT_STATIC_REPORT.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/DISASTER_RECOVERY_DRIVE.md` | `current` | Guida corrente subordinata al Prompt Master |
| `memoria/DRIVE_ESTRATTI_CONTO.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/FORNITORI_REGOLA_CANONICA.md` | `current` | Guida corrente subordinata al Prompt Master |
| `memoria/INDEX.md` | `current` | Guida corrente subordinata al Prompt Master |
| `memoria/LOGICA_LIBRO_MASTRO.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/MAPPA_ENDPOINT_COMPLETA.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/MAPPA_MODULI.md` | `current` | Guida corrente subordinata al Prompt Master |
| `memoria/MAPPA_ROUTER.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/SPECIFICA_IVA.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/01-prima-nota.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/02-contabilita.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/03-fatture-fornitori.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/04-banca-riconciliazione.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/05-f24.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/06-documenti-email-ai.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/07-hr-noleggio-verbali.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/08-sistema-admin.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/endpoints/README.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/CEDOLINI.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/DIPENDENTI.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/DOCUMENTI_INBOX.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/F24.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/FATTURE_RICEVUTE.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/FORNITORI.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/MAGAZZINO.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/PRIMA_NOTA_BANCA.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/PRIMA_NOTA_CASSA.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/README.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |
| `memoria/moduli/RICONCILIAZIONE.md` | `reference` | Dettaglio di dominio subordinato al Prompt Master |

## Regola architetturale

La specifica normativa unica è `PROMPT_MASTER.md`. La destinazione è
Drive-only: originali in Google Drive e registri in Google Sheets/Excel
collegato a Drive. Audit, piani e porting datati non restano nel repository:
la loro storia è già conservata da Git.
