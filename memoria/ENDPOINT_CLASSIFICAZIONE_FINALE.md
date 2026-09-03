# Classificazione endpoint (§7) — RIGENERABILE
> Generato da `scripts/genera_classificazione_endpoint.py` sulla route table reale.
> NON modificare a mano: rilancia lo script.

**Totale endpoint:** 1531 · tenere: 991 · verificare: 507 · admin-only (migrazione/manutenzione): 33

Colonne: FE=frontend, Sch=scheduler, Chat, Migr=migrazione/manutenzione, Test. Decisione conservativa: nulla viene eliminata in blocco (§7).

## Endpoint prioritari (§7)
| Metodo/path | Router | FE | Sch | Chat | Migr | Test | Decisione | Motivo |
|---|---|:-:|:-:|:-:|:-:|:-:|---|---|
| `POST /api/batch-reprocess/cedolini-only` | batch_reprocessing | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/batch-reprocess/f24-only` | batch_reprocessing | — | sì | — | — | sì | tenere | in uso: scheduler |
| `GET /api/batch-reprocess/preview` | batch_reprocessing | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/batch-reprocess/start` | batch_reprocessing | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/batch-reprocess/status` | batch_reprocessing | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/cedolini/drive/quadratura-completa` | drive_cedolini | — | sì | — | — | — | tenere | in uso: scheduler |
| `GET /api/cedolini/drive/status` | drive_cedolini | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/cedolini/drive/sync` | drive_cedolini | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/dati-provvisori/riconcilia-estratto-conto` | dati_provvisori | — | sì | — | — | — | tenere | in uso: scheduler |

