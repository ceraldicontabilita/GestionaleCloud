# Inventario Markdown — GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

Inventario rigenerato il 2026-09-17 da `scripts/refresh_markdown_docs.py`.
Classifica i documenti senza riscrivere gli artefatti prodotti da altri script.

## Significato degli stati

| Stato | Significato |
|---|---|
| `current` | Descrive il comportamento o le regole operative correnti. |
| `reference` | Approfondimento di dominio; l'architettura corrente prevale. |
| `planned` | Specifica o piano approvato, non ancora completamente operativo. |
| `generated` | Output di uno script, da non modificare manualmente. |
| `historical` | Audit, piano o fotografia datata, conservata come prova. |

## Riepilogo

- Correnti: **29**
- Riferimento: **28**
- Pianificati: **7**
- Generati: **5**
- Storici: **51**
- Totale: **120**

## Elenco completo

| File | Stato | Uso |
|---|---|---|
| `.github/agents/mcp-gateway.agent.md` | `current` | Autorità operativa corrente |
| `.github/agents/ogni-pagina.agent.md` | `current` | Autorità operativa corrente |
| `.github/copilot-instructions.md` | `current` | Autorità operativa corrente |
| `.github/instructions/pagine-erp.instructions.md` | `current` | Autorità operativa corrente |
| `.github/skills/mcp-gateway/SKILL.md` | `current` | Autorità operativa corrente |
| `.github/skills/pagina-erp/SKILL.md` | `current` | Autorità operativa corrente |
| `AGENTS.md` | `current` | Autorità operativa corrente |
| `CLAUDE.md` | `current` | Autorità operativa corrente |
| `DESIGN.md` | `current` | Autorità operativa corrente |
| `LOGICA_FUNZIONAMENTO.md` | `current` | Autorità operativa corrente |
| `PRODUCT.md` | `current` | Autorità operativa corrente |
| `PROMPT_MASTER.md` | `current` | Autorità operativa corrente |
| `README.md` | `current` | Autorità operativa corrente |
| `archive/legacy-audit/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/ADR-001-HACCP-LOTTI-DRIVE-SHEETS.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/ADR-005-INGESTIONE-DOCUMENTALE-UNIVERSALE-RENDER.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/AUDIT_DUPLICATI_DRIVE_2026-09-11.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/AUDIT_DUPLICATI_DRIVE_2026-09-11_LOTTO2.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/FISCAL_ACCOUNTING_POLICY.md` | `current` | Autorità operativa corrente |
| `docs/GUIDA-SEMPLICE-FLUSSO-ATOMICO-RENDER.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/MARKDOWN_INVENTORY.md` | `current` | Autorità operativa corrente |
| `docs/MCP_GESTIONALE_RUNBOOK.md` | `current` | Autorità operativa corrente |
| `docs/MCP_GESTIONALE_SPEC.md` | `current` | Autorità operativa corrente |
| `docs/OBSIDIAN_KNOWLEDGE_ARCHITECTURE_2026-08-20.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/PIANO_OPERATIVO_GESTIONALE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/PROMPT_CEDOLINI_NETTO_DRIVE_SALARI.md` | `current` | Autorità operativa corrente |
| `docs/PROMPT_GESTIONALE_MITTENTI_TRIBUTI_DICHIARAZIONI_PARTENOPAY.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/REGOLA_FISSA_ATTESE.md` | `current` | Autorità operativa corrente |
| `docs/RUNBOOK-OBSIDIAN-PROCEDURE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `docs/RUNBOOK-RENDER-CALDERONE.md` | `current` | Autorità operativa corrente |
| `docs/obsidian-integration/ARCHITETTURA.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/obsidian-integration/MAPPA_COLLEGAMENTI.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/obsidian-integration/MODELLO_NOTE.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `docs/obsidian-integration/PIANO_IMPLEMENTAZIONE.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/obsidian-integration/PROMPT_IMPLEMENTAZIONE.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/obsidian-integration/README.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `docs/obsidian-integration/SICUREZZA_E_GOVERNANCE.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `docs/obsidian-integration/templates/ENTITA.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/obsidian-integration/templates/RUN_GIORNALIERO.md` | `planned` | Specifica approvata ma non ancora completamente operativa |
| `docs/rt-locale-drive.md` | `current` | Autorità operativa corrente |
| `frontend/README.md` | `current` | Autorità operativa corrente |
| `frontend_lotti/README.md` | `current` | Autorità operativa corrente |
| `frontend_menu/README.md` | `current` | Autorità operativa corrente |
| `memoria/AUDIT_COMMERCIALISTA_2026-09-03.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
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
| `memoria/README_ARCHIVIO_APP.md` | `current` | Autorità operativa corrente |
| `memoria/REFACTOR_APP_PAGINA_PER_PAGINA_2026-09-05.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/SPECIFICA_IVA.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/diario/2026-09-03.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/diario/2026-09-14.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/diario/2026-09-15.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/diario/2026-09-16-17.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/endpoints/01-prima-nota.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/02-contabilita.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/03-fatture-fornitori.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/04-banca-riconciliazione.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/05-f24.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/06-documenti-email-ai.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/07-hr-noleggio-verbali.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/08-sistema-admin.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/endpoints/README.md` | `reference` | Dettaglio di dominio subordinato ai documenti correnti |
| `memoria/hr/CLAUDE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/hr/modelli/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/.claude/skills/audit-codice/SKILL.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/.claude/skills/bonifica-design/SKILL.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/.claude/skills/collaudo-funzionale/SKILL.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/.claude/skills/guida-operativa/SKILL.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/CLAUDE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/DOCUMENTAZIONE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/MAPPA_VERITA.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/RISTRUTTURAZIONE_NAVIGAZIONE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/design_handoff/KIT_ALTRE_APP.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/design_handoff/PROMPT_USABILITA.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/design_handoff/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/docs/CONSOLIDAMENTO.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/docs/KEEPALIVE_RENDER.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/docs/PANORAMICA_APP.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/docs/ROADMAP_INTERCONNESSIONE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_E2E_LIVE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_FLUSSI.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_IMPORT_DATABASE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_NAVIGAZIONE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_QUANTITA_UNITA.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_REGISTRI_STAMPE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_SCHEDULER_TEMPERATURE.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_SICUREZZA.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/AUDIT_VISIVO_MOBILE_TABLET.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/PIANO_ESECUTIVO.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/PIANO_REFACTOR.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/PRD.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/REGOLE_ENZO.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/STATO.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/memory/claude.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/lotti/print-agent/README.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/menu/ALLERGENI_MENU.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
| `memoria/menu/test_result.md` | `historical` | Snapshot/audit datato, conservato come evidenza |
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

Drive/Sheets è l'unico archivio operativo: originali in Google Drive e registri
in Google Sheets/Excel collegato a Drive. Non esistono fallback di persistenza;
i documenti storici che descrivono altre architetture non sono autorità.
