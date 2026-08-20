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
| `historical` | Audit, piano o fotografia datata, conservata come prova. |

## Riepilogo

- Correnti: **16**
- Riferimento: **25**
- Generati: **5**
- Storici: **18**
- Totale: **64**

## Elenco completo

| File | Stato | Uso |
|---|---|---|
| `.github/agents/mcp-gateway.agent.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `.github/agents/ogni-pagina.agent.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `.github/copilot-instructions.md` | `current` | Autorità operativa corrente |
| `.github/instructions/pagine-erp.instructions.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `.github/skills/mcp-gateway/SKILL.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `.github/skills/pagina-erp/SKILL.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `CLAUDE.md` | `current` | Autorità operativa corrente |
| `DESIGN.md` | `current` | Autorità operativa corrente |
| `LOGICA_FUNZIONAMENTO.md` | `current` | Autorità operativa corrente |
| `PRODUCT.md` | `current` | Autorità operativa corrente |
| `PROMPT_MASTER.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `README.md` | `current` | Autorità operativa corrente |
| `archive/legacy-audit/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/FISCAL_ACCOUNTING_POLICY.md` | `current` | Autorità operativa corrente |
| `docs/MARKDOWN_INVENTORY.md` | `current` | Autorità operativa corrente |
| `docs/MCP_GESTIONALE_RUNBOOK.md` | `current` | Autorità operativa corrente |
| `docs/MCP_GESTIONALE_SPEC.md` | `current` | Autorità operativa corrente |
| `docs/OBSIDIAN_KNOWLEDGE_ARCHITECTURE_2026-08-20.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/PIANO_OPERATIVO_GESTIONALE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/ARCHITETTURA.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/MAPPA_COLLEGAMENTI.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/MODELLO_NOTE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/PIANO_IMPLEMENTAZIONE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/PROMPT_IMPLEMENTAZIONE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/SICUREZZA_E_GOVERNANCE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/templates/ENTITA.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/obsidian-integration/templates/RUN_GIORNALIERO.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/rt-locale-drive.md` | `current` | Autorità operativa corrente |
| `frontend/README.md` | `current` | Autorità operativa corrente |
| `memoria/AUDIT_FRONTEND_DEAD_CODE.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/AUDIT_STATIC_REPORT.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/DISASTER_RECOVERY_DRIVE.md` | `current` | Autorità operativa corrente |
| `memoria/DRIVE_ESTRATTI_CONTO.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/FORNITORI_REGOLA_CANONICA.md` | `current` | Autorità operativa corrente |
| `memoria/INDEX.md` | `current` | Autorità operativa corrente |
| `memoria/LOGICA_LIBRO_MASTRO.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/MAPPA_ENDPOINT_COMPLETA.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/MAPPA_MODULI.md` | `current` | Autorità operativa corrente |
| `memoria/MAPPA_ROUTER.md` | `generated` | Artefatto meccanico; rigenerare dalla sorgente indicata |
| `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/SPECIFICA_IVA.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/01-prima-nota.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/02-contabilita.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/03-fatture-fornitori.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/04-banca-riconciliazione.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/05-f24.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/06-documenti-email-ai.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/07-hr-noleggio-verbali.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/08-sistema-admin.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/README.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/CEDOLINI.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/DIPENDENTI.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/DOCUMENTI_INBOX.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/F24.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/FATTURE_RICEVUTE.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/FORNITORI.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/MAGAZZINO.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/PRIMA_NOTA_BANCA.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/PRIMA_NOTA_CASSA.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/README.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/moduli/RICONCILIAZIONE.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |

## Regola architetturale

La destinazione è Drive-only: originali in Google Drive e registri in Google
Sheets/Excel collegato a Drive. MongoDB è compatibilità transitoria fino alla
verifica completa di copia, scrittura, ricostruzione e cutover; i documenti
storici che lo indicano come database primario non sono più autorità.