## Tutti gli endpoint
| Metodo/path | Router | FE | Sch | Chat | Migr | Test | Decisione | Motivo |
|---|---|:-:|:-:|:-:|:-:|:-:|---|---|
| `POST /api/batch-reprocess/cedolini-only` | batch_reprocessing | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/batch-reprocess/f24-only` | batch_reprocessing | — | sì | — | — | sì | tenere | in uso: scheduler |
| `GET /api/batch-reprocess/preview` | batch_reprocessing | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/batch-reprocess/start` | batch_reprocessing | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/batch-reprocess/status` | batch_reprocessing | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/cedolini/drive/quadratura-completa` | drive_cedolini | — | sì | — | — | — | tenere | in uso: scheduler |
| `GET /api/cedolini/drive/status` | drive_cedolini | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/cedolini/drive/sync` | drive_cedolini | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/dati-provvisori/riconcilia-estratto-conto` | dati_provvisori | — | sì | — | — | — | tenere | in uso: scheduler |
| `GET /api/admin/bank-supplier-rules` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/bank-supplier-rules` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/bank-supplier-rules/reprocess/{year}` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/admin/bank-supplier-rules/{rule_id}` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/admin/cleanup-trattenute-disciplinari` | admin | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/admin/collections` | admin | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/admin/dashboard-summary` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/export` | admin_export | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/admin/export/{filename}` | admin_export | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/admin/google-sheets-ledger/config` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/google-sheets-ledger/config` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/google-sheets-ledger/duplicate-audit` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/google-sheets-ledger/duplicate-audit-folders` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/google-sheets-ledger/duplicate-cleanup-folders` | admin | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/admin/google-sheets-ledger/jobs/{action}` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/google-sheets-ledger/jobs/{job_id}` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/google-sheets-ledger/manifest` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/google-sheets-ledger/migration-audit` | admin | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/admin/google-sheets-ledger/restore` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/google-sheets-ledger/sync` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/noleggio/backfill-dati-gestionali` | admin | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/admin/reset-collections` | admin | — | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/admin/rollback/drive-fatture/conta` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/rollback/drive-fatture/elimina` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/rollback/fatture/azzera-tutto` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/rollback/fatture/azzera-tutto/conta` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/rollback/sezioni` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/admin/rollback/{sezione}` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/rollback/{sezione}/conta` | admin_rollback | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/admin/stats` | admin | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/admin/supabase-migration/jobs` | admin | sì | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/admin/supabase-migration/jobs/{job_id}` | admin | sì | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/admin/year-opening-balances/{year}` | admin | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/admin/year-opening-balances/{year}` | admin | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/agenti/automazioni/ferma` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/agenti/automazioni/riprendi` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/automazioni/stato` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/cash-flow-13-settimane` | agenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/agenti/decisioni` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/agenti/decisioni/{decision_id}/approva` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/decisioni/{decision_id}/eventi` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/agenti/decisioni/{decision_id}/rifiuta` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/pattern-appresi` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/agenti/run` | agenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/agenti/segnalazioni` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/segnalazioni/count` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/segnalazioni/summary` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/agenti/segnalazioni/{sid}/letta` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/agenti/segnalazioni/{sid}/risolta` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/agenti/stato` | agenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/ai-parser/batch-parse` | ai_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/ai-parser/da-rivedere` | ai_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/ai-parser/da-rivedere/process-batch` | ai_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/ai-parser/da-rivedere/{document_id}/classifica` | ai_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/ai-parser/parse` | ai_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/ai-parser/parse-busta-paga` | ai_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/ai-parser/parse-f24` | ai_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/ai-parser/parse-fattura` | ai_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/ai-parser/process-email-batch` | ai_parser | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/ai-parser/statistiche` | ai_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/ai-parser/test` | ai_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/alerts/fornitori-senza-metodo` | alerts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/alerts/lista` | alerts | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/alerts/risolvi-fornitore/{fornitore_piva}` | alerts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/alerts/summary` | alerts | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/alerts/{alert_id}` | alerts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/alerts/{alert_id}/risolvi` | alerts | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/alerts/{alert_id}/segna-letto` | alerts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/anagrafica-fornitori/popola-fornitore/{fornitore_id}` | anagrafica_fornitori_xml | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/anagrafica-fornitori/popola-tutti` | anagrafica_fornitori_xml | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/archivio-bonifici/associa-dipendenti` | bonifici_module.riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/archivio-bonifici/associa-fattura` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/archivio-bonifici/associa-salario` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/dashboard` | bonifici_module.riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/archivio-bonifici/dipendente/{dipendente_id}` | bonifici_module.associazioni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/archivio-bonifici/disassocia-fattura/{bonifico_id}` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/archivio-bonifici/disassocia-salario/{bonifico_id}` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/download-zip/{year}` | bonifici_module.transfers | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/archivio-bonifici/export` | bonifici_module.transfers | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/archivio-bonifici/fatture-compatibili/{bonifico_id}` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/jobs` | bonifici_module.jobs | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/archivio-bonifici/jobs` | bonifici_module.jobs | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/archivio-bonifici/jobs/import` | bank.bonifici_import_unificato | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/archivio-bonifici/jobs/{job_id}` | bonifici_module.jobs | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/archivio-bonifici/jobs/{job_id}/upload` | bonifici_module.jobs | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/archivio-bonifici/operazioni-salari/{bonifico_id}` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/archivio-bonifici/reset-riconciliazione` | bonifici_module.riconciliazione | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/archivio-bonifici/riconcilia` | bonifici_module.riconciliazione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/riconcilia/task/{task_id}` | bonifici_module.riconciliazione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/stato-riconciliazione` | bonifici_module.riconciliazione | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/archivio-bonifici/sync-iban-anagrafica` | bonifici_module.associazioni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/transfers` | bonifici_module.transfers | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/archivio-bonifici/transfers/bulk` | bonifici_module.transfers | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/transfers/count` | bonifici_module.transfers | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/transfers/summary` | bonifici_module.transfers | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/archivio-bonifici/transfers/{transfer_id}` | bonifici_module.transfers | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/archivio-bonifici/transfers/{transfer_id}` | bonifici_module.transfers | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/archivio-bonifici/transfers/{transfer_id}/pdf` | bonifici_module.transfers | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/assegni` | public_api | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/assegni-legacy` | public_api | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/assegni/ambigui` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/associa-beneficiari-robusto` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/associa-pagamenti-multipli` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/auto-associa` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/auto-match` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/auto-match/conferma` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/cerca-combinazioni-assegni` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/assegni/clear-generated` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/conferma-proposta/{proposta_id}` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/assegni/correggi-associazione/{assegno_id}` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/correggi-numeri` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/genera` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/assegni/learning/associa-combinazioni-avanzato` | bank.assegni_learning | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/learning/associa-intelligente` | bank.assegni_learning | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/learning/learn` | bank.assegni_learning | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/learning/pulizia-duplicati` | bank.assegni_learning | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/assegni/learning/stats-avanzate` | bank.assegni_learning | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/learning/suggerimenti/{importo}` | bank.assegni_learning | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/preview-combinazioni` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/proposte-associazione` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/pulisci-beneficiari-fittizi` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/ricostruisci-dati` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/assegni/rifiuta-proposta/{proposta_id}` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/riprocessa-collegamenti` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/assegni/senza-associazione` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/stati` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/stats` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/supporto/fatture-disponibili` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/assegni/sync-da-estratto-conto` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/verifica-associazioni` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/assegni/{assegno_id}` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/assegni/{assegno_id}` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/assegni/{assegno_id}` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/assegni/{assegno_id}/annulla` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/{assegno_id}/emetti` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/assegni/{assegno_id}/fatture-collegate` | bank.assegni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/assegni/{assegno_id}/incassa` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/assegni/{assegno_id}/risolvi-ambiguo` | bank.assegni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/auth/login` | auth | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/auth/logout` | auth | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/auth/mfa/disable` | mfa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/auth/mfa/setup/confirm` | mfa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/auth/mfa/setup/start` | mfa | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/auth/mfa/status` | mfa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/auth/mfa/step-up` | mfa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/auth/mfa/verify-login` | mfa | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/auth/pin-login` | pin_login | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/auth/pin-login/health` | pin_login | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/auth/verify` | auth | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/auto-repair/collega-targa-driver` | auto_repair | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/auto-repair/inferisci-targa-driver-da-fatture` | auto_repair | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/bank-statement/cleanup-duplicati` | bank.bank_statement_import | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/bank-statement/cleanup-duplicati-causale` | bank.bank_statement_import | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/bank-statement/formati-supportati` | bank.bank_statement_import | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/bank-statement/import` | bank.bank_statement_import | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/bank-statement/movements` | bank.bank_statement_import | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/bank-statement/riconcilia-manuale` | bank.bank_statement_import | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/bank-statement/stats` | bank.bank_statement_import | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/bank/statements` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/bank/statements` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/bilancio/confronto-annuale` | accounting.bilancio | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/bilancio/conto-economico` | accounting.bilancio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/bilancio/conto-economico-dettagliato` | accounting.bilancio | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/bilancio/export-pdf` | accounting.bilancio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/bilancio/export/pdf/confronto` | accounting.bilancio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/bilancio/riepilogo` | accounting.bilancio | — | — | sì | — | — | tenere | in uso: chat |
| `GET /api/bilancio/stato-patrimoniale` | accounting.bilancio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cash` | public_api | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/cash` | public_api | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/cash/corrispettivi` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/cash/corrispettivi/{target_date}` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/cash/export/excel` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/cash/movements` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/cash/movements` | cash | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/cash/movements/{movement_id}` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/cash/movements/{movement_id}` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/cash/stats` | cash | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/centri-costo` | accounting.centri_costo | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/centri-costo` | accounting.centri_costo | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/centri-costo/assegna-cdc-fatture` | accounting.centri_costo | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/centri-costo/mapping-categorie` | accounting.centri_costo | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/centri-costo/ribaltamento/calcola` | accounting.centri_costo | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/centri-costo/ribaltamento/quote-ricavo` | accounting.centri_costo | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/centri-costo/utile-obiettivo` | accounting.centri_costo | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/centri-costo/utile-obiettivo` | accounting.centri_costo | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/centri-costo/utile-obiettivo/per-cdc` | accounting.centri_costo | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/centri-costo/utile-obiettivo/suggerimenti` | accounting.centri_costo | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/cespiti/` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/cespiti/` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cespiti/calcolo-rateo/{anno}/{mese}` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cespiti/calcolo/{anno}` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cespiti/categorie` | cespiti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/cespiti/dismissione` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/cespiti/registra/{anno}` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cespiti/riepilogo` | cespiti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/cespiti/scan-fatture` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cespiti/verifica/{anno}` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/cespiti/{cespite_id}` | cespiti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/cespiti/{cespite_id}` | cespiti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/cespiti/{cespite_id}` | cespiti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/chat/ask` | chat_router | sì | — | sì | — | — | tenere | in uso: FE, chat |
| `GET /api/chat/health` | chat_router | — | — | sì | — | — | tenere | in uso: chat |
| `GET /api/chat/history` | chat_router | — | — | sì | — | — | tenere | in uso: chat |
| `POST /api/chiusura-esercizio/apertura-nuovo-esercizio` | chiusura_esercizio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/chiusura-esercizio/bilancino-verifica/{anno}` | chiusura_esercizio | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/chiusura-esercizio/esegui-chiusura` | chiusura_esercizio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/chiusura-esercizio/saldi-iniziali/{anno}` | chiusura_esercizio | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/chiusura-esercizio/stato/{anno}` | chiusura_esercizio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/chiusura-esercizio/storico` | chiusura_esercizio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/chiusura-esercizio/verifica-preliminare/{anno}` | chiusura_esercizio | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/collaudo/esegui` | collaudo | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/collaudo/storico` | collaudo | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/collaudo/ultimo` | collaudo | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/alert-status` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/config` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/commercialista/config` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/export-completo/{anno}/{mese}` | commercialista | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/commercialista/export-excel/{anno}/{mese}` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/export-log` | commercialista | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/commercialista/fatture-cassa/{anno}/{mese}` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/commercialista/invia-carnet` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/commercialista/invia-fatture-cassa` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/commercialista/invia-prima-nota` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/log` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/prima-nota-cassa/{anno}/{mese}` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/commercialista/riepilogo/{anno}/{mese}` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/commercialista/schedula-export` | commercialista | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/commercialista/segna-inviata` | commercialista | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/conferma-tutte` | dati_provvisori | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/conferma/{proposta_id}` | dati_provvisori | — | sì | sì | — | sì | tenere | in uso: scheduler, chat |
| `GET /api/config-import/anno` | config_import | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/config-import/anno` | config_import | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/config-import/importa-anno` | config_import | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/config/email-accounts` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/config/email-accounts` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/config/email-accounts/{account_id}` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/config/email-accounts/{account_id}` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/config/email-accounts/{account_id}/test` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/config/parole-chiave` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/config/parole-chiave` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/config/parole-chiave/aggiungi` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/config/parole-chiave/rimuovi` | configurazioni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/bilancio-verifica` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/contabilita-gestionale/budget` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/budget-vs-consuntivo/{anno}` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/contabilita-gestionale/budget/duplica/{anno_origine}/{anno_destinazione}` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/budget/{anno}` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/contabilita-gestionale/budget/{anno}/{voce}` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/libro-giornale` | accounting.contabilita_gestionale | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/libro-giornale/controllo-60-giorni` | accounting.contabilita_gestionale | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/libro-giornale/export` | accounting.contabilita_gestionale | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/contabilita-gestionale/libro-giornale/import` | accounting.contabilita_gestionale | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/libro-mastro` | accounting.contabilita_gestionale | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/contabilita-gestionale/partitario/clienti` | accounting.contabilita_gestionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/contabilita-gestionale/partitario/fornitori` | accounting.contabilita_gestionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/contabilita-gestionale/partitario/fornitori/{piva}` | accounting.contabilita_gestionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/contabilita/aliquote-irap` | accounting.contabilita_avanzata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita/bilancio-dettagliato` | accounting.contabilita_avanzata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita/calcolo-imposte` | accounting.contabilita_avanzata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita/categorizzazione-preview` | accounting.contabilita_avanzata | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/contabilita/disponibilita-liquide` | contabilita_italiana | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita/export/pdf-dichiarazione` | accounting.contabilita_avanzata | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/contabilita/inizializza-piano-esteso` | accounting.contabilita_avanzata | sì | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/contabilita/piano-conti-esteso` | accounting.contabilita_avanzata | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/contabilita/ricategorizza-fatture` | accounting.contabilita_avanzata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/contabilita/statistiche-categorizzazione` | accounting.contabilita_avanzata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/controllo-gestione/costi-per-categoria` | controllo_gestione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/controllo-gestione/costi-ricavi` | controllo_gestione | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/controllo-gestione/kpi/{anno}` | controllo_gestione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/controllo-gestione/trend-mensile` | controllo_gestione | — | — | sì | — | — | tenere | in uso: chat |
| `GET /api/corrispettivi` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/aggiorna-stati-mancanti` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/corrispettivi/all` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/auto-ricostruisci-dati` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/cleanup-duplicati-forte` | invoices.corrispettivi | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/corrispettivi/drive/quadratura` | drive_corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/corrispettivi/drive/status` | drive_corrispettivi | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/corrispettivi/drive/sync` | drive_corrispettivi | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/corrispettivi/elimina-duplicati` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/hard-delete-bulk` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/corrispettivi/hard-delete/{corrispettivo_id}` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/import-csv` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/manuale` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/corrispettivi/manuali-senza-xml` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/normalizza-pagamenti` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/rebuild-prima-nota` | invoices.corrispettivi | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/corrispettivi/ricalcola-annulli-non-riscosso` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/ricalcola-iva` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/sincronizza-prima-nota` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/corrispettivi/template-csv` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/corrispettivi/totals` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/upload-xml` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/upload-xml-bulk` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/corrispettivi/upload-zip` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/corrispettivi/view-by-filename` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/corrispettivi/{corrispettivo_id}` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/corrispettivi/{corrispettivo_id}/view` | invoices.corrispettivi | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dashboard/bilancio-istantaneo` | reports.dashboard | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/confronto-annuale` | reports.dashboard | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/fascia-energia` | reports.dashboard | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dashboard/kpi` | reports.dashboard | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/spese-per-categoria` | reports.dashboard | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/stato-riconciliazione` | reports.dashboard | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/stats` | reports.dashboard | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/stats-legacy` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/summary` | reports.dashboard | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dashboard/trend-mensile` | reports.dashboard | sì | — | sì | — | — | tenere | in uso: FE, chat |
| `GET /api/data-deletion` | legal_pages | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dati-isa/riepilogo` | dati_isa | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/dipendenti` | employees.dipendenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/dipendenti` | employees.dipendenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/dipendenti/bulk-upsert` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/bulk-upsert/preview` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/buste-paga` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/buste-paga` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/buste-paga/dipendente/{dipendente_id}` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/buste-paga/dipendente/{dipendente_id}/import` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/buste-paga/import` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/buste-paga/scan` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/by-google-email` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/duplicati` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/duplicati/auto-merge` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/duplicati/merge` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/invita-multipli` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/mansioni` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/portale/stats` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/report-ferie-permessi-tutti` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/stats` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/sync-iban` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/tipi-turno` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/turni/salva` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/turni/settimana` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/dipendenti/{dipendente_id}` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/{dipendente_id}` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/dipendenti/{dipendente_id}` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dipendenti/{dipendente_id}/invita-portale` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dipendenti/{dipendente_id}/report-ferie-permessi` | employees.dipendenti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/dizionario-articoli/articolo/{descrizione_encoded}` | warehouse.dizionario_articoli | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/dizionario-articoli/categorizza-ai` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dizionario-articoli/cerca` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dizionario-articoli/dizionario` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dizionario-articoli/estrai-articoli` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/dizionario-articoli/genera-dizionario` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/dizionario-articoli/non-classificati` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/dizionario-articoli/reset-dizionario` | warehouse.dizionario_articoli | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/dizionario-articoli/ricategorizza-fatture` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/dizionario-articoli/riclassifica-completo` | warehouse.dizionario_articoli | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/dizionario-articoli/statistiche` | warehouse.dizionario_articoli | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/document-ai/classified-documents-stats` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/document-ai/document-types` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/document-ai/extract` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/document-ai/extract-base64` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/document-ai/extract-text-only` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/document-ai/extracted-documents` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/document-ai/extracted-documents/{doc_id}` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/document-ai/process-all-classified` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/document-ai/process-classified-email` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/document-ai/reprocess-and-save` | document_ai | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti-fiscali/lista` | documenti_fiscali | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti-fiscali/upload` | documenti_fiscali | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti-fiscali/upload-f24-commercialista` | documenti_fiscali | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti-inbox/auto-classify` | documents_inbox_classify | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti-inbox/cross-check-f24` | documents_inbox_classify | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti-inbox/import-dipendenti-from-cu` | documents_inbox_classify | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti-inbox/import-f24-from-inbox` | documents_inbox_classify | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti-inbox/statistics` | documents_inbox_classify | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti-non-associati/associa` | documenti_non_associati | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti-non-associati/associati-di-recente` | documenti_non_associati | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti-non-associati/categorie-mittente` | documenti_non_associati | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti-non-associati/collezioni-disponibili` | documenti_non_associati | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti-non-associati/de-associa` | documenti_non_associati | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti-non-associati/lista` | documenti_non_associati | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti-non-associati/pdf/{documento_id}` | documenti_non_associati | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti-non-associati/statistiche` | documenti_non_associati | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/documenti-non-associati/{documento_id}` | documenti_non_associati | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/amministrativi` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/amministrativi/familiari` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/cartelle-email` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/categorie` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/documenti/documento/{doc_id}` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/documento/{doc_id}` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti/documento/{doc_id}/annulla-processamento` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti/documento/{doc_id}/cambia-categoria` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/documento/{doc_id}/download` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti/documento/{doc_id}/processa` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/drive/catalog` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti/drive/fiscal/discover` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/drive/fiscal/status` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti/drive/fiscal/sync` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/drive/folders` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/drive/index/declarations` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/drive/index/document/{document_id}` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/drive/index/f24` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/drive/index/overview` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/drive/index/search` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/documenti/drive/index/status` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti/drive/sync` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti/elimina-processati` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/fiscal/ingest` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/lista` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/lock-status` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/monitor/start` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/monitor/status` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/monitor/stop` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/monitor/sync-now` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/processa-f24-scaricati` | documenti | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/processa-tutti` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/reimporta-da-filesystem` | documenti | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/documenti/ricategorizza-documenti` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/scarica-da-email` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/statistiche` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/sync-estratti-bnl` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/sync-estratti-conto` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/sync-f24-automatico` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/task/{task_id}` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/tax-codes` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/tax-codes/status` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti/tax-codes/sync` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/telegram/status` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/telegram/test` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/documenti/ultimo-sync` | documenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/documenti/upload-auto` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/documenti/upload-auto/jobs/{job_id}` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti/upload-auto/preview` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti/upload-auto/queue` | documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/documenti/upload-auto/render` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/documenti/upload-auto/render/preview` | documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/email-download/associa-documento` | email_download | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/associa-f24-filesystem` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/auto-associa` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/email-download/auto-associa-v2` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/confronto-pos` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/dizionario-email` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/email-download/dizionario-email/reset` | email_download | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/email-download/documenti-non-associati` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/documents-inbox-stats` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/download-single-day` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/estrai-importi-verbali` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/fix-numeri-verbali` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/inbox-documents` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/mittenti` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/email-download/mittenti` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/email-download/mittenti/check` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/email-download/mittenti/migra-legacy` | email_download | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `DELETE /api/email-download/mittenti/{mittente_id}` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/email-download/mittenti/{mittente_id}` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/email-download/parse-f24-llm` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/parse-verbali-llm` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/paypal-transazioni` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/pdf/{collection}/{pdf_id}` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/popola-pdf-payslips` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/processa-cedolini` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/processa-pipeline` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/email-download/pulisci-duplicati` | email_download | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/email-download/pulizia-non-attendibili` | email_download | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/email-download/riconcilia-paypal` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/riconcilia-verbali` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/riconcilia-verbali-avanzato` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/riconciliazione-completa` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/scarica-pdf-verbali-mancanti` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/start-full-download` | email_download | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/email-download/statistiche` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-download/status` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/sync-email-now` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-download/sync-filesystem` | email_download | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-scanner/associa` | email_scanner | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/email-scanner/cartelle` | email_scanner | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-scanner/scansiona` | email_scanner | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/email-scanner/scansiona-e-associa` | email_scanner | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/email-scanner/statistiche` | email_scanner | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/estratto-conto-movimenti/categorie` | bank.estratto_conto | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/estratto-conto-movimenti/clear` | bank.estratto_conto | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/estratto-conto-movimenti/export-excel` | bank.estratto_conto | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/estratto-conto-movimenti/force-reimport` | bank.estratto_conto | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/estratto-conto-movimenti/fornitori` | bank.estratto_conto | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/estratto-conto-movimenti/import` | bank.estratto_conto | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/estratto-conto-movimenti/movimenti` | bank.estratto_conto | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/estratto-conto-movimenti/movimenti-stipendi` | bank.estratto_conto | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/estratto-conto-movimenti/pulizia-non-in-csv` | bank.estratto_conto | — | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/estratto-conto-movimenti/reimport` | bank.estratto_conto | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/estratto-conto-movimenti/ricategorizza-batch` | bank.estratto_conto | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/estratto-conto-movimenti/riconcilia-stipendi` | bank.estratto_conto | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/estratto-conto-movimenti/riepilogo` | bank.estratto_conto | — | — | sì | — | sì | tenere | in uso: chat |
| `POST /api/estratto-conto-movimenti/ripara-versamenti-cassa` | bank.estratto_conto | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/estratto-conto-movimenti/{movimento_id}` | bank.estratto_conto | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24` | f24.f24_main | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/f24` | f24.f24_main | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/f24-analisi/doppi-pagamenti` | f24_analisi | — | — | sì | — | — | tenere | in uso: chat |
| `GET /api/f24-analisi/tabella` | f24_analisi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-analisi/{f24_id}` | f24_analisi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-analisi/{f24_id}/associazione` | f24_analisi | — | — | sì | — | sì | tenere | in uso: chat |
| `POST /api/f24-email-settings/aggiungi-mittente` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24-email-settings/impostazioni` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24-email-settings/impostazioni` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24-email-settings/log-scansioni` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/f24-email-settings/rimuovi-mittente/{email}` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24-email-settings/scan-manuale` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24-email-settings/stato-sistema` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24-email-settings/toggle-auto-scan` | f24_email_settings | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24-email/allegati` | f24.email_f24 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-email/codici-tributo` | f24.email_f24 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-email/log-download` | f24.email_f24 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-email/mittenti` | f24.email_f24 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-email/processa-allegati` | f24.email_f24 | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-email/scarica-e-processa` | f24.email_f24 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-email/scarica-email` | f24.email_f24 | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-public/alerts` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-public/dashboard` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-public/models` | f24.f24_public | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/f24-public/models/{f24_id}` | f24.f24_public | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/f24-public/models/{f24_id}` | f24.f24_public | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/f24-public/models/{f24_id}/pagato` | f24.f24_public | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-public/pdf/{f24_id}` | f24.f24_public | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-public/scadenze-prossime` | f24.f24_public | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-public/test` | f24.f24_public | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-public/upload` | f24.f24_public | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-public/upload-overwrite` | f24.f24_public | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/alerts` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/alerts/{alert_id}/conferma-elimina` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/alerts/{alert_id}/ignora` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/commercialista` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/commercialista/upload` | f24.f24_riconciliazione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/f24-riconciliazione/commercialista/{f24_id}` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/commercialista/{f24_id}` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/f24-riconciliazione/commercialista/{f24_id}` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/f24-riconciliazione/commercialista/{f24_id}/pagato` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/commercialista/{f24_id}/pdf` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/dashboard` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/estratti-conto` | bank.riconciliazione_f24_banca | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/fix-campo-anno` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/movimenti-f24-banca` | bank.riconciliazione_f24_banca | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/quietanze` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/quietanze/upload-multiplo` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/quietanze/{quietanza_id}` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/riconcilia-f24` | bank.riconciliazione_f24_banca | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/riconcilia-quietanza` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/riconcilia-tutto` | f24.f24_riconciliazione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24-riconciliazione/stato-riconciliazione` | bank.riconciliazione_f24_banca | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/f24-riconciliazione/upload-estratto-bpm` | bank.riconciliazione_f24_banca | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24-riconciliazione/verifica-codice/{codice_tributo}` | f24.f24_riconciliazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/f24/alerts/scadenze` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/codici/all` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/codici/{codice}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/dashboard/summary` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/documents` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/f24/documents/{doc_id}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24/fascicolo/costruisci` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/fascicolo/{codice_fiscale}/{mese}/{anno}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/quietanze` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24/quietanze/drive/quadratura` | drive_quietanze | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/quietanze/drive/status` | drive_quietanze | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/f24/quietanze/drive/sync` | drive_quietanze | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/f24/quietanze/statistiche/tributi` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24/quietanze/upload` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/f24/quietanze/{f24_id}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/quietanze/{f24_id}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24/riconcilia` | f24.f24_main | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/f24/upload` | f24.f24_main | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/f24/upload-multiple` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24/upload-pdf` | f24.f24_main | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/f24/upload-zip` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/f24/{f24_id}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/f24/{f24_id}` | f24.f24_main | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/f24/{f24_id}` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/f24/{f24_id}/mark-paid` | f24.f24_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fatture-estere/affidabilita` | fatture_estera_verifica | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fatture-estere/da-verificare` | fatture_estera_verifica | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fatture-estere/{fattura_id}/verifica` | fatture_estera_verifica | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fatture-ricevute/aggiorna-metodi-pagamento` | fatture_module.pagamento | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fatture-ricevute/archivio` | fatture_module.crud | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fatture-ricevute/backfill-autoroute` | fatture_module.pagamento | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/fatture-ricevute/cambia-metodo-pagamento` | fatture_module.pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fatture-ricevute/elimina-anni-vecchi` | fatture_module.crud | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fatture-ricevute/elimina-gusci-vuoti` | fatture_module.crud | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fatture-ricevute/export-selezione` | fatture_module.export_selezione | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fattura/{fattura_id}` | fatture_module.crud | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `PUT /api/fatture-ricevute/fattura/{fattura_id}` | fatture_module.crud | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `GET /api/fatture-ricevute/fattura/{fattura_id}/candidati-bancari` | fatture_module.pagamento | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fattura/{fattura_id}/documenti-pagamento` | fatture_module.crud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fattura/{fattura_id}/pdf/{allegato_id}` | fatture_module.crud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fattura/{fattura_id}/storia` | fatture_module.crud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fattura/{fattura_id}/view-assoinvoice` | fatture_module.crud | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fattura/{fattura_id}/xml-originale` | fatture_module.crud | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fatture-ricevute/fornitori` | fatture_module.crud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fatture-ricevute/import-paypal` | fatture_module.pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fatture-ricevute/lista-paypal` | fatture_module.pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fatture-ricevute/paga-manuale` | fatture_module.pagamento | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fatture-ricevute/pulisci-duplicati` | fatture_module.crud | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/fatture-ricevute/riconcilia-con-estratto-conto` | fatture_module.pagamento | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fatture-ricevute/riconcilia-paypal` | fatture_module.pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fatture-ricevute/statistiche` | fatture_module.crud | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fatture-ricevute/verifica-incoerenze-estratto-conto` | fatture_module.pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/fatture/all` | invoices.fatture_upload | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/fatture/categorize-movements` | invoices.fatture_upload | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/fatture/drive/quadratura` | invoices.fatture_drive | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fatture/drive/ricostruzione` | invoices.fatture_drive | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fatture/drive/ricostruzione/lotto` | invoices.fatture_drive | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fatture/drive/status` | invoices.fatture_drive | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/fatture/drive/sync` | invoices.fatture_drive | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/fatture/recalculate-iva` | invoices.fatture_upload | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/fatture/sync-suppliers` | invoices.fatture_upload | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/fatture/upload-xml` | invoices.fatture_upload | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/fatture/upload-xml-bulk` | invoices.fatture_upload | — | sì | — | — | — | tenere | in uso: scheduler |
| `DELETE /api/fatture/{invoice_id}` | invoices.fatture_upload | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `GET /api/fatture/{invoice_id}` | invoices.fatture_upload | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `PUT /api/fatture/{invoice_id}` | invoices.fatture_upload | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `PUT /api/fatture/{invoice_id}/classifica` | invoices.fatture_upload | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `GET /api/fatture/{invoice_id}/entita-correlate` | invoices.fatture_upload | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `PUT /api/fatture/{invoice_id}/paga` | invoices.fatture_upload | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/finanziamenti-soci/movimento` | finanziamenti_soci | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/finanziamenti-soci/movimento/{movimento_id}` | finanziamenti_soci | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/finanziamenti-soci/scan` | finanziamenti_soci | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/finanziamenti-soci/schede` | finanziamenti_soci | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/finanziaria/cost-categories` | finanziaria | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/finanziaria/costi` | finanziaria | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/finanziaria/costo` | finanziaria | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/finanziaria/summary` | finanziaria | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscal/ader-snapshots` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fiscal/ader-snapshots/dry-run` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fiscal/ader-snapshots/import` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fiscal/collection-snapshots/dry-run` | fiscal_control | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fiscal/collection-snapshots/import` | fiscal_control | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscal/collections` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscal/collections/{claim_id}` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fiscal/collections/{claim_id}/events` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fiscal/crosswalk` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fiscal/declarations` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscal/declarations/{document_id}/field-certainty` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscal/documents/{document_id}/content` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fiscal/dossier.pdf` | fiscal_control | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscal/evidence-package.zip` | fiscal_control | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscal/evidence/{entity_type}/{entity_id}` | fiscal_control | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/fiscal/f24-documents` | fiscal_control | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscal/f24-rows` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscal/obligations` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fiscal/ravvedimento/calculate` | fiscal_control | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscal/review` | fiscal_control | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fiscal/source-certainty` | fiscal_control | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscal/summary` | fiscal_control | sì | — | sì | — | sì | tenere | in uso: FE, chat |
| `POST /api/fiscal/vat-credit-chain/rebuild` | fiscal_control | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscalita/agevolazioni` | fiscalita_italiana | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fiscalita/agevolazioni/simula` | fiscalita_italiana | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscalita/agevolazioni/{agevolazione_id}` | fiscalita_italiana | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fiscalita/calendario/completa/{scadenza_id}` | fiscalita_italiana | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fiscalita/calendario/riapri/{scadenza_id}` | fiscalita_italiana | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscalita/calendario/scadenze-imminenti` | fiscalita_italiana | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/fiscalita/calendario/{anno}` | fiscalita_italiana | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fiscalita/f24/registra` | fiscalita_italiana | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscalita/f24/storico` | fiscalita_italiana | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fiscalita/notifiche-scadenze` | fiscalita_italiana | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fiscalita/notifiche-scadenze/invia` | fiscalita_italiana | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fornitori-learning/associa-magazzino` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fornitori-learning/centri-costo-disponibili` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fornitori-learning/classifica-ai` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fornitori-learning/classifica-da-contenuto` | fornitori_learning | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/fornitori-learning/classifica-f24` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fornitori-learning/f24-statistiche` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fornitori-learning/giacenze-fornitore/{fornitore_nome}` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/fornitori-learning/lista` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fornitori-learning/non-classificati` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fornitori-learning/prodotti-per-fornitore/{fornitore_nome}` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fornitori-learning/riclassifica-con-keywords` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/fornitori-learning/riclassifica-f24/{f24_id}` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/fornitori-learning/salva` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fornitori-learning/stats` | fornitori_learning | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/fornitori-learning/suggerisci-keywords/{fornitore_nome}` | fornitori_learning | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/fornitori-learning/{fornitore_id}` | fornitori_learning | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/genera-proposte` | dati_provvisori | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/gestione-riservata/login` | gestione_riservata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/gestione-riservata/movimenti` | gestione_riservata | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/gestione-riservata/movimenti` | gestione_riservata | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/gestione-riservata/movimenti/{movimento_id}` | gestione_riservata | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/gestione-riservata/movimenti/{movimento_id}` | gestione_riservata | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/gestione-riservata/riepilogo` | gestione_riservata | sì | — | sì | — | sì | tenere | in uso: FE, chat |
| `GET /api/gestione-riservata/volume-affari-reale` | gestione_riservata | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/haccp/equipment` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/equipment` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `PATCH /api/haccp/equipment/{equipment_id}` | haccp | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/haccp/expectations` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/lots` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/lots` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/lots/{lot_id}/movements` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/lots/{lot_id}/trace` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/overview` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/productions` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/productions` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/purchase-lines` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/recipes` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/recipes` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/haccp/recipes/{recipe_id}` | haccp | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/haccp/register-types` | haccp | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/haccp/registers` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/registers` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/registers/{entry_id}/resolve` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/haccp/sync-invoices` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/haccp/sync-preview` | haccp | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/accessi` | app.hr.routers.employees.accessi | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/hr/accessi/genera-mancanti` | app.hr.routers.employees.accessi | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/hr/accessi/{dipendente_id}/pin` | app.hr.routers.employees.accessi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/accessi/{dipendente_id}/pin` | app.hr.routers.employees.accessi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/accessi/{dipendente_id}/pin/genera` | app.hr.routers.employees.accessi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/accessi/{dipendente_id}/ruolo` | app.hr.routers.employees.accessi | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/admin/migrazione-appdipendenti` | app.hr.routers.admin_hr | — | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/hr/admin/migrazione-appdipendenti/{job_id}` | app.hr.routers.admin_hr | — | sì | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/hr/admin/stato-dati` | app.hr.routers.admin_hr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/assenze/{employee_id}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/attendance/batch-insert` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/dashboard-presenze` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/dipendenti-in-carico` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/attendance/genera-pdf-consulente` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/month-grid` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/note-presenze/{anno}/{mese}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/ore-lavorate/{employee_id}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/attendance/presenza` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/presenze-mese` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/attendance/richiesta-assenza` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/attendance/richiesta-assenza/{richiesta_id}/approva` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/attendance/richiesta-assenza/{richiesta_id}/rifiuta` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/richieste-pending` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/saldo-ferie/{employee_id}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/attendance/set-in-carico/{employee_id}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/attendance/set-nota-presenza` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/attendance/set-presenza` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/attendance/timbratura` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/timbrature/giorno/{data}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/timbrature/{employee_id}` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/attendance/tipologie-giustificativi` | app.hr.routers.attendance | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/auth/dipendenti-attivi` | app.hr.routers.pin_login | sì | — | sì | — | sì | tenere | in uso: FE, chat |
| `POST /api/hr/auth/pin-login` | app.hr.routers.pin_login | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/auth/pin-login/health` | app.hr.routers.pin_login | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/buste-paga/competenze` | app.hr.routers.employees.buste_paga | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/buste-paga/lista` | app.hr.routers.employees.buste_paga | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/buste-paga/riepilogo-mensile/{competenza}` | app.hr.routers.employees.buste_paga | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/buste-paga/salva` | app.hr.routers.employees.buste_paga | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/buste-paga/upload` | app.hr.routers.employees.buste_paga | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/buste-paga/{competenza}/{nome}` | app.hr.routers.employees.buste_paga | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/cedolini` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/acconti/dipendente/{dipendente_id}` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/acconti/scan-estratto-conto` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/conferma` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/correggi-problematici` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/dipendente/{dipendente_id}` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/dipendente/{dipendente_id}/acconti-banca` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/dipendente/{dipendente_id}/applica-trattenuta/{trattenuta_id}` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/dipendente/{dipendente_id}/applica-tutte-trattenute` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/dipendente/{dipendente_id}/trattenute` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/import-drive` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/import-gmail` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/incompleti` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/incompleti/{cedolino_id}/completa` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/lista/{anno}/{mese}` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/problematici` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/riepilogo-mensile/{anno}/{mese}` | app.hr.routers.cedolini | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/cedolini/simulazione-f24` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/cedolini/stima` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/{cedolino_id}` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/cedolini/{cedolino_id}/download` | app.hr.routers.cedolini | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/acconti-tfr` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/acconti-tfr/{employee_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/carica-firmato/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/ccnl` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/ccnl/suggerisci` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/ccnl/verifica-tranche` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/ccnl/{ccnl_id}/livello/{livello}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/cedolini/importa-libro-unico` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/download/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/employee/{employee_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/finalizza/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/genera-massivo` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/generate/{employee_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/pdf/{contract_id}/{versione}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/pec/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/profilo-retributivo/{employee_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/send/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/sign/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/sign/{contract_id}/status` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/contracts/template/{contract_type}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/templates` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/contracts/types` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/contracts/{contract_id}` | app.hr.routers.employees.employee_contracts | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/diagnostica` | app.hr.routers.diagnostica | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/dimissioni` | app.hr.routers.dimissioni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dimissioni/associa-dimissioni-dipendenti` | app.hr.routers.dimissioni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dimissioni/cerca-email-dimissioni` | app.hr.routers.dimissioni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dimissioni/stats` | app.hr.routers.dimissioni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti` | app.hr.routers.employees.dipendenti | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti` | app.hr.routers.employees.dipendenti | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti-cloud/_unif_diag` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/_unif_esegui` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/alerts` | app.hr.routers.dipendenti_cloud | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/alerts/{alert_id}/risolvi` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/assegnazioni-turni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/assegnazioni-turni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/assegnazioni-turni/migra` | app.hr.routers.dipendenti_cloud | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/hr/dipendenti-cloud/bonifici-da-associare` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/bonifici-da-associare/{bonifico_id}/associa` | app.hr.routers.dipendenti_cloud | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/bonifici-da-associare/{bonifico_id}/ignora` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/bonifici-da-associare/{bonifico_id}/pdf` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/buste-paga` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/buste-paga` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/buste-paga/genera` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/buste-paga/{busta_id}/paga` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/cedolini/cerca-voce` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/cedolini/riscansiona` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/dashboard/stats` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/dipendenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/dipendenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/dipendenti/importa-anagrafica` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/dipendenti/{dipendente_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/dipendenti/{dipendente_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/dipendenti/{dipendente_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/dipendenti/{dipendente_id}/cessa` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/documenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/documenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/documenti/upload-massivo` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/documenti/{documento_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/documenti/{documento_id}/file` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/ferie` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/ferie` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/ferie-giorno` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/ferie/{ferie_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/ferie/{ferie_id}/approva` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/ferie/{ferie_id}/rifiuta` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/missioni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/missioni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/missioni/{missione_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/missioni/{missione_id}/approva` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/onomastici` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/onomastici` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/onomastici/settimana` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/ordine-dipendenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/ordine-dipendenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/paghe` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe/associazioni-bonifici` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe/associazioni-bonifici/export-excel` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/conferma-associazione` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/correggi-acconti-cedolino` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-bonifici-drive` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-email` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-excel-salari` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-lul` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-pagamenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-prima-nota` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/importa-storico-pagamenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe/in-attesa` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe/pagamento-esito/{key}/pdf` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe/prima-nota` | app.hr.routers.dipendenti_cloud | sì | sì | sì | — | sì | tenere | in uso: FE, scheduler, chat |
| `POST /api/hr/dipendenti-cloud/paghe/sincronizza` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/paghe/sincronizza-bonifici-storici` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/paghe/storico-pagamenti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/presenze` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/batch` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/consolida-da-turni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/presenze/email-commercialista` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/email-commercialista` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/invia-commercialista` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/presenze/invii` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/pdf` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/pdf-riepilogo` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/presenze/riepilogo-dati` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/presenze/{presenza_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/presenze/{presenza_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/prestiti` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/prestiti/{prestito_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/riduzioni-orario` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/riduzioni-orario/scadenze` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/seed-data` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/turni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/turni` | app.hr.routers.dipendenti_cloud | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/turni-chiusura-pomeridiana` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/turni-chiusura-pomeridiana` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/turni-config` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti-cloud/turni-config` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/turni-disponibilita-bar` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/dipendenti-cloud/turni-preferenze` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/dipendenti-cloud/turni/{turno_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/dipendenti-cloud/turni/{turno_id}` | app.hr.routers.dipendenti_cloud | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/dipendenti/bulk-upsert` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/bulk-upsert/preview` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/buste-paga` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/buste-paga` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/buste-paga/dipendente/{dipendente_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/buste-paga/dipendente/{dipendente_id}/import` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/buste-paga/import` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/buste-paga/scan` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/by-google-email` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/contratti` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/contratti` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/contratti` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/contratti/import-excel` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/contratti/scadenze` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/dipendenti/contratti/{contratto_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/dipendenti/contratti/{contratto_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/contratti/{contratto_id}/termina` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/duplicati` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/duplicati/auto-merge` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/duplicati/merge` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/invita-multipli` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/libretti-sanitari` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/libretti-sanitari/all` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/libretti-sanitari/genera-da-dipendenti` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/libretti-sanitari/import-excel` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/libretti-sanitari/scadenze` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/dipendenti/libretti-sanitari/{libretto_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/dipendenti/libretti-sanitari/{libretto_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/libretti/scadenze` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/libro-unico/export-excel` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/libro-unico/presenze` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/libro-unico/salaries` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/dipendenti/libro-unico/salaries/{salary_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/dipendenti/libro-unico/salaries/{salary_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/libro-unico/upload` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/mansioni` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/portale/stats` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/report-ferie-permessi-tutti` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/stats` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/sync-iban` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/tipi-contratto` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/tipi-turno` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/turni/salva` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/turni/settimana` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/dipendenti/{dipendente_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/{dipendente_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/dipendenti/{dipendente_id}` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/{dipendente_id}/fascicolo` | app.hr.routers.employees.fascicolo_dipendente | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/dipendenti/{dipendente_id}/invita-portale` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/{dipendente_id}/kpi` | app.hr.routers.employees.fascicolo_dipendente | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/dipendenti/{dipendente_id}/libretto` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/dipendenti/{dipendente_id}/report-ferie-permessi` | app.hr.routers.employees.dipendenti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/aggiorna-riepilogo` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/alert-limiti` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/giustificativi/codice/{codice}` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/dipendente/{employee_id}/giustificativi` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/giustificativi/dipendente/{employee_id}/giustificativi/limiti` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/dipendente/{employee_id}/riporto-ferie` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/dipendente/{employee_id}/saldo-ferie` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/init-giustificativi` | app.hr.routers.employees.giustificativi | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/hr/giustificativi/presenze-mensili/{employee_id}` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/riepilogo-limiti` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/riepilogo-progressivo/{employee_id}` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/saldi-finali-tutti` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/giustificativi/saldi-finali/{employee_id}` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/giustificativi/saldi-finali/{employee_id}` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/giustificativi/saldi-finali/{employee_id}/periodo` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/salva-saldi-finali` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/sync-giustificativi-da-cedolini` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/upload-libro-unico` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/giustificativi/valida-giustificativo` | app.hr.routers.employees.giustificativi | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/health` | app.hr.router_registry | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/notifiche` | app.hr.routers.notifiche | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/notifiche/conteggio` | app.hr.routers.notifiche | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/hr/notifiche/{notifica_id}/letta` | app.hr.routers.notifiche | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/paghe/acconti` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/acconti/{busta_id}` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/paghe/acconti/{busta_id}/{acconto_id}` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/paghe/buste-paga` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/paghe/distinte-f24` | app.hr.routers.f24_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/paghe/f24/lista` | app.hr.routers.f24_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/import-f24` | app.hr.routers.f24_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/import-libro-unico` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/parse-f24` | app.hr.routers.f24_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/parse-libro-unico` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/parse-libro-unico/dipendente/{indice}` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/paghe/presenze-mensili` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/paghe/presenze-mensili/{codice_fiscale}/{periodo}` | app.hr.routers.libro_unico_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/paghe/riconcilia-f24` | app.hr.routers.f24_parser | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/hr/paghe/riconcilia-stipendi` | app.hr.routers.libro_unico_parser | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/paghe/tributi-pagati` | app.hr.routers.f24_parser | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/portale/buste` | app.hr.routers.portale_buste | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/portale/buste/{cedolino_id}` | app.hr.routers.portale_buste | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/portale/buste/{cedolino_id}/contesta` | app.hr.routers.portale_buste | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/buste/{cedolino_id}/modulo-contestazione` | app.hr.routers.portale_buste | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/buste/{cedolino_id}/pdf` | app.hr.routers.portale_buste | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/portale/buste/{cedolino_id}/presa-visione` | app.hr.routers.portale_buste | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/buste/{cedolino_id}/storico-accessi` | app.hr.routers.portale_buste | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/documenti` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/portale/documenti/admin/upload` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/documenti/modulo/{tipo}` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/portale/documenti/regolamento/accetta` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/documenti/regolamento/file` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/documenti/regolamento/stato` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/documenti/tipi` | app.hr.routers.portale_documenti | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/hr/portale/documenti/upload` | app.hr.routers.portale_documenti | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/hr/portale/documenti/{doc_id}` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/portale/documenti/{doc_id}/file` | app.hr.routers.portale_documenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/richieste` | app.hr.routers.richieste | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/richieste` | app.hr.routers.richieste | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/richieste/mie` | app.hr.routers.richieste | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/richieste/{richiesta_id}/risolvi` | app.hr.routers.richieste | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/salari-v2/ferie-rol` | app.hr.routers.salari_unificati_v2 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/salari-v2/non-pagati` | app.hr.routers.salari_unificati_v2 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/salari-v2/pagamento` | app.hr.routers.salari_unificati_v2 | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/hr/salari-v2/riconcilia-banca` | app.hr.routers.salari_unificati_v2 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/salari-v2/riepilogo` | app.hr.routers.salari_unificati_v2 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/salari-v2/saldo/{codice_fiscale}` | app.hr.routers.salari_unificati_v2 | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/shifts/assegnazioni` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/shifts/assegnazioni` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/shifts/assegnazioni/{assegnazione_id}` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/shifts/schedule` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/shifts/schedule` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/hr/shifts/tipi` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/shifts/tipi` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/hr/shifts/tipi/{turno_id}` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/hr/shifts/tipi/{turno_id}` | app.hr.routers.employees.shifts | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/hr/tfr/accantonamento` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/acconti` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/tfr/acconti/{acconto_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/tfr/acconti/{acconto_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/acconti/{acconto_id}/annulla-riconciliazione-banca` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/acconti/{acconto_id}/candidati-banca` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/acconti/{acconto_id}/riconcilia-banca` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/acconti/{dipendente_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/calcola-batch/{anno}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/calcolo-lordo-da-netto` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/calcolo-netto-da-lordo` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/cedolini/{cedolino_id}/annulla-scalatura-acconti` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/cedolini/{cedolino_id}/preview-scalatura-acconti` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/cedolini/{cedolino_id}/scala-acconti` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/liquidazione` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/parse-payslips` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/riepilogo-aziendale` | app.hr.routers.tfr | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/tfr/simulazione-parametri` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/tfr/simulazione-parametri` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/simulazione/{dipendente_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/simulazione/{dipendente_id}/liquidazione` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/tfr/simulazione/{dipendente_id}/liquidazione-override` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/simulazione/{dipendente_id}/periodi` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/tfr/simulazione/{dipendente_id}/periodi/{periodo_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/hr/tfr/simulazione/{dipendente_id}/periodi/{periodo_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/tfr/simulazione/{dipendente_id}/rate` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/tfr/situazione/{dipendente_id}` | app.hr.routers.tfr | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/hr/tfr/storico-tfr/{dipendente_id}` | app.hr.routers.tfr | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/timbrature` | app.hr.routers.timbrature | sì | sì | sì | — | sì | tenere | in uso: FE, scheduler, chat |
| `POST /api/hr/timbrature` | app.hr.routers.timbrature | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/timbrature/mie/oggi` | app.hr.routers.timbrature | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/timbrature/riepilogo` | app.hr.routers.timbrature | sì | sì | sì | — | sì | tenere | in uso: FE, scheduler, chat |
| `GET /api/hr/timbrature/sede` | app.hr.routers.timbrature | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/timbrature/sede` | app.hr.routers.timbrature | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/turni` | app.hr.routers.turni | sì | sì | sì | — | sì | tenere | in uso: FE, scheduler, chat |
| `GET /api/hr/turni/azienda/settimana` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/turni/disponibilita-bar` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/turni/disponibilita-bar` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/hr/turni/disponibilita-bar/{disp_id}` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/turni/genera` | app.hr.routers.turni | sì | sì | sì | — | sì | tenere | in uso: FE, scheduler, chat |
| `GET /api/hr/turni/miei/corrente` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/turni/preferenza-riposo` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/turni/preferenza-riposo` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/hr/turni/{settimana_inizio}` | app.hr.routers.turni | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `PUT /api/hr/turni/{settimana_inizio}/cella` | app.hr.routers.turni | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/hr/turni/{settimana_inizio}/pubblica` | app.hr.routers.turni | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/hr/turni/{settimana_inizio}/sblocca` | app.hr.routers.turni | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/integrations/lotti/employees` | lotti_integration | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/integrations/lotti/invoices` | lotti_integration | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/integrations/lotti/invoices/{source_id}` | lotti_integration | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/invoices` | invoices.invoices_main | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/invoices/bank-pending` | invoices.invoices_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/invoices/by-month/{year}/{month}` | invoices.invoices_main | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/invoices/emesse` | invoices.invoices_emesse | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/invoices/emesse` | invoices.invoices_emesse | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/invoices/emesse/{invoice_id}` | invoices.invoices_emesse | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/invoices/emesse/{invoice_id}` | invoices.invoices_emesse | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/invoices/{invoice_id}` | invoices.invoices_main | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/iva/anomalie` | iva | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/iva/dashboard/{anno}/{mese}` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/iva/fatture` | iva | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/iva/fatture/non-utilizzate` | iva | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/iva/fatture/{fid}/correggi-periodo` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/fatture/{fid}/escludi` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/fatture/{fid}/includi` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/fatture/{fid}/indetraibile` | iva | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/iva/fatture/{fid}/recupero-annuale` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/fatture/{fid}/rinvia` | iva | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/iva/liquidazioni` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/liquidazioni/calcola` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/liquidazioni/{liq_id}/conferma` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/liquidazioni/{liq_id}/rettifica` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/liquidazioni/{liq_id}/riapri` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/iva/liquidazioni/{periodo}` | iva | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/iva/ricalcola-attribuzione` | iva | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/iva/ricalcola-attribuzione/ultimo` | iva | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/iva/riepilogo-annuale/{anno}` | iva | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/iva/versamento/{anno}/{mese}` | iva | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/learning-machine/dashboard` | learning_machine | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/learning-machine/documenti` | learning_machine | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/learning-machine/feedback` | learning_machine | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/learning-machine/regole-apprese` | learning_machine | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/learning-machine/reset-learning` | learning_machine | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/learning-machine/scan` | learning_machine | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/learning-machine/statistiche-feedback` | learning_machine | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/learning-universal/apply-suggestions` | learning_universal | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/learning-universal/results` | learning_universal | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/learning-universal/status` | learning_universal | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/learning-universal/suggestions/{module}` | learning_universal | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/learning-universal/train/all` | learning_universal | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/mutui` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/mutui/` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/mutui/` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/mutui/import-pdf` | mutui_parser | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/mutui/parse-multiple` | mutui_parser | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/mutui/parse-pdf` | mutui_parser | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/mutui/riconcilia` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/mutui/statistiche/dashboard` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/mutui/{mutuo_id}` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/mutui/{mutuo_id}` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/mutui/{mutuo_id}` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/mutui/{mutuo_id}/rate` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/mutui/{mutuo_id}/rate/{numero_rata}/riconcilia` | mutui | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/nexi/movimenti` | nexi_carta | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/nexi/stato` | nexi_carta | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/nexi/upload-pdf` | nexi_carta | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/nexi/verifica` | nexi_carta | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/noleggio/associa-fornitore` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/noleggio/controllo-canoni` | noleggio | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/noleggio/drivers` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/noleggio/export-pdf-costi` | noleggio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/noleggio/fatture-non-associate` | noleggio | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/noleggio/fatture/{fattura_id}/associa-veicolo` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/noleggio/fornitori` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/noleggio/riepilogo-controlli` | noleggio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/noleggio/veicoli` | noleggio | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/noleggio/veicoli` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/noleggio/veicoli/{targa}` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/noleggio/veicoli/{targa}` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/noleggio/veicoli/{targa}/completo` | noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/noleggio/verbali-dipendente` | noleggio | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/openapi-automotive/aggiorna-veicolo` | openapi_automotive | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi-automotive/assicurazione/{targa}` | openapi_automotive | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi-automotive/info/{targa}` | openapi_automotive | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi-automotive/status` | openapi_automotive | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi-automotive/veicoli-da-aggiornare` | openapi_automotive | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/openapi-imprese/aggiorna-fornitore` | openapi_imprese | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi-imprese/cerca` | openapi_imprese | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi-imprese/info/{partita_iva}` | openapi_imprese | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi-imprese/pec/{partita_iva}` | openapi_imprese | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi-imprese/sdi/{partita_iva}` | openapi_imprese | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi-imprese/status` | openapi_imprese | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/openapi/aisp/connetti-conto` | openapi_it | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi/aisp/movimenti` | openapi_it | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi/aisp/status` | openapi_it | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/openapi/visure/richiedi` | openapi_it | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/openapi/xbrl/bilancio/{request_id}` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi/xbrl/download/{request_id}` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi/xbrl/download/{request_id}/{tipo}` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/openapi/xbrl/richiedi-bilancio` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/openapi/xbrl/richiedi-riclassificato` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi/xbrl/status` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/openapi/xbrl/storico-richieste` | openapi_it | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/analizza` | operazioni_module.smart | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/analizza-anomalie` | operazioni_module.smart | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/banca-veloce` | operazioni_module.smart | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/cerca-f24` | operazioni_module.smart | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/cerca-fatture` | operazioni_module.smart | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/cerca-stipendi` | operazioni_module.smart | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/operazioni-da-confermare/smart/conferma-f24` | operazioni_module.smart | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/operazioni-da-confermare/smart/ignora` | operazioni_module | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/operazioni-da-confermare/smart/movimento/{movimento_id}` | operazioni_module.smart | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/operazioni-da-confermare/smart/riconcilia-manuale` | operazioni_module.smart | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/operazioni-da-confermare/smart/riconcilia-stipendio` | operazioni_module | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/pagamenti-buoni` | pagamenti_buoni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/pagamenti-buoni/import` | pagamenti_buoni | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/pagamenti/assegno-multi-fatture` | multi_pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/pagamenti/fattura-multi-metodo` | multi_pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pagamenti/fattura/{fattura_id}` | multi_pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/pagamenti/registra` | multi_pagamento | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/pagamenti/riepilogo-fornitore/{piva}` | multi_pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/pagamenti/{pagamento_id}` | multi_pagamento | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/pagopa/auto-associa` | pagopa | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/pagopa/cerca-movimenti-pagopa` | pagopa | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pagopa/movimenti-agenzia-entrate` | pagopa | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pagopa/ricevute` | pagopa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/pagopa/ricevute/associa-manuale` | pagopa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/pagopa/ricevute/upload` | pagopa | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/pagopa/ricevute/{ricevuta_id}/pdf` | pagopa | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/pagopa/stats` | pagopa | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/partite-aperte/lista` | partite_aperte_api | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/partite-aperte/scadute` | partite_aperte_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/partite-aperte/stats` | partite_aperte_api | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-api/account-ids-non-mappati` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-api/account/{paypal_account_id}/cerca-fattura-email` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-api/crea-fornitore-e-mappa` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-api/mappa-fornitore` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-api/ricevuta-pdf/{transaction_id}` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-api/riconcilia` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-api/smappa-fornitore` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-api/status` | paypal_api | sì | sì | sì | — | sì | tenere | in uso: FE, scheduler, chat |
| `POST /api/paypal-api/sync` | paypal_api | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/paypal-api/sync/incremental` | paypal_api | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/paypal-api/sync/month` | paypal_api | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/paypal-api/webhook` | paypal_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-statements/auto-associa` | paypal_statements | — | sì | — | — | sì | tenere | in uso: scheduler |
| `POST /api/paypal-statements/auto-cerca-gmail` | paypal_statements | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-statements/bank-movements` | paypal_statements | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/paypal-statements/dashboard` | paypal_statements | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/paypal-statements/import-all-local` | paypal_statements | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-statements/import-csv` | paypal_statements | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-statements/import-pdf` | paypal_statements | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-statements/pulisci-match-solo-importo` | paypal_statements | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-statements/report` | paypal_statements | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/paypal-statements/riconcilia-banca` | paypal_statements | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/paypal-statements/riprocessa` | paypal_statements | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/paypal-statements/statements` | paypal_statements | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/paypal-statements/transactions` | paypal_statements | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/paypal-statements/transactions/{transaction_id}/descrizione` | paypal_statements | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/paypal-statements/transazione/{transaction_id}/associa` | paypal_statements | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-statements/transazione/{transaction_id}/cerca-gmail` | paypal_statements | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/paypal-statements/transazione/{transaction_id}/dettaglio` | paypal_statements | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pianificazione/costi-previsionali` | pianificazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/pianificazione/costi-previsionali` | pianificazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/pianificazione/costi-previsionali/{costo_id}` | pianificazione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pianificazione/events` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/pianificazione/events` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/piano-conti/` | accounting.piano_conti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/piano-conti/` | accounting.piano_conti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/piano-conti/bilancio` | accounting.piano_conti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/piano-conti/conto/{codice}/movimenti` | accounting.piano_conti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/piano-conti/movimenti` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/piano-conti/registra-corrispettivi` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/piano-conti/registra-fattura` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/piano-conti/registra-tutte-fatture` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/piano-conti/regole` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/piano-conti/regole` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/piano-conti/{conto_id}` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/piano-conti/{conto_id}` | accounting.piano_conti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/portal/upload` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pos-corrispettivi/alert-oggi` | pos_corrispettivi_check | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pos-corrispettivi/anomalie-gravi` | pos_corrispettivi_check | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/pos-corrispettivi/chiusura-giornaliera` | pos_corrispettivi_check | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/pos-corrispettivi/chiusura-giornaliera/audit` | pos_corrispettivi_check | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/pos-corrispettivi/chiusure-giornaliere/batch` | pos_corrispettivi_check | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/pos-corrispettivi/controllo-due-fasi` | pos_corrispettivi_check | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/pos-corrispettivi/riconcilia-pos-giorno` | pos_corrispettivi_check | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/pos-corrispettivi/riepilogo-mensile` | pos_corrispettivi_check | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/pos-corrispettivi/verifica-coerenza` | pos_corrispettivi_check | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/previsioni-acquisti/confronto-ordine` | previsioni_acquisti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/previsioni-acquisti/popola-storico` | previsioni_acquisti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/previsioni-acquisti/previsioni` | previsioni_acquisti | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/previsioni-acquisti/prodotti` | previsioni_acquisti | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/previsioni-acquisti/statistiche` | previsioni_acquisti | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota-salari/consolida-record` | accounting.prima_nota_salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota-salari/dipendenti-lista` | accounting.prima_nota_salari | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota-salari/export-appdipendenti/download` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota-salari/export-appdipendenti/preview` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota-salari/export-excel` | accounting.prima_nota_salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota-salari/import-bonifici` | accounting.prima_nota_salari | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota-salari/import-paghe` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota-salari/import-salari-ricostruiti` | accounting.prima_nota_salari | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota-salari/import-salari-verificati` | accounting.prima_nota_salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/prima-nota-salari/pulisci-righe-vuote` | accounting.prima_nota_salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota-salari/ricalcola-progressivi` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota-salari/salari` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota-salari/salari-ricostruiti` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota-salari/salari/aggiustamento` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota-salari/salari/reset` | accounting.prima_nota_salari | sì | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/prima-nota-salari/salari/riepilogo` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota-salari/salari/{record_id}` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/prima-nota-salari/salari/{record_id}` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota-salari/salari/{record_id}/bonifico-pdf` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota-salari/salari/{record_id}/bonifico-pdf` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota-salari/salari/{record_id}/cedolino-pdf` | accounting.prima_nota_salari | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota-salari/salari/{record_id}/cedolino-pdf` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/prima-nota-salari/salari/{record_id}/riconcilia` | accounting.prima_nota_salari | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/anni-disponibili` | prima_nota_module.stats | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/annulla-associazione-fattura-banca` | prima_nota_module.manutenzione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/arricchisci-pagamenti-banca` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/banca` | prima_nota_module.banca | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/banca` | prima_nota_module.banca | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota/banca/analisi-righe-grezze` | prima_nota_module.banca | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/banca/candidati-per-fattura` | prima_nota_module.banca | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/banca/delete-all` | prima_nota_module.banca | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/banca/delete-by-source/{source}` | prima_nota_module.banca | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/banca/in-attesa-documento` | prima_nota_module.banca | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/banca/sync-estratto-conto` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/banca/template-csv` | prima_nota_module | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/banca/{movimento_id}` | prima_nota_module.banca | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/prima-nota/banca/{movimento_id}` | prima_nota_module.banca | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota/banca/{movimento_id}/fattura` | prima_nota_module.banca | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/cassa` | prima_nota_module.cassa | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/cassa` | prima_nota_module.cassa | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota/cassa/analisi-movimenti-bancari-errati` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/cassa/crea-entrata-da-corrispettivo` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/cassa/delete-all` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/cassa/delete-by-source/{source}` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/cassa/elimina-movimenti-bancari-errati` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/cassa/fix-corrispettivi-importo` | prima_nota_module.manutenzione | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/cassa/sync-corrispettivi` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/cassa/sync-fatture-pagate` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota/cassa/template-csv` | prima_nota_module | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/cassa/verifica-entrate-corrispettivi` | prima_nota_module.manutenzione | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/prima-nota/cassa/{movimento_id}` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/prima-nota/cassa/{movimento_id}` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/cassa/{movimento_id}/fattura` | prima_nota_module.cassa | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/cleanup-orphan-movements` | prima_nota_module.manutenzione | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/prima-nota/collega-banca-estratto-conto` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/collega-corrispettivi` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/collega-fatture` | prima_nota_module.sync | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/corrispettivi-status` | prima_nota_module.sync | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/dedup-fatture` | prima_nota_module.manutenzione | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/dedup-righe-estratto-conto` | prima_nota_module.manutenzione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/diagnostica-corrispettivi` | prima_nota_module.manutenzione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/diagnostica-metodi` | prima_nota_module.manutenzione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/export/excel` | prima_nota_module.stats | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/fix-categories-and-duplicates` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/fix-date-formato-italiano` | prima_nota_module.manutenzione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/fix-tipo-movimento` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/fix-versamenti-duplicati` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/import-batch` | prima_nota_module.sync | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/indice-operazioni` | prima_nota_module.operation_index | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/prima-nota/indice-operazioni/{movement_id}` | prima_nota_module.operation_index | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota/indice-operazioni/{movement_id}/candidati` | prima_nota_module.operation_index | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/migra-pos-accrediti-reali` | prima_nota_module.manutenzione | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/prima-nota/migrazione-pulisci-bancari-cassa` | prima_nota_module.manutenzione | — | — | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `GET /api/prima-nota/movimenti-ec-non-in-prima-nota` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/movimento` | prima_nota_module.sync | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/provvisori` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/annulla-auto-conferma` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/provvisori/assegni-proposti` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/associa-assegno` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/attendi-banca` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/auto-conferma-per-metodo` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/conferma` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/conferma-divisione` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/conferma-multipla` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/da-decidere` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/provvisori/segnala-dubbio` | prima_nota_module.sync | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/pulizia-pre-anno` | prima_nota_module.manutenzione | — | — | — | sì | sì | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/prima-nota/recalculate-balances` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/regenerate-from-invoices` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/registra-fattura` | prima_nota_module.sync | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/ripristina-fatture-movimento-cancellato` | prima_nota_module.manutenzione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/ripristina-provvisori-metodo-errato` | prima_nota_module.manutenzione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/salari` | prima_nota_module.salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/salari` | prima_nota_module.salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/salari/stats` | prima_nota_module.salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/prima-nota/salari/{movimento_id}` | prima_nota_module.salari | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/saldi-finanziari` | prima_nota_module.stats | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/saldo-finale` | prima_nota_module.stats | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/saldo-iniziale` | prima_nota_module.stats | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/prima-nota/saldo-iniziale` | prima_nota_module.stats | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/prima-nota/saldo-iniziale/{tipo}/{anno}` | prima_nota_module.stats | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/sposta-cassa-pagate-in-banca` | prima_nota_module.sync | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/sposta-movimento` | prima_nota_module.manutenzione | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/sposta-scrittura` | prima_nota_module.sync | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/prima-nota/stats` | prima_nota_module.stats | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/prima-nota/sumup` | prima_nota_module.banca | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/prima-nota/sync-corrispettivi` | prima_nota_module.sync | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/prima-nota/unifica-categorie` | prima_nota_module.manutenzione | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/prima-nota/verifica-metodo-fattura/{fattura_id}` | prima_nota_module.manutenzione | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/privacy` | legal_pages | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/proposte` | dati_provvisori | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/rapido/acconto-dipendente` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/rapido/apporto-soci` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/rapido/corrispettivo` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/rapido/dipendenti-attivi` | rapido | sì | — | sì | — | sì | tenere | in uso: FE, chat |
| `POST /api/rapido/paga-fattura` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/rapido/presenza` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/rapido/ultimi-inserimenti` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/rapido/versamento-banca` | rapido | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/regole` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/regole/categorie` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/regole/descrizione` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/regole/download-regole` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/regole/elimina/{tipo}/{pattern}` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/regole/fornitore` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/regole/upload-regole` | accounting.regole_categorizzazione | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/ricerca-globale` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/riconciliazione/stats` | riconciliazione_stats_api | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/rifiuta/{proposta_id}` | dati_provvisori | — | sì | — | — | sì | tenere | in uso: scheduler |
| `GET /api/ritenute` | ritenute | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/ritenute/codici-ravvedimento` | ritenute | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/ritenute/scan` | ritenute | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/ritenute/verifica-caso-1040` | ritenute | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenzario-fornitori/` | scadenzario_fornitori | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/scadenzario-fornitori/aggiorna-scadenza` | scadenzario_fornitori | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenzario-fornitori/aging` | scadenzario_fornitori | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenzario-fornitori/cash-flow-previsionale` | scadenzario_fornitori | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenzario-fornitori/scadenze-integrate` | scadenzario_fornitori | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenzario-fornitori/urgenti` | scadenzario_fornitori | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenze` | scadenze | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/scadenze/` | scadenze | sì | — | — | — | sì | tenere | in uso: FE |
| `PUT /api/scadenze/completa/{notifica_id}` | scadenze | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/scadenze/crea` | scadenze | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenze/dashboard-widget` | scadenze | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenze/iva-mensile/{anno}` | scadenze | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/scadenze/prossime` | scadenze | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/scadenze/tutte` | scadenze | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/scadenze/{notifica_id}` | scadenze | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/settings` | settings | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/settings` | settings | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/settings/anthropic` | settings_router | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/settings/anthropic` | settings_router | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/settings/anthropic/test` | settings_router | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/settings/gmail` | settings_router | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/settings/gmail` | settings_router | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/settings/gmail/test` | settings_router | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/settings/logo` | settings | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/settings/logo` | settings | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/settings/openai` | settings_router | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/settings/openai` | settings_router | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/settings/openai/test` | settings_router | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/settings/user-preferences` | settings | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/settings/user-preferences` | settings | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/sumup/bonifica-accrediti-numia` | sumup | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/sumup/bonifica-pos-xml` | sumup | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/sumup/bonifica-pos-xml` | sumup | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/sumup/normalizza-descrizioni-pos` | sumup | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/sumup/riepilogo` | sumup | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/sumup/sincronizza` | sumup | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/sumup/stato` | sumup | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/suppliers` | suppliers_module.base | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/suppliers` | suppliers_module.base | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/suppliers-legacy` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/suppliers/aggiorna-dizionario-metodo` | suppliers_module.validation | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/aggiorna-metodi-bulk` | suppliers_module.bulk | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/aggiorna-tutti-bulk` | suppliers_module.bulk | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/correggi-nomi-mancanti` | suppliers_module.bulk | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/dizionario-metodi-pagamento` | suppliers_module.validation | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/elimina-senza-fatture` | suppliers_module.bulk | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/filtered` | suppliers_module.base | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/suppliers/import-excel` | suppliers_module.import_export | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/payment-methods` | suppliers_module.validation | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/payment-terms` | suppliers_module.validation | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/ricerca-iban-singolo/{supplier_id}` | suppliers_module.iban | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/ricerca-iban-web` | suppliers_module.iban | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/ripara-sconosciuti` | suppliers_module.bulk | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/scadenze` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/search-piva/{partita_iva}` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/sincronizza-da-fatture` | suppliers_module.bulk | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/stats` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/sync-iban` | suppliers_module.iban | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/upload-excel` | suppliers_module.import_export | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/validazione-p0` | suppliers_module.validation | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/suppliers/{supplier_id}` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/{supplier_id}` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/suppliers/{supplier_id}` | suppliers_module.base | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/suppliers/{supplier_id}/dati-da-fatture` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/{supplier_id}/fatturato` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/{supplier_id}/fatture` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/{supplier_id}/iban-from-invoices` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/suppliers/{supplier_id}/inventory` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/suppliers/{supplier_id}/metodo-pagamento` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/suppliers/{supplier_id}/nome` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/suppliers/{supplier_id}/toggle-active` | suppliers_module.base | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/sync/fatture-cassa-dettaglio` | sync_relazionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/sync/match-fatture-banca` | sync_relazionale | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/sync/match-fatture-cassa` | sync_relazionale | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/sync/stato-sincronizzazione` | sync_relazionale | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/sync/sync-all-corrispettivi` | sync_relazionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/sync/sync-corrispettivo/{corrispettivo_id}` | sync_relazionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/sync/sync-fattura/{fattura_id}` | sync_relazionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/sync/update-fattura-everywhere/{fattura_id}` | sync_relazionale | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/terms` | legal_pages | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/accantonamento` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/acconti` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `DELETE /api/tfr/acconti/{acconto_id}` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `PUT /api/tfr/acconti/{acconto_id}` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/acconti/{acconto_id}/annulla-riconciliazione-banca` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/tfr/acconti/{acconto_id}/candidati-banca` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/acconti/{acconto_id}/riconcilia-banca` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/tfr/acconti/{dipendente_id}` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/calcola-batch/{anno}` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/cedolini/{cedolino_id}/annulla-scalatura-acconti` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/tfr/cedolini/{cedolino_id}/preview-scalatura-acconti` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/cedolini/{cedolino_id}/scala-acconti` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/tfr/liquidazione` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/tfr/parse-payslips` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/tfr/riepilogo-aziendale` | tfr | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/tfr/situazione/{dipendente_id}` | tfr | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/tfr/storico-tfr/{dipendente_id}` | tfr | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/utenti` | utenti | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/utenti` | utenti | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/utenti/{utente_id}` | utenti | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/utenti/{utente_id}` | utenti | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/v1/fatture` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/v1/keys` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/v1/keys/generate` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/v1/movimenti` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/v1/stats` | public_api | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/verbali-noleggio/associa-pdf/{numero_verbale:path}` | verbali_noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/verbali-noleggio/correggi-importo/{numero_verbale:path}` | verbali_noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/verbali-noleggio/correggi-trasgressore/{numero_verbale:path}` | verbali_noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/verbali-noleggio/dettaglio/{numero_verbale:path}` | verbali_noleggio_api | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `GET /api/verbali-noleggio/dettaglio/{numero_verbale}` | verbali_noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/verbali-noleggio/pdf/{numero_verbale:path}` | verbali_noleggio | sì | — | — | — | sì | tenere | in uso: FE |
| `POST /api/verbali-noleggio/ricalcola-pdf/{numero_verbale:path}` | verbali_noleggio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/verbali-noleggio/verbali-completi` | verbali_noleggio | — | — | sì | — | — | tenere | in uso: chat |
| `POST /api/verbali-noleggio/{verbale_id}/upload-quietanza` | verbali_noleggio_api | — | sì | — | — | — | tenere | in uso: scheduler |
| `POST /api/verbali-riconciliazione/collega-driver-massivo` | verbali_riconciliazione | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `GET /api/verbali-riconciliazione/dashboard` | verbali_riconciliazione | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/verbali-riconciliazione/import-partenopay` | verbali_riconciliazione | — | sì | — | — | — | tenere | in uso: scheduler |
| `GET /api/verbali-riconciliazione/lista` | verbali_riconciliazione | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/verbali-riconciliazione/migra-attesa-quietanza` | verbali_riconciliazione | sì | sì | — | sì | — | admin-only | endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7) |
| `POST /api/verbali-riconciliazione/pulisci-duplicati` | verbali_riconciliazione | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/verbali-riconciliazione/riconcilia/{numero_verbale}` | verbali_riconciliazione | sì | sì | — | — | sì | tenere | in uso: FE, scheduler |
| `POST /api/verbali-riconciliazione/scan-email` | verbali_riconciliazione | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/verbali-riconciliazione/scan-fatture-verbali` | verbali_riconciliazione | sì | sì | — | — | — | tenere | in uso: FE, scheduler |
| `POST /api/verbali-riconciliazione/scan-gmail-attendibili` | verbali_riconciliazione | — | sì | — | — | sì | tenere | in uso: scheduler |
| `GET /api/verifica-coerenza/completa/{anno}` | verifica_coerenza | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/verifica-coerenza/confronto-iva-completo/{anno}` | verifica_coerenza | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/verifica-coerenza/discrepanze/{anno}` | verifica_coerenza | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/verifica-coerenza/iva/{anno}/{mese}` | verifica_coerenza | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/verifica-coerenza/riepilogo-giornaliero` | verifica_coerenza | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/verifica-coerenza/verifica-bonifici-vs-banca/{anno}` | verifica_coerenza | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/verifica-coerenza/widget` | verifica_coerenza | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/voci-bilancio/` | voci_bilancio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/voci-bilancio/codici-disponibili` | voci_bilancio | sì | — | — | — | — | tenere | in uso: FE |
| `GET /api/voci-bilancio/{anno}` | voci_bilancio | sì | — | — | — | sì | tenere | in uso: FE |
| `DELETE /api/voci-bilancio/{voce_id}` | voci_bilancio | sì | — | — | — | sì | tenere | in uso: FE |
| `GET /api/warehouse/movements` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `POST /api/warehouse/movements` | public_api | — | — | — | — | — | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /api/warehouse/products` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `POST /api/warehouse/products` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `DELETE /api/warehouse/products/{product_id}` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `PUT /api/warehouse/products/{product_id}` | public_api | sì | — | — | — | — | tenere | in uso: FE |
| `GET /data-deletion` | legal_pages | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /privacy` | legal_pages | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |
| `GET /terms` | legal_pages | — | — | — | — | sì | verificare | nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare |

## Note operative (§7)
- Gli endpoint marcati **deprecare** sono di migrazione/manutenzione one-shot: devono essere Admin-only, disabilitabili, documentati e non esposti a lungo.
- Gli endpoint **verificare** non hanno riferimenti noti automatici: verificare manualmente (potrebbero essere chiamati via strumenti esterni/Postman) prima di deprecare. NON eliminare in blocco.
