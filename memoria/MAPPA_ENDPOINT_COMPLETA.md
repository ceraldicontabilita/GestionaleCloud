# MAPPA ENDPOINT COMPLETA — GestionaleCloud

> rigenerata via scripts/genera_mappa.py. Ogni endpoint REALMENTE montato, per gruppo (tag).
> Totale **1112 endpoint** in **114 gruppi**.
> FE: `✓` usato dal frontend · `ext` chiamante esterno · `—` nessun riferimento noto.

**Riepilogo uso:** ✓ frontend = 671 · ext esterni = 88 · — da verificare = 353

## AI Parser  (11)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/ai-parser/batch-parse` | ext | ai_parser |
| GET | `/api/ai-parser/da-rivedere` | ext | ai_parser |
| POST | `/api/ai-parser/da-rivedere/process-batch` | ext | ai_parser |
| PUT | `/api/ai-parser/da-rivedere/{document_id}/classifica` | ext | ai_parser |
| POST | `/api/ai-parser/parse` | ext | ai_parser |
| POST | `/api/ai-parser/parse-busta-paga` | ext | ai_parser |
| POST | `/api/ai-parser/parse-f24` | ext | ai_parser |
| POST | `/api/ai-parser/parse-fattura` | ext | ai_parser |
| POST | `/api/ai-parser/process-email-batch` | ext | ai_parser |
| GET | `/api/ai-parser/statistiche` | ext | ai_parser |
| GET | `/api/ai-parser/test` | ext | ai_parser |

## Admin  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| DELETE | `/api/admin/cleanup-trattenute-disciplinari` | — | admin |
| GET | `/api/admin/collections` | — | admin |
| GET | `/api/admin/dashboard-summary` | ✓ | admin |
| POST | `/api/admin/noleggio/backfill-dati-gestionali` | — | admin |
| POST | `/api/admin/reset-collections` | — | admin |
| GET | `/api/admin/stats` | ✓ | admin |
| GET | `/api/admin/year-opening-balances/{year}` | — | admin |
| PUT | `/api/admin/year-opening-balances/{year}` | — | admin |

## Admin Export  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/admin/export` | — | admin_export |
| GET | `/api/admin/export/{filename}` | — | admin_export |

## Admin Rollback  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/admin/rollback/drive-fatture/conta` | — | admin_rollback |
| POST | `/api/admin/rollback/drive-fatture/elimina` | — | admin_rollback |
| POST | `/api/admin/rollback/fatture/azzera-tutto` | — | admin_rollback |
| GET | `/api/admin/rollback/fatture/azzera-tutto/conta` | — | admin_rollback |
| GET | `/api/admin/rollback/sezioni` | ✓ | admin_rollback |
| DELETE | `/api/admin/rollback/{sezione}` | ✓ | admin_rollback |
| GET | `/api/admin/rollback/{sezione}/conta` | ✓ | admin_rollback |

## Agenti AI  (16)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/agenti/automazioni/ferma` | ext | agenti |
| POST | `/api/agenti/automazioni/riprendi` | ext | agenti |
| GET | `/api/agenti/automazioni/stato` | ext | agenti |
| GET | `/api/agenti/cash-flow-13-settimane` | ext | agenti |
| GET | `/api/agenti/decisioni` | ext | agenti |
| POST | `/api/agenti/decisioni/{decision_id}/approva` | ext | agenti |
| GET | `/api/agenti/decisioni/{decision_id}/eventi` | ext | agenti |
| POST | `/api/agenti/decisioni/{decision_id}/rifiuta` | ext | agenti |
| GET | `/api/agenti/pattern-appresi` | ext | agenti |
| POST | `/api/agenti/run` | ext | agenti |
| GET | `/api/agenti/segnalazioni` | ext | agenti |
| GET | `/api/agenti/segnalazioni/count` | ext | agenti |
| GET | `/api/agenti/segnalazioni/summary` | ext | agenti |
| PUT | `/api/agenti/segnalazioni/{sid}/letta` | ext | agenti |
| PUT | `/api/agenti/segnalazioni/{sid}/risolta` | ext | agenti |
| GET | `/api/agenti/stato` | ext | agenti |

## Alert  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/alerts/fornitori-senza-metodo` | — | alerts |
| GET | `/api/alerts/lista` | ✓ | alerts |
| POST | `/api/alerts/risolvi-fornitore/{fornitore_piva}` | — | alerts |
| GET | `/api/alerts/summary` | ✓ | alerts |
| DELETE | `/api/alerts/{alert_id}` | ✓ | alerts |
| POST | `/api/alerts/{alert_id}/risolvi` | ✓ | alerts |
| POST | `/api/alerts/{alert_id}/segna-letto` | ✓ | alerts |

## Anagrafica Fornitori  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/anagrafica-fornitori/popola-fornitore/{fornitore_id}` | ✓ | anagrafica_fornitori_xml |
| POST | `/api/anagrafica-fornitori/popola-tutti` | ✓ | anagrafica_fornitori_xml |

## Archivio Bonifici  (19)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/archivio-bonifici/associa-dipendenti` | — | bonifici_module.riconciliazione |
| GET | `/api/archivio-bonifici/dashboard` | — | bonifici_module.riconciliazione |
| GET | `/api/archivio-bonifici/download-zip/{year}` | ✓ | bonifici_module.transfers |
| GET | `/api/archivio-bonifici/export` | ✓ | bonifici_module.transfers |
| POST | `/api/archivio-bonifici/jobs` | — | bonifici_module.jobs |
| GET | `/api/archivio-bonifici/jobs` | — | bonifici_module.jobs |
| GET | `/api/archivio-bonifici/jobs/{job_id}` | — | bonifici_module.jobs |
| POST | `/api/archivio-bonifici/jobs/{job_id}/upload` | — | bonifici_module.jobs |
| POST | `/api/archivio-bonifici/reset-riconciliazione` | — | bonifici_module.riconciliazione |
| POST | `/api/archivio-bonifici/riconcilia` | ✓ | bonifici_module.riconciliazione |
| GET | `/api/archivio-bonifici/riconcilia/task/{task_id}` | ✓ | bonifici_module.riconciliazione |
| GET | `/api/archivio-bonifici/stato-riconciliazione` | ✓ | bonifici_module.riconciliazione |
| GET | `/api/archivio-bonifici/transfers` | ✓ | bonifici_module.transfers |
| DELETE | `/api/archivio-bonifici/transfers/bulk` | ✓ | bonifici_module.transfers |
| GET | `/api/archivio-bonifici/transfers/count` | ✓ | bonifici_module.transfers |
| GET | `/api/archivio-bonifici/transfers/summary` | ✓ | bonifici_module.transfers |
| DELETE | `/api/archivio-bonifici/transfers/{transfer_id}` | ✓ | bonifici_module.transfers |
| PUT | `/api/archivio-bonifici/transfers/{transfer_id}` | ✓ | bonifici_module.transfers |
| GET | `/api/archivio-bonifici/transfers/{transfer_id}/pdf` | ✓ | bonifici_module.transfers |

## Assegni  (33)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/assegni` | ✓ | bank.assegni |
| GET | `/api/assegni/ambigui` | ✓ | bank.assegni |
| POST | `/api/assegni/associa-beneficiari-robusto` | ✓ | bank.assegni |
| POST | `/api/assegni/associa-pagamenti-multipli` | ✓ | bank.assegni |
| POST | `/api/assegni/auto-associa` | ✓ | bank.assegni |
| POST | `/api/assegni/auto-match` | ✓ | bank.assegni |
| POST | `/api/assegni/auto-match/conferma` | ✓ | bank.assegni |
| POST | `/api/assegni/cerca-combinazioni-assegni` | ✓ | bank.assegni |
| DELETE | `/api/assegni/clear-generated` | ✓ | bank.assegni |
| POST | `/api/assegni/conferma-proposta/{proposta_id}` | ✓ | bank.assegni |
| PUT | `/api/assegni/correggi-associazione/{assegno_id}` | ✓ | bank.assegni |
| POST | `/api/assegni/correggi-numeri` | ✓ | bank.assegni |
| POST | `/api/assegni/genera` | ✓ | bank.assegni |
| GET | `/api/assegni/preview-combinazioni` | ✓ | bank.assegni |
| GET | `/api/assegni/proposte-associazione` | ✓ | bank.assegni |
| POST | `/api/assegni/pulisci-beneficiari-fittizi` | ✓ | bank.assegni |
| POST | `/api/assegni/ricostruisci-dati` | ✓ | bank.assegni |
| POST | `/api/assegni/rifiuta-proposta/{proposta_id}` | ✓ | bank.assegni |
| POST | `/api/assegni/riprocessa-collegamenti` | ✓ | bank.assegni |
| GET | `/api/assegni/senza-associazione` | ✓ | bank.assegni |
| GET | `/api/assegni/stati` | ✓ | bank.assegni |
| GET | `/api/assegni/stats` | ✓ | bank.assegni |
| GET | `/api/assegni/supporto/fatture-disponibili` | ✓ | bank.assegni |
| POST | `/api/assegni/sync-da-estratto-conto` | ✓ | bank.assegni |
| GET | `/api/assegni/verifica-associazioni` | ✓ | bank.assegni |
| GET | `/api/assegni/{assegno_id}` | ✓ | bank.assegni |
| PUT | `/api/assegni/{assegno_id}` | ✓ | bank.assegni |
| DELETE | `/api/assegni/{assegno_id}` | ✓ | bank.assegni |
| POST | `/api/assegni/{assegno_id}/annulla` | ✓ | bank.assegni |
| POST | `/api/assegni/{assegno_id}/emetti` | ✓ | bank.assegni |
| PUT | `/api/assegni/{assegno_id}/fatture-collegate` | ✓ | bank.assegni |
| POST | `/api/assegni/{assegno_id}/incassa` | ✓ | bank.assegni |
| POST | `/api/assegni/{assegno_id}/risolvi-ambiguo` | ✓ | bank.assegni |

## Assegni Learning  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/assegni/learning/associa-combinazioni-avanzato` | ✓ | bank.assegni_learning |
| POST | `/api/assegni/learning/associa-intelligente` | ✓ | bank.assegni_learning |
| POST | `/api/assegni/learning/learn` | ✓ | bank.assegni_learning |
| POST | `/api/assegni/learning/pulizia-duplicati` | ✓ | bank.assegni_learning |
| GET | `/api/assegni/learning/stats-avanzate` | ✓ | bank.assegni_learning |
| GET | `/api/assegni/learning/suggerimenti/{importo}` | ✓ | bank.assegni_learning |

## Assistente Ceraldi  (11)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/assistente/cases` | — | assistente_operativo |
| GET | `/api/assistente/dashboard` | ✓ | assistente_operativo |
| POST | `/api/assistente/facts/driver-assignment` | — | assistente_operativo |
| POST | `/api/assistente/knowledge-sources/official` | — | assistente_operativo |
| POST | `/api/assistente/observations` | — | assistente_operativo |
| POST | `/api/assistente/questions/{question_id}/answer` | — | assistente_operativo |
| POST | `/api/assistente/scan/all` | ✓ | assistente_operativo |
| POST | `/api/assistente/scan/employees` | — | assistente_operativo |
| POST | `/api/assistente/scan/f24` | — | assistente_operativo |
| POST | `/api/assistente/scan/payroll` | — | assistente_operativo |
| POST | `/api/assistente/tax-obligations` | — | assistente_operativo |

## Authentication  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/auth/login` | ext | auth |
| POST | `/api/auth/logout` | ext | auth |
| GET | `/api/auth/verify` | ext | auth |

## Auto Riparazione  (1)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/auto-repair/collega-targa-driver` | ✓ | auto_repair |

## Bank Statement  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/bank-statement/cleanup-duplicati` | — | bank.bank_statement_import |
| POST | `/api/bank-statement/cleanup-duplicati-causale` | — | bank.bank_statement_import |
| GET | `/api/bank-statement/formati-supportati` | — | bank.bank_statement_import |
| POST | `/api/bank-statement/import` | — | bank.bank_statement_import |
| GET | `/api/bank-statement/movements` | ✓ | bank.bank_statement_import |
| POST | `/api/bank-statement/riconcilia-manuale` | — | bank.bank_statement_import |
| GET | `/api/bank-statement/stats` | — | bank.bank_statement_import |

## Batch Reprocessing  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/batch-reprocess/cedolini-only` | ✓ | batch_reprocessing |
| POST | `/api/batch-reprocess/f24-only` | ✓ | batch_reprocessing |
| GET | `/api/batch-reprocess/preview` | ✓ | batch_reprocessing |
| POST | `/api/batch-reprocess/start` | ✓ | batch_reprocessing |
| GET | `/api/batch-reprocess/status` | ✓ | batch_reprocessing |

## Bilancio  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/bilancio/confronto-annuale` | — | accounting.bilancio |
| GET | `/api/bilancio/conto-economico` | ✓ | accounting.bilancio |
| GET | `/api/bilancio/conto-economico-dettagliato` | ✓ | accounting.bilancio |
| GET | `/api/bilancio/export-pdf` | ✓ | accounting.bilancio |
| GET | `/api/bilancio/export/pdf/confronto` | ✓ | accounting.bilancio |
| GET | `/api/bilancio/riepilogo` | — | accounting.bilancio |
| GET | `/api/bilancio/stato-patrimoniale` | ✓ | accounting.bilancio |

## Bonifici Associazioni  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/archivio-bonifici/associa-fattura` | ✓ | bonifici_module.associazioni |
| POST | `/api/archivio-bonifici/associa-salario` | ✓ | bonifici_module.associazioni |
| GET | `/api/archivio-bonifici/dipendente/{dipendente_id}` | — | bonifici_module.associazioni |
| DELETE | `/api/archivio-bonifici/disassocia-fattura/{bonifico_id}` | ✓ | bonifici_module.associazioni |
| DELETE | `/api/archivio-bonifici/disassocia-salario/{bonifico_id}` | ✓ | bonifici_module.associazioni |
| GET | `/api/archivio-bonifici/fatture-compatibili/{bonifico_id}` | ✓ | bonifici_module.associazioni |
| GET | `/api/archivio-bonifici/operazioni-salari/{bonifico_id}` | ✓ | bonifici_module.associazioni |
| POST | `/api/archivio-bonifici/sync-iban-anagrafica` | ✓ | bonifici_module.associazioni |

## Bonifici Import Unificato  (1)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/archivio-bonifici/jobs/import` | — | bank.bonifici_import_unificato |

## Carta Nexi  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/nexi/movimenti` | — | nexi_carta |
| GET | `/api/nexi/stato` | ✓ | nexi_carta |
| POST | `/api/nexi/upload-pdf` | ✓ | nexi_carta |
| POST | `/api/nexi/verifica` | — | nexi_carta |

## Cash  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/cash/corrispettivi` | ✓ | cash |
| GET | `/api/cash/corrispettivi/{target_date}` | ✓ | cash |
| GET | `/api/cash/export/excel` | ✓ | cash |
| GET | `/api/cash/movements` | ✓ | cash |
| POST | `/api/cash/movements` | ✓ | cash |
| PUT | `/api/cash/movements/{movement_id}` | ✓ | cash |
| DELETE | `/api/cash/movements/{movement_id}` | ✓ | cash |
| GET | `/api/cash/stats` | ✓ | cash |

## Cedolini Drive  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/cedolini/drive/quadratura-completa` | — | drive_cedolini |
| GET | `/api/cedolini/drive/status` | — | drive_cedolini |
| POST | `/api/cedolini/drive/sync` | — | drive_cedolini |

## Centri di Costo  (10)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/centri-costo` | ✓ | accounting.centri_costo |
| POST | `/api/centri-costo` | ✓ | accounting.centri_costo |
| POST | `/api/centri-costo/assegna-cdc-fatture` | — | accounting.centri_costo |
| GET | `/api/centri-costo/mapping-categorie` | — | accounting.centri_costo |
| POST | `/api/centri-costo/ribaltamento/calcola` | — | accounting.centri_costo |
| POST | `/api/centri-costo/ribaltamento/quote-ricavo` | — | accounting.centri_costo |
| GET | `/api/centri-costo/utile-obiettivo` | ✓ | accounting.centri_costo |
| POST | `/api/centri-costo/utile-obiettivo` | ✓ | accounting.centri_costo |
| GET | `/api/centri-costo/utile-obiettivo/per-cdc` | ✓ | accounting.centri_costo |
| GET | `/api/centri-costo/utile-obiettivo/suggerimenti` | ✓ | accounting.centri_costo |

## Cespiti  (13)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/cespiti/` | ✓ | cespiti |
| GET | `/api/cespiti/` | ✓ | cespiti |
| GET | `/api/cespiti/calcolo-rateo/{anno}/{mese}` | ✓ | cespiti |
| GET | `/api/cespiti/calcolo/{anno}` | ✓ | cespiti |
| GET | `/api/cespiti/categorie` | ✓ | cespiti |
| POST | `/api/cespiti/dismissione` | ✓ | cespiti |
| POST | `/api/cespiti/registra/{anno}` | ✓ | cespiti |
| GET | `/api/cespiti/riepilogo` | ✓ | cespiti |
| POST | `/api/cespiti/scan-fatture` | ✓ | cespiti |
| GET | `/api/cespiti/verifica/{anno}` | ✓ | cespiti |
| GET | `/api/cespiti/{cespite_id}` | ✓ | cespiti |
| PUT | `/api/cespiti/{cespite_id}` | ✓ | cespiti |
| DELETE | `/api/cespiti/{cespite_id}` | ✓ | cespiti |

## Chat  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/chat/ask` | ✓ | chat_router |
| GET | `/api/chat/health` | — | chat_router |
| GET | `/api/chat/history` | — | chat_router |

## Chiusura Esercizio  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/chiusura-esercizio/apertura-nuovo-esercizio` | ✓ | chiusura_esercizio |
| GET | `/api/chiusura-esercizio/bilancino-verifica/{anno}` | ✓ | chiusura_esercizio |
| POST | `/api/chiusura-esercizio/esegui-chiusura` | ✓ | chiusura_esercizio |
| GET | `/api/chiusura-esercizio/saldi-iniziali/{anno}` | — | chiusura_esercizio |
| GET | `/api/chiusura-esercizio/stato/{anno}` | ✓ | chiusura_esercizio |
| GET | `/api/chiusura-esercizio/storico` | ✓ | chiusura_esercizio |
| GET | `/api/chiusura-esercizio/verifica-preliminare/{anno}` | ✓ | chiusura_esercizio |

## Collaudo  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/collaudo/esegui` | ✓ | collaudo |
| GET | `/api/collaudo/storico` | ✓ | collaudo |
| GET | `/api/collaudo/ultimo` | ✓ | collaudo |

## Commercialista  (15)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/commercialista/alert-status` | ✓ | commercialista |
| GET | `/api/commercialista/config` | ✓ | commercialista |
| PUT | `/api/commercialista/config` | ✓ | commercialista |
| GET | `/api/commercialista/export-completo/{anno}/{mese}` | ✓ | commercialista |
| GET | `/api/commercialista/export-excel/{anno}/{mese}` | ✓ | commercialista |
| GET | `/api/commercialista/export-log` | — | commercialista |
| GET | `/api/commercialista/fatture-cassa/{anno}/{mese}` | ✓ | commercialista |
| POST | `/api/commercialista/invia-carnet` | ✓ | commercialista |
| POST | `/api/commercialista/invia-fatture-cassa` | ✓ | commercialista |
| POST | `/api/commercialista/invia-prima-nota` | ✓ | commercialista |
| GET | `/api/commercialista/log` | ✓ | commercialista |
| GET | `/api/commercialista/prima-nota-cassa/{anno}/{mese}` | ✓ | commercialista |
| GET | `/api/commercialista/riepilogo/{anno}/{mese}` | ✓ | commercialista |
| POST | `/api/commercialista/schedula-export` | — | commercialista |
| POST | `/api/commercialista/segna-inviata` | ✓ | commercialista |

## Config Import  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/config-import/anno` | ✓ | config_import |
| PUT | `/api/config-import/anno` | ✓ | config_import |
| POST | `/api/config-import/importa-anno` | ✓ | config_import |

## Configurazioni  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/config/email-accounts` | ✓ | configurazioni |
| POST | `/api/config/email-accounts` | ✓ | configurazioni |
| PUT | `/api/config/email-accounts/{account_id}` | ✓ | configurazioni |
| DELETE | `/api/config/email-accounts/{account_id}` | ✓ | configurazioni |
| POST | `/api/config/email-accounts/{account_id}/test` | ✓ | configurazioni |
| GET | `/api/config/parole-chiave` | ✓ | configurazioni |
| PUT | `/api/config/parole-chiave` | ✓ | configurazioni |
| POST | `/api/config/parole-chiave/aggiungi` | ✓ | configurazioni |
| DELETE | `/api/config/parole-chiave/rimuovi` | ✓ | configurazioni |

## Contabilita Avanzata  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/contabilita/aliquote-irap` | ✓ | accounting.contabilita_avanzata |
| GET | `/api/contabilita/bilancio-dettagliato` | ✓ | accounting.contabilita_avanzata |
| GET | `/api/contabilita/calcolo-imposte` | ✓ | accounting.contabilita_avanzata |
| GET | `/api/contabilita/categorizzazione-preview` | — | accounting.contabilita_avanzata |
| GET | `/api/contabilita/export/pdf-dichiarazione` | ✓ | accounting.contabilita_avanzata |
| POST | `/api/contabilita/inizializza-piano-esteso` | ✓ | accounting.contabilita_avanzata |
| GET | `/api/contabilita/piano-conti-esteso` | — | accounting.contabilita_avanzata |
| POST | `/api/contabilita/ricategorizza-fatture` | ✓ | accounting.contabilita_avanzata |
| GET | `/api/contabilita/statistiche-categorizzazione` | ✓ | accounting.contabilita_avanzata |

## Contabilità Gestionale  (14)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/contabilita-gestionale/bilancio-verifica` | ✓ | accounting.contabilita_gestionale |
| POST | `/api/contabilita-gestionale/budget` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/budget-vs-consuntivo/{anno}` | ✓ | accounting.contabilita_gestionale |
| POST | `/api/contabilita-gestionale/budget/duplica/{anno_origine}/{anno_destinazione}` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/budget/{anno}` | ✓ | accounting.contabilita_gestionale |
| DELETE | `/api/contabilita-gestionale/budget/{anno}/{voce}` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/libro-giornale` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/libro-giornale/controllo-60-giorni` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/libro-giornale/export` | ✓ | accounting.contabilita_gestionale |
| POST | `/api/contabilita-gestionale/libro-giornale/import` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/libro-mastro` | ✓ | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/partitario/clienti` | — | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/partitario/fornitori` | — | accounting.contabilita_gestionale |
| GET | `/api/contabilita-gestionale/partitario/fornitori/{piva}` | — | accounting.contabilita_gestionale |

## Contabilità Italiana  (1)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/contabilita/disponibilita-liquide` | ✓ | contabilita_italiana |

## Controllo Gestione  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/controllo-gestione/costi-per-categoria` | — | controllo_gestione |
| GET | `/api/controllo-gestione/costi-ricavi` | ✓ | controllo_gestione |
| GET | `/api/controllo-gestione/kpi/{anno}` | — | controllo_gestione |
| GET | `/api/controllo-gestione/trend-mensile` | — | controllo_gestione |

## Corrispettivi  (24)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/corrispettivi` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/aggiorna-stati-mancanti` | ✓ | invoices.corrispettivi |
| DELETE | `/api/corrispettivi/all` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/auto-ricostruisci-dati` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/cleanup-duplicati-forte` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/elimina-duplicati` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/hard-delete-bulk` | ✓ | invoices.corrispettivi |
| DELETE | `/api/corrispettivi/hard-delete/{corrispettivo_id}` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/import-csv` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/manuale` | ✓ | invoices.corrispettivi |
| GET | `/api/corrispettivi/manuali-senza-xml` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/normalizza-pagamenti` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/rebuild-prima-nota` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/ricalcola-annulli-non-riscosso` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/ricalcola-iva` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/sincronizza-prima-nota` | ✓ | invoices.corrispettivi |
| GET | `/api/corrispettivi/template-csv` | ✓ | invoices.corrispettivi |
| GET | `/api/corrispettivi/totals` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/upload-xml` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/upload-xml-bulk` | ✓ | invoices.corrispettivi |
| POST | `/api/corrispettivi/upload-zip` | ✓ | invoices.corrispettivi |
| GET | `/api/corrispettivi/view-by-filename` | ✓ | invoices.corrispettivi |
| DELETE | `/api/corrispettivi/{corrispettivo_id}` | ✓ | invoices.corrispettivi |
| GET | `/api/corrispettivi/{corrispettivo_id}/view` | ✓ | invoices.corrispettivi |

## Corrispettivi Drive  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/corrispettivi/drive/quadratura` | ✓ | drive_corrispettivi |
| GET | `/api/corrispettivi/drive/status` | ✓ | drive_corrispettivi |
| POST | `/api/corrispettivi/drive/sync` | ✓ | drive_corrispettivi |

## Dashboard  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/dashboard/bilancio-istantaneo` | — | reports.dashboard |
| GET | `/api/dashboard/confronto-annuale` | — | reports.dashboard |
| GET | `/api/dashboard/fascia-energia` | ✓ | reports.dashboard |
| GET | `/api/dashboard/kpi` | — | reports.dashboard |
| GET | `/api/dashboard/spese-per-categoria` | — | reports.dashboard |
| GET | `/api/dashboard/stato-riconciliazione` | — | reports.dashboard |
| GET | `/api/dashboard/stats` | — | reports.dashboard |
| GET | `/api/dashboard/summary` | ✓ | reports.dashboard |
| GET | `/api/dashboard/trend-mensile` | ✓ | reports.dashboard |

## Dati ISA  (1)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/dati-isa/riepilogo` | ✓ | dati_isa |

## Dati Provvisori  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/conferma-tutte` | — | dati_provvisori |
| POST | `/api/conferma/{proposta_id}` | — | dati_provvisori |
| POST | `/api/dati-provvisori/riconcilia-estratto-conto` | — | dati_provvisori |
| POST | `/api/genera-proposte` | — | dati_provvisori |
| GET | `/api/proposte` | — | dati_provvisori |
| POST | `/api/rifiuta/{proposta_id}` | — | dati_provvisori |

## Dipendenti  (28)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/dipendenti` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/bulk-upsert` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/bulk-upsert/preview` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/buste-paga` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/buste-paga` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/buste-paga/dipendente/{dipendente_id}` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/buste-paga/dipendente/{dipendente_id}/import` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/buste-paga/import` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/buste-paga/scan` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/by-google-email` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/duplicati` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/duplicati/auto-merge` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/duplicati/merge` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/invita-multipli` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/mansioni` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/portale/stats` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/report-ferie-permessi-tutti` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/stats` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/sync-iban` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/tipi-turno` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/turni/salva` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/turni/settimana` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/{dipendente_id}` | ✓ | employees.dipendenti |
| PUT | `/api/dipendenti/{dipendente_id}` | ✓ | employees.dipendenti |
| DELETE | `/api/dipendenti/{dipendente_id}` | ✓ | employees.dipendenti |
| POST | `/api/dipendenti/{dipendente_id}/invita-portale` | ✓ | employees.dipendenti |
| GET | `/api/dipendenti/{dipendente_id}/report-ferie-permessi` | ✓ | employees.dipendenti |

## Dizionario Articoli  (11)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| PUT | `/api/dizionario-articoli/articolo/{descrizione_encoded}` | — | warehouse.dizionario_articoli |
| POST | `/api/dizionario-articoli/categorizza-ai` | — | warehouse.dizionario_articoli |
| GET | `/api/dizionario-articoli/cerca` | — | warehouse.dizionario_articoli |
| GET | `/api/dizionario-articoli/dizionario` | — | warehouse.dizionario_articoli |
| GET | `/api/dizionario-articoli/estrai-articoli` | — | warehouse.dizionario_articoli |
| POST | `/api/dizionario-articoli/genera-dizionario` | — | warehouse.dizionario_articoli |
| GET | `/api/dizionario-articoli/non-classificati` | — | warehouse.dizionario_articoli |
| DELETE | `/api/dizionario-articoli/reset-dizionario` | — | warehouse.dizionario_articoli |
| POST | `/api/dizionario-articoli/ricategorizza-fatture` | — | warehouse.dizionario_articoli |
| POST | `/api/dizionario-articoli/riclassifica-completo` | ✓ | warehouse.dizionario_articoli |
| GET | `/api/dizionario-articoli/statistiche` | — | warehouse.dizionario_articoli |

## Document AI  (10)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/document-ai/classified-documents-stats` | — | document_ai |
| GET | `/api/document-ai/document-types` | — | document_ai |
| POST | `/api/document-ai/extract` | — | document_ai |
| POST | `/api/document-ai/extract-base64` | — | document_ai |
| POST | `/api/document-ai/extract-text-only` | — | document_ai |
| GET | `/api/document-ai/extracted-documents` | — | document_ai |
| DELETE | `/api/document-ai/extracted-documents/{doc_id}` | — | document_ai |
| POST | `/api/document-ai/process-all-classified` | — | document_ai |
| POST | `/api/document-ai/process-classified-email` | — | document_ai |
| POST | `/api/document-ai/reprocess-and-save` | — | document_ai |

## Documenti  (38)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/documenti/cartelle-email` | — | documenti |
| GET | `/api/documenti/categorie` | — | documenti |
| GET | `/api/documenti/documento/{doc_id}` | ✓ | documenti |
| DELETE | `/api/documenti/documento/{doc_id}` | ✓ | documenti |
| POST | `/api/documenti/documento/{doc_id}/annulla-processamento` | — | documenti |
| POST | `/api/documenti/documento/{doc_id}/cambia-categoria` | — | documenti |
| GET | `/api/documenti/documento/{doc_id}/download` | ✓ | documenti |
| POST | `/api/documenti/documento/{doc_id}/processa` | — | documenti |
| GET | `/api/documenti/drive/catalog` | ✓ | documenti |
| POST | `/api/documenti/drive/fiscal/discover` | — | documenti |
| GET | `/api/documenti/drive/fiscal/status` | — | documenti |
| POST | `/api/documenti/drive/fiscal/sync` | ✓ | documenti |
| POST | `/api/documenti/drive/sync` | ✓ | documenti |
| POST | `/api/documenti/elimina-processati` | — | documenti |
| POST | `/api/documenti/fiscal/ingest` | — | documenti |
| GET | `/api/documenti/lista` | ✓ | documenti |
| GET | `/api/documenti/lock-status` | — | documenti |
| POST | `/api/documenti/monitor/start` | — | documenti |
| GET | `/api/documenti/monitor/status` | — | documenti |
| POST | `/api/documenti/monitor/stop` | — | documenti |
| POST | `/api/documenti/monitor/sync-now` | — | documenti |
| POST | `/api/documenti/processa-f24-scaricati` | — | documenti |
| POST | `/api/documenti/processa-tutti` | — | documenti |
| POST | `/api/documenti/reimporta-da-filesystem` | — | documenti |
| POST | `/api/documenti/ricategorizza-documenti` | — | documenti |
| POST | `/api/documenti/scarica-da-email` | — | documenti |
| GET | `/api/documenti/statistiche` | — | documenti |
| POST | `/api/documenti/sync-estratti-bnl` | — | documenti |
| POST | `/api/documenti/sync-estratti-conto` | — | documenti |
| POST | `/api/documenti/sync-f24-automatico` | ✓ | documenti |
| GET | `/api/documenti/task/{task_id}` | — | documenti |
| GET | `/api/documenti/tax-codes/status` | ✓ | documenti |
| POST | `/api/documenti/tax-codes/sync` | — | documenti |
| GET | `/api/documenti/telegram/status` | — | documenti |
| POST | `/api/documenti/telegram/test` | — | documenti |
| GET | `/api/documenti/ultimo-sync` | — | documenti |
| POST | `/api/documenti/upload-auto` | ✓ | documenti |
| POST | `/api/documenti/upload-auto/preview` | ✓ | documenti |

## Documenti Non Associati  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/documenti-non-associati/associa` | ✓ | documenti_non_associati |
| GET | `/api/documenti-non-associati/associati-di-recente` | ✓ | documenti_non_associati |
| GET | `/api/documenti-non-associati/categorie-mittente` | — | documenti_non_associati |
| GET | `/api/documenti-non-associati/collezioni-disponibili` | ✓ | documenti_non_associati |
| POST | `/api/documenti-non-associati/de-associa` | ✓ | documenti_non_associati |
| GET | `/api/documenti-non-associati/lista` | ✓ | documenti_non_associati |
| GET | `/api/documenti-non-associati/pdf/{documento_id}` | ✓ | documenti_non_associati |
| GET | `/api/documenti-non-associati/statistiche` | ✓ | documenti_non_associati |
| DELETE | `/api/documenti-non-associati/{documento_id}` | ✓ | documenti_non_associati |

## Documenti fiscali  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/documenti-fiscali/lista` | — | documenti_fiscali |
| POST | `/api/documenti-fiscali/upload` | — | documenti_fiscali |

## Documents Inbox  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/documenti-inbox/auto-classify` | ✓ | documents_inbox_classify |
| GET | `/api/documenti-inbox/cross-check-f24` | — | documents_inbox_classify |
| POST | `/api/documenti-inbox/import-dipendenti-from-cu` | ✓ | documents_inbox_classify |
| POST | `/api/documenti-inbox/import-f24-from-inbox` | ✓ | documents_inbox_classify |
| GET | `/api/documenti-inbox/statistics` | — | documents_inbox_classify |

## ERP Bridge  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/erp/ponte/fattura-ricevuta` | ext | erp_bridge |
| GET | `/api/erp/ponte/status` | ext | erp_bridge |

## Email Download  (41)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/email-download/associa-documento` | — | email_download |
| POST | `/api/email-download/associa-f24-filesystem` | — | email_download |
| POST | `/api/email-download/auto-associa` | ✓ | email_download |
| POST | `/api/email-download/auto-associa-v2` | ✓ | email_download |
| GET | `/api/email-download/confronto-pos` | — | email_download |
| GET | `/api/email-download/dizionario-email` | — | email_download |
| DELETE | `/api/email-download/dizionario-email/reset` | — | email_download |
| GET | `/api/email-download/documenti-non-associati` | — | email_download |
| GET | `/api/email-download/documents-inbox-stats` | — | email_download |
| POST | `/api/email-download/download-single-day` | — | email_download |
| POST | `/api/email-download/estrai-importi-verbali` | — | email_download |
| POST | `/api/email-download/fix-numeri-verbali` | — | email_download |
| GET | `/api/email-download/inbox-documents` | — | email_download |
| GET | `/api/email-download/mittenti` | ✓ | email_download |
| POST | `/api/email-download/mittenti` | ✓ | email_download |
| GET | `/api/email-download/mittenti/check` | ✓ | email_download |
| POST | `/api/email-download/mittenti/migra-legacy` | ✓ | email_download |
| DELETE | `/api/email-download/mittenti/{mittente_id}` | ✓ | email_download |
| PUT | `/api/email-download/mittenti/{mittente_id}` | ✓ | email_download |
| POST | `/api/email-download/parse-f24-llm` | — | email_download |
| POST | `/api/email-download/parse-verbali-llm` | — | email_download |
| GET | `/api/email-download/paypal-transazioni` | — | email_download |
| GET | `/api/email-download/pdf/{collection}/{pdf_id}` | — | email_download |
| POST | `/api/email-download/popola-pdf-payslips` | — | email_download |
| POST | `/api/email-download/processa-cedolini` | — | email_download |
| POST | `/api/email-download/processa-fatture-email` | — | email_download |
| POST | `/api/email-download/processa-fatture-email/batch` | — | email_download |
| GET | `/api/email-download/processa-fatture-email/status` | — | email_download |
| POST | `/api/email-download/processa-pipeline` | — | email_download |
| DELETE | `/api/email-download/pulisci-duplicati` | — | email_download |
| POST | `/api/email-download/pulizia-non-attendibili` | — | email_download |
| POST | `/api/email-download/riconcilia-paypal` | — | email_download |
| POST | `/api/email-download/riconcilia-verbali` | — | email_download |
| POST | `/api/email-download/riconcilia-verbali-avanzato` | — | email_download |
| POST | `/api/email-download/riconciliazione-completa` | — | email_download |
| POST | `/api/email-download/scarica-pdf-verbali-mancanti` | — | email_download |
| POST | `/api/email-download/start-full-download` | ✓ | email_download |
| GET | `/api/email-download/statistiche` | — | email_download |
| GET | `/api/email-download/status` | — | email_download |
| POST | `/api/email-download/sync-email-now` | — | email_download |
| POST | `/api/email-download/sync-filesystem` | — | email_download |

## Email Scanner  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/email-scanner/associa` | ✓ | email_scanner |
| GET | `/api/email-scanner/cartelle` | — | email_scanner |
| POST | `/api/email-scanner/scansiona` | — | email_scanner |
| POST | `/api/email-scanner/scansiona-e-associa` | — | email_scanner |
| GET | `/api/email-scanner/statistiche` | ✓ | email_scanner |

## Estratto Conto  (15)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/estratto-conto-movimenti/categorie` | — | bank.estratto_conto |
| DELETE | `/api/estratto-conto-movimenti/clear` | — | bank.estratto_conto |
| GET | `/api/estratto-conto-movimenti/export-excel` | — | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/force-reimport` | — | bank.estratto_conto |
| GET | `/api/estratto-conto-movimenti/fornitori` | — | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/import` | — | bank.estratto_conto |
| GET | `/api/estratto-conto-movimenti/movimenti` | — | bank.estratto_conto |
| GET | `/api/estratto-conto-movimenti/movimenti-stipendi` | — | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/pulizia-non-in-csv` | — | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/reimport` | — | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/ricategorizza-batch` | ✓ | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/riconcilia-stipendi` | — | bank.estratto_conto |
| GET | `/api/estratto-conto-movimenti/riepilogo` | — | bank.estratto_conto |
| POST | `/api/estratto-conto-movimenti/ripara-versamenti-cassa` | ✓ | bank.estratto_conto |
| DELETE | `/api/estratto-conto-movimenti/{movimento_id}` | ✓ | bank.estratto_conto |

## F24  (24)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/f24` | ✓ | f24.f24_main |
| POST | `/api/f24` | ✓ | f24.f24_main |
| GET | `/api/f24/alerts/scadenze` | ✓ | f24.f24_main |
| GET | `/api/f24/codici/all` | ✓ | f24.f24_main |
| GET | `/api/f24/codici/{codice}` | ✓ | f24.f24_main |
| GET | `/api/f24/dashboard/summary` | ✓ | f24.f24_main |
| GET | `/api/f24/documents` | ✓ | f24.f24_main |
| DELETE | `/api/f24/documents/{doc_id}` | ✓ | f24.f24_main |
| POST | `/api/f24/fascicolo/costruisci` | ✓ | f24.f24_main |
| GET | `/api/f24/fascicolo/{codice_fiscale}/{mese}/{anno}` | ✓ | f24.f24_main |
| GET | `/api/f24/quietanze` | ✓ | f24.f24_main |
| GET | `/api/f24/quietanze/statistiche/tributi` | ✓ | f24.f24_main |
| POST | `/api/f24/quietanze/upload` | ✓ | f24.f24_main |
| GET | `/api/f24/quietanze/{f24_id}` | ✓ | f24.f24_main |
| DELETE | `/api/f24/quietanze/{f24_id}` | ✓ | f24.f24_main |
| POST | `/api/f24/riconcilia` | ✓ | f24.f24_main |
| POST | `/api/f24/upload` | ✓ | f24.f24_main |
| POST | `/api/f24/upload-multiple` | ✓ | f24.f24_main |
| POST | `/api/f24/upload-pdf` | ✓ | f24.f24_main |
| POST | `/api/f24/upload-zip` | ✓ | f24.f24_main |
| PUT | `/api/f24/{f24_id}` | ✓ | f24.f24_main |
| DELETE | `/api/f24/{f24_id}` | ✓ | f24.f24_main |
| GET | `/api/f24/{f24_id}` | ✓ | f24.f24_main |
| POST | `/api/f24/{f24_id}/mark-paid` | ✓ | f24.f24_main |

## F24 Analisi  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/f24-analisi/doppi-pagamenti` | ✓ | f24_analisi |
| GET | `/api/f24-analisi/tabella` | ✓ | f24_analisi |
| GET | `/api/f24-analisi/{f24_id}` | ✓ | f24_analisi |
| GET | `/api/f24-analisi/{f24_id}/associazione` | ✓ | f24_analisi |

## F24 Email  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/f24-email-settings/aggiungi-mittente` | ✓ | f24_email_settings |
| GET | `/api/f24-email-settings/impostazioni` | ✓ | f24_email_settings |
| POST | `/api/f24-email-settings/impostazioni` | ✓ | f24_email_settings |
| GET | `/api/f24-email-settings/log-scansioni` | ✓ | f24_email_settings |
| DELETE | `/api/f24-email-settings/rimuovi-mittente/{email}` | ✓ | f24_email_settings |
| POST | `/api/f24-email-settings/scan-manuale` | ✓ | f24_email_settings |
| GET | `/api/f24-email-settings/stato-sistema` | ✓ | f24_email_settings |
| POST | `/api/f24-email-settings/toggle-auto-scan` | ✓ | f24_email_settings |

## F24 Email Download  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/f24-email/allegati` | ✓ | f24.email_f24 |
| GET | `/api/f24-email/codici-tributo` | ✓ | f24.email_f24 |
| GET | `/api/f24-email/log-download` | ✓ | f24.email_f24 |
| GET | `/api/f24-email/mittenti` | ✓ | f24.email_f24 |
| POST | `/api/f24-email/processa-allegati` | ✓ | f24.email_f24 |
| POST | `/api/f24-email/scarica-e-processa` | ✓ | f24.email_f24 |
| POST | `/api/f24-email/scarica-email` | ✓ | f24.email_f24 |

## F24 Public  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/f24-public/models` | ext | f24.f24_public |
| PUT | `/api/f24-public/models/{f24_id}` | ext | f24.f24_public |
| DELETE | `/api/f24-public/models/{f24_id}` | ext | f24.f24_public |
| PUT | `/api/f24-public/models/{f24_id}/pagato` | ext | f24.f24_public |
| GET | `/api/f24-public/pdf/{f24_id}` | ext | f24.f24_public |
| GET | `/api/f24-public/scadenze-prossime` | ext | f24.f24_public |
| GET | `/api/f24-public/test` | ext | f24.f24_public |
| POST | `/api/f24-public/upload` | ext | f24.f24_public |
| POST | `/api/f24-public/upload-overwrite` | ext | f24.f24_public |

## F24 Riconciliazione  (18)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/f24-riconciliazione/alerts` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/alerts/{alert_id}/conferma-elimina` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/alerts/{alert_id}/ignora` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/commercialista` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/commercialista/upload` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/commercialista/{f24_id}` | ✓ | f24.f24_riconciliazione |
| PUT | `/api/f24-riconciliazione/commercialista/{f24_id}` | ✓ | f24.f24_riconciliazione |
| DELETE | `/api/f24-riconciliazione/commercialista/{f24_id}` | ✓ | f24.f24_riconciliazione |
| PUT | `/api/f24-riconciliazione/commercialista/{f24_id}/pagato` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/commercialista/{f24_id}/pdf` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/dashboard` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/fix-campo-anno` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/quietanze` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/quietanze/upload-multiplo` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/quietanze/{quietanza_id}` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/riconcilia-quietanza` | ✓ | f24.f24_riconciliazione |
| POST | `/api/f24-riconciliazione/riconcilia-tutto` | ✓ | f24.f24_riconciliazione |
| GET | `/api/f24-riconciliazione/verifica-codice/{codice_tributo}` | ✓ | f24.f24_riconciliazione |

## Fatture Drive  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/fatture/drive/quadratura` | — | invoices.fatture_drive |
| GET | `/api/fatture/drive/status` | ✓ | invoices.fatture_drive |
| POST | `/api/fatture/drive/sync` | ✓ | invoices.fatture_drive |

## Fatture Estere Verifica  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/fatture-estere/affidabilita` | ✓ | fatture_estera_verifica |
| GET | `/api/fatture-estere/da-verificare` | ✓ | fatture_estera_verifica |
| POST | `/api/fatture-estere/{fattura_id}/verifica` | ✓ | fatture_estera_verifica |

## Fatture Ricevute  (23)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/fatture-ricevute/aggiorna-metodi-pagamento` | — | fatture_module.pagamento |
| GET | `/api/fatture-ricevute/archivio` | ✓ | fatture_module.crud |
| POST | `/api/fatture-ricevute/backfill-autoroute` | — | fatture_module.pagamento |
| POST | `/api/fatture-ricevute/cambia-metodo-pagamento` | — | fatture_module.pagamento |
| POST | `/api/fatture-ricevute/elimina-anni-vecchi` | — | fatture_module.crud |
| POST | `/api/fatture-ricevute/elimina-gusci-vuoti` | — | fatture_module.crud |
| POST | `/api/fatture-ricevute/export-selezione` | ✓ | fatture_module.export_selezione |
| GET | `/api/fatture-ricevute/fattura/{fattura_id}` | ✓ | fatture_module.crud |
| PUT | `/api/fatture-ricevute/fattura/{fattura_id}` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/fattura/{fattura_id}/documenti-pagamento` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/fattura/{fattura_id}/pdf/{allegato_id}` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/fattura/{fattura_id}/storia` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/fattura/{fattura_id}/view-assoinvoice` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/fattura/{fattura_id}/xml-originale` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/fornitori` | ✓ | fatture_module.crud |
| POST | `/api/fatture-ricevute/import-paypal` | — | fatture_module.pagamento |
| GET | `/api/fatture-ricevute/lista-paypal` | — | fatture_module.pagamento |
| POST | `/api/fatture-ricevute/paga-manuale` | ✓ | fatture_module.pagamento |
| POST | `/api/fatture-ricevute/pulisci-duplicati` | — | fatture_module.crud |
| POST | `/api/fatture-ricevute/riconcilia-con-estratto-conto` | — | fatture_module.pagamento |
| POST | `/api/fatture-ricevute/riconcilia-paypal` | — | fatture_module.pagamento |
| GET | `/api/fatture-ricevute/statistiche` | ✓ | fatture_module.crud |
| GET | `/api/fatture-ricevute/verifica-incoerenze-estratto-conto` | — | fatture_module.pagamento |

## Fatture Upload  (12)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| DELETE | `/api/fatture/all` | — | invoices.fatture_upload |
| POST | `/api/fatture/categorize-movements` | — | invoices.fatture_upload |
| POST | `/api/fatture/recalculate-iva` | — | invoices.fatture_upload |
| POST | `/api/fatture/sync-suppliers` | — | invoices.fatture_upload |
| POST | `/api/fatture/upload-xml` | — | invoices.fatture_upload |
| POST | `/api/fatture/upload-xml-bulk` | — | invoices.fatture_upload |
| GET | `/api/fatture/{invoice_id}` | ✓ | invoices.fatture_upload |
| PUT | `/api/fatture/{invoice_id}` | ✓ | invoices.fatture_upload |
| DELETE | `/api/fatture/{invoice_id}` | ✓ | invoices.fatture_upload |
| PUT | `/api/fatture/{invoice_id}/classifica` | ✓ | invoices.fatture_upload |
| GET | `/api/fatture/{invoice_id}/entita-correlate` | ✓ | invoices.fatture_upload |
| PUT | `/api/fatture/{invoice_id}/paga` | ✓ | invoices.fatture_upload |

## Finanziamento Soci  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/finanziamenti-soci/movimento` | ✓ | finanziamenti_soci |
| DELETE | `/api/finanziamenti-soci/movimento/{movimento_id}` | ✓ | finanziamenti_soci |
| POST | `/api/finanziamenti-soci/scan` | — | finanziamenti_soci |
| GET | `/api/finanziamenti-soci/schede` | ✓ | finanziamenti_soci |

## Finanziaria  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/finanziaria/cost-categories` | — | finanziaria |
| GET | `/api/finanziaria/costi` | — | finanziaria |
| POST | `/api/finanziaria/costo` | — | finanziaria |
| GET | `/api/finanziaria/summary` | ✓ | finanziaria |

## Fiscalità Italiana  (11)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/fiscalita/agevolazioni` | — | fiscalita_italiana |
| POST | `/api/fiscalita/agevolazioni/simula` | — | fiscalita_italiana |
| GET | `/api/fiscalita/agevolazioni/{agevolazione_id}` | — | fiscalita_italiana |
| POST | `/api/fiscalita/calendario/completa/{scadenza_id}` | ✓ | fiscalita_italiana |
| POST | `/api/fiscalita/calendario/riapri/{scadenza_id}` | ✓ | fiscalita_italiana |
| GET | `/api/fiscalita/calendario/scadenze-imminenti` | — | fiscalita_italiana |
| GET | `/api/fiscalita/calendario/{anno}` | ✓ | fiscalita_italiana |
| POST | `/api/fiscalita/f24/registra` | — | fiscalita_italiana |
| GET | `/api/fiscalita/f24/storico` | — | fiscalita_italiana |
| GET | `/api/fiscalita/notifiche-scadenze` | ✓ | fiscalita_italiana |
| POST | `/api/fiscalita/notifiche-scadenze/invia` | ✓ | fiscalita_italiana |

## Fornitori Learning  (16)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/fornitori-learning/associa-magazzino` | — | fornitori_learning |
| GET | `/api/fornitori-learning/centri-costo-disponibili` | ✓ | fornitori_learning |
| POST | `/api/fornitori-learning/classifica-ai` | ✓ | fornitori_learning |
| POST | `/api/fornitori-learning/classifica-da-contenuto` | ✓ | fornitori_learning |
| POST | `/api/fornitori-learning/classifica-f24` | — | fornitori_learning |
| GET | `/api/fornitori-learning/f24-statistiche` | — | fornitori_learning |
| GET | `/api/fornitori-learning/giacenze-fornitore/{fornitore_nome}` | — | fornitori_learning |
| GET | `/api/fornitori-learning/lista` | ✓ | fornitori_learning |
| GET | `/api/fornitori-learning/non-classificati` | ✓ | fornitori_learning |
| GET | `/api/fornitori-learning/prodotti-per-fornitore/{fornitore_nome}` | — | fornitori_learning |
| POST | `/api/fornitori-learning/riclassifica-con-keywords` | ✓ | fornitori_learning |
| POST | `/api/fornitori-learning/riclassifica-f24/{f24_id}` | — | fornitori_learning |
| POST | `/api/fornitori-learning/salva` | ✓ | fornitori_learning |
| GET | `/api/fornitori-learning/stats` | ✓ | fornitori_learning |
| GET | `/api/fornitori-learning/suggerisci-keywords/{fornitore_nome}` | — | fornitori_learning |
| DELETE | `/api/fornitori-learning/{fornitore_id}` | ✓ | fornitori_learning |

## Gestione Riservata  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/gestione-riservata/login` | ✓ | gestione_riservata |
| GET | `/api/gestione-riservata/movimenti` | ✓ | gestione_riservata |
| POST | `/api/gestione-riservata/movimenti` | ✓ | gestione_riservata |
| PUT | `/api/gestione-riservata/movimenti/{movimento_id}` | ✓ | gestione_riservata |
| DELETE | `/api/gestione-riservata/movimenti/{movimento_id}` | ✓ | gestione_riservata |
| GET | `/api/gestione-riservata/riepilogo` | ✓ | gestione_riservata |
| GET | `/api/gestione-riservata/volume-affari-reale` | — | gestione_riservata |

## IVA  (20)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/iva/anomalie` | ✓ | iva |
| GET | `/api/iva/dashboard/{anno}/{mese}` | ✓ | iva |
| GET | `/api/iva/fatture` | ✓ | iva |
| GET | `/api/iva/fatture/non-utilizzate` | ✓ | iva |
| POST | `/api/iva/fatture/{fid}/correggi-periodo` | — | iva |
| POST | `/api/iva/fatture/{fid}/escludi` | — | iva |
| POST | `/api/iva/fatture/{fid}/includi` | — | iva |
| POST | `/api/iva/fatture/{fid}/indetraibile` | — | iva |
| POST | `/api/iva/fatture/{fid}/recupero-annuale` | — | iva |
| POST | `/api/iva/fatture/{fid}/rinvia` | — | iva |
| GET | `/api/iva/liquidazioni` | ✓ | iva |
| POST | `/api/iva/liquidazioni/calcola` | ✓ | iva |
| POST | `/api/iva/liquidazioni/{liq_id}/conferma` | ✓ | iva |
| POST | `/api/iva/liquidazioni/{liq_id}/rettifica` | ✓ | iva |
| POST | `/api/iva/liquidazioni/{liq_id}/riapri` | ✓ | iva |
| GET | `/api/iva/liquidazioni/{periodo}` | ✓ | iva |
| POST | `/api/iva/ricalcola-attribuzione` | ✓ | iva |
| GET | `/api/iva/ricalcola-attribuzione/ultimo` | ✓ | iva |
| GET | `/api/iva/riepilogo-annuale/{anno}` | ✓ | iva |
| GET | `/api/iva/versamento/{anno}/{mese}` | — | iva |

## Inserimento Rapido  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/rapido/acconto-dipendente` | ✓ | rapido |
| POST | `/api/rapido/apporto-soci` | ✓ | rapido |
| POST | `/api/rapido/corrispettivo` | ✓ | rapido |
| GET | `/api/rapido/dipendenti-attivi` | ✓ | rapido |
| POST | `/api/rapido/paga-fattura` | ✓ | rapido |
| POST | `/api/rapido/presenza` | ✓ | rapido |
| GET | `/api/rapido/ultimi-inserimenti` | ✓ | rapido |
| POST | `/api/rapido/versamento-banca` | ✓ | rapido |

## Invoices  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/invoices` | ✓ | invoices.invoices_main |
| GET | `/api/invoices/bank-pending` | ✓ | invoices.invoices_main |
| GET | `/api/invoices/by-month/{year}/{month}` | ✓ | invoices.invoices_main |
| GET | `/api/invoices/{invoice_id}` | ✓ | invoices.invoices_main |

## Invoices Emesse  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/invoices/emesse` | ✓ | invoices.invoices_emesse |
| POST | `/api/invoices/emesse` | ✓ | invoices.invoices_emesse |
| GET | `/api/invoices/emesse/{invoice_id}` | ✓ | invoices.invoices_emesse |
| DELETE | `/api/invoices/emesse/{invoice_id}` | ✓ | invoices.invoices_emesse |

## Learning Machine  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/learning-machine/dashboard` | ✓ | learning_machine |
| GET | `/api/learning-machine/documenti` | — | learning_machine |
| POST | `/api/learning-machine/feedback` | — | learning_machine |
| GET | `/api/learning-machine/regole-apprese` | ✓ | learning_machine |
| DELETE | `/api/learning-machine/reset-learning` | — | learning_machine |
| POST | `/api/learning-machine/scan` | — | learning_machine |
| GET | `/api/learning-machine/statistiche-feedback` | — | learning_machine |

## Learning Universal  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/learning-universal/apply-suggestions` | — | learning_universal |
| GET | `/api/learning-universal/results` | ✓ | learning_universal |
| GET | `/api/learning-universal/status` | ✓ | learning_universal |
| GET | `/api/learning-universal/suggestions/{module}` | — | learning_universal |
| POST | `/api/learning-universal/train/all` | ✓ | learning_universal |

## Legal  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/data-deletion` | — | legal_pages |
| GET | `/api/privacy` | — | legal_pages |
| GET | `/api/terms` | — | legal_pages |
| GET | `/data-deletion` | ext | legal_pages |
| GET | `/privacy` | ext | legal_pages |
| GET | `/terms` | ext | legal_pages |

## MFA  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/auth/mfa/disable` | ext | mfa |
| POST | `/api/auth/mfa/setup/confirm` | ext | mfa |
| POST | `/api/auth/mfa/setup/start` | ext | mfa |
| GET | `/api/auth/mfa/status` | ext | mfa |
| POST | `/api/auth/mfa/step-up` | ext | mfa |
| POST | `/api/auth/mfa/verify-login` | ext | mfa |

## Multi-Pagamento  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/pagamenti/assegno-multi-fatture` | — | multi_pagamento |
| POST | `/api/pagamenti/fattura-multi-metodo` | — | multi_pagamento |
| GET | `/api/pagamenti/fattura/{fattura_id}` | — | multi_pagamento |
| POST | `/api/pagamenti/registra` | ✓ | multi_pagamento |
| GET | `/api/pagamenti/riepilogo-fornitore/{piva}` | — | multi_pagamento |
| DELETE | `/api/pagamenti/{pagamento_id}` | — | multi_pagamento |

## Mutui  (10)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/mutui` | ✓ | mutui |
| GET | `/api/mutui/` | ✓ | mutui |
| POST | `/api/mutui/` | ✓ | mutui |
| POST | `/api/mutui/riconcilia` | ✓ | mutui |
| GET | `/api/mutui/statistiche/dashboard` | ✓ | mutui |
| GET | `/api/mutui/{mutuo_id}` | ✓ | mutui |
| PUT | `/api/mutui/{mutuo_id}` | ✓ | mutui |
| DELETE | `/api/mutui/{mutuo_id}` | ✓ | mutui |
| GET | `/api/mutui/{mutuo_id}/rate` | ✓ | mutui |
| PUT | `/api/mutui/{mutuo_id}/rate/{numero_rata}/riconcilia` | ✓ | mutui |

## Mutui Parser  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/mutui/import-pdf` | ✓ | mutui_parser |
| POST | `/api/mutui/parse-multiple` | ✓ | mutui_parser |
| POST | `/api/mutui/parse-pdf` | ✓ | mutui_parser |

## Noleggio Auto  (13)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/noleggio/associa-fornitore` | ✓ | noleggio |
| POST | `/api/noleggio/controllo-canoni` | — | noleggio |
| GET | `/api/noleggio/drivers` | ✓ | noleggio |
| GET | `/api/noleggio/export-pdf-costi` | ✓ | noleggio |
| GET | `/api/noleggio/fatture-non-associate` | ✓ | noleggio |
| GET | `/api/noleggio/fornitori` | ✓ | noleggio |
| GET | `/api/noleggio/riepilogo-controlli` | ✓ | noleggio |
| GET | `/api/noleggio/veicoli` | ✓ | noleggio |
| POST | `/api/noleggio/veicoli` | ✓ | noleggio |
| PUT | `/api/noleggio/veicoli/{targa}` | ✓ | noleggio |
| DELETE | `/api/noleggio/veicoli/{targa}` | ✓ | noleggio |
| GET | `/api/noleggio/veicoli/{targa}/completo` | ✓ | noleggio |
| GET | `/api/noleggio/verbali-dipendente` | — | noleggio |

## OpenAPI Automotive  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/openapi-automotive/aggiorna-veicolo` | ext | openapi_automotive |
| GET | `/api/openapi-automotive/assicurazione/{targa}` | ext | openapi_automotive |
| GET | `/api/openapi-automotive/info/{targa}` | ext | openapi_automotive |
| GET | `/api/openapi-automotive/status` | ext | openapi_automotive |
| GET | `/api/openapi-automotive/veicoli-da-aggiornare` | ext | openapi_automotive |

## OpenAPI Imprese  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/openapi-imprese/aggiorna-fornitore` | ext | openapi_imprese |
| GET | `/api/openapi-imprese/cerca` | ext | openapi_imprese |
| GET | `/api/openapi-imprese/info/{partita_iva}` | ext | openapi_imprese |
| GET | `/api/openapi-imprese/pec/{partita_iva}` | ext | openapi_imprese |
| GET | `/api/openapi-imprese/sdi/{partita_iva}` | ext | openapi_imprese |
| GET | `/api/openapi-imprese/status` | ext | openapi_imprese |

## OpenAPI.it  (11)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/openapi/aisp/connetti-conto` | ext | openapi_it |
| GET | `/api/openapi/aisp/movimenti` | ext | openapi_it |
| GET | `/api/openapi/aisp/status` | ext | openapi_it |
| POST | `/api/openapi/visure/richiedi` | ext | openapi_it |
| GET | `/api/openapi/xbrl/bilancio/{request_id}` | ext | openapi_it |
| GET | `/api/openapi/xbrl/download/{request_id}` | ext | openapi_it |
| GET | `/api/openapi/xbrl/download/{request_id}/{tipo}` | ext | openapi_it |
| POST | `/api/openapi/xbrl/richiedi-bilancio` | ext | openapi_it |
| POST | `/api/openapi/xbrl/richiedi-riclassificato` | ext | openapi_it |
| GET | `/api/openapi/xbrl/status` | ext | openapi_it |
| GET | `/api/openapi/xbrl/storico-richieste` | ext | openapi_it |

## Operazioni  (10)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/operazioni-da-confermare/smart/analizza` | ✓ | operazioni_module.smart |
| GET | `/api/operazioni-da-confermare/smart/banca-veloce` | ✓ | operazioni_module.smart |
| GET | `/api/operazioni-da-confermare/smart/cerca-f24` | ✓ | operazioni_module.smart |
| GET | `/api/operazioni-da-confermare/smart/cerca-fatture` | — | operazioni_module.smart |
| GET | `/api/operazioni-da-confermare/smart/cerca-stipendi` | ✓ | operazioni_module.smart |
| POST | `/api/operazioni-da-confermare/smart/conferma-f24` | ✓ | operazioni_module.smart |
| POST | `/api/operazioni-da-confermare/smart/ignora` | ✓ | operazioni_module |
| GET | `/api/operazioni-da-confermare/smart/movimento/{movimento_id}` | — | operazioni_module.smart |
| POST | `/api/operazioni-da-confermare/smart/riconcilia-manuale` | ✓ | operazioni_module.smart |
| POST | `/api/operazioni-da-confermare/smart/riconcilia-stipendio` | ✓ | operazioni_module |

## PIN Login  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/auth/pin-login` | ext | pin_login |
| GET | `/api/auth/pin-login/health` | ext | pin_login |

## POS Check  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/pos-corrispettivi/alert-oggi` | — | pos_corrispettivi_check |
| GET | `/api/pos-corrispettivi/anomalie-gravi` | — | pos_corrispettivi_check |
| PUT | `/api/pos-corrispettivi/chiusura-giornaliera` | ✓ | pos_corrispettivi_check |
| GET | `/api/pos-corrispettivi/chiusura-giornaliera/audit` | ✓ | pos_corrispettivi_check |
| POST | `/api/pos-corrispettivi/chiusure-giornaliere/batch` | ✓ | pos_corrispettivi_check |
| GET | `/api/pos-corrispettivi/controllo-due-fasi` | ✓ | pos_corrispettivi_check |
| POST | `/api/pos-corrispettivi/riconcilia-pos-giorno` | — | pos_corrispettivi_check |
| GET | `/api/pos-corrispettivi/riepilogo-mensile` | ✓ | pos_corrispettivi_check |
| GET | `/api/pos-corrispettivi/verifica-coerenza` | ✓ | pos_corrispettivi_check |

## Pagamenti buoni  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/pagamenti-buoni` | — | pagamenti_buoni |
| POST | `/api/pagamenti-buoni/import` | — | pagamenti_buoni |

## PagoPA  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/pagopa/auto-associa` | ✓ | pagopa |
| POST | `/api/pagopa/cerca-movimenti-pagopa` | — | pagopa |
| GET | `/api/pagopa/movimenti-agenzia-entrate` | — | pagopa |
| GET | `/api/pagopa/ricevute` | ✓ | pagopa |
| POST | `/api/pagopa/ricevute/associa-manuale` | ✓ | pagopa |
| POST | `/api/pagopa/ricevute/upload` | ✓ | pagopa |
| GET | `/api/pagopa/ricevute/{ricevuta_id}/pdf` | ✓ | pagopa |
| GET | `/api/pagopa/stats` | ✓ | pagopa |

## Partite Aperte  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/partite-aperte/lista` | — | partite_aperte_api |
| GET | `/api/partite-aperte/scadute` | — | partite_aperte_api |
| GET | `/api/partite-aperte/stats` | — | partite_aperte_api |

## PayPal  (16)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/paypal-statements/auto-associa` | — | paypal_statements |
| POST | `/api/paypal-statements/auto-cerca-gmail` | — | paypal_statements |
| GET | `/api/paypal-statements/bank-movements` | ✓ | paypal_statements |
| GET | `/api/paypal-statements/dashboard` | ✓ | paypal_statements |
| POST | `/api/paypal-statements/import-all-local` | — | paypal_statements |
| POST | `/api/paypal-statements/import-csv` | — | paypal_statements |
| POST | `/api/paypal-statements/import-pdf` | — | paypal_statements |
| POST | `/api/paypal-statements/pulisci-match-solo-importo` | — | paypal_statements |
| GET | `/api/paypal-statements/report` | ✓ | paypal_statements |
| POST | `/api/paypal-statements/riconcilia-banca` | ✓ | paypal_statements |
| POST | `/api/paypal-statements/riprocessa` | ✓ | paypal_statements |
| GET | `/api/paypal-statements/statements` | ✓ | paypal_statements |
| GET | `/api/paypal-statements/transactions` | ✓ | paypal_statements |
| POST | `/api/paypal-statements/transazione/{transaction_id}/associa` | — | paypal_statements |
| GET | `/api/paypal-statements/transazione/{transaction_id}/cerca-gmail` | — | paypal_statements |
| GET | `/api/paypal-statements/transazione/{transaction_id}/dettaglio` | ✓ | paypal_statements |

## PayPal API  (11)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/paypal-api/account-ids-non-mappati` | ✓ | paypal_api |
| POST | `/api/paypal-api/account/{paypal_account_id}/cerca-fattura-email` | — | paypal_api |
| POST | `/api/paypal-api/crea-fornitore-e-mappa` | ✓ | paypal_api |
| POST | `/api/paypal-api/mappa-fornitore` | ✓ | paypal_api |
| GET | `/api/paypal-api/ricevuta-pdf/{transaction_id}` | — | paypal_api |
| POST | `/api/paypal-api/riconcilia` | ✓ | paypal_api |
| POST | `/api/paypal-api/smappa-fornitore` | — | paypal_api |
| GET | `/api/paypal-api/status` | ✓ | paypal_api |
| POST | `/api/paypal-api/sync` | ✓ | paypal_api |
| POST | `/api/paypal-api/sync/month` | ✓ | paypal_api |
| POST | `/api/paypal-api/webhook` | ext | paypal_api |

## Pianificazione  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/pianificazione/costi-previsionali` | — | pianificazione |
| POST | `/api/pianificazione/costi-previsionali` | — | pianificazione |
| DELETE | `/api/pianificazione/costi-previsionali/{costo_id}` | — | pianificazione |

## Piano dei Conti  (12)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/piano-conti/` | ✓ | accounting.piano_conti |
| POST | `/api/piano-conti/` | ✓ | accounting.piano_conti |
| GET | `/api/piano-conti/bilancio` | ✓ | accounting.piano_conti |
| GET | `/api/piano-conti/conto/{codice}/movimenti` | ✓ | accounting.piano_conti |
| GET | `/api/piano-conti/movimenti` | ✓ | accounting.piano_conti |
| POST | `/api/piano-conti/registra-corrispettivi` | ✓ | accounting.piano_conti |
| POST | `/api/piano-conti/registra-fattura` | ✓ | accounting.piano_conti |
| POST | `/api/piano-conti/registra-tutte-fatture` | ✓ | accounting.piano_conti |
| GET | `/api/piano-conti/regole` | ✓ | accounting.piano_conti |
| POST | `/api/piano-conti/regole` | ✓ | accounting.piano_conti |
| PUT | `/api/piano-conti/{conto_id}` | ✓ | accounting.piano_conti |
| DELETE | `/api/piano-conti/{conto_id}` | ✓ | accounting.piano_conti |

## Previsioni Acquisti  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/previsioni-acquisti/confronto-ordine` | — | previsioni_acquisti |
| POST | `/api/previsioni-acquisti/popola-storico` | ✓ | previsioni_acquisti |
| GET | `/api/previsioni-acquisti/previsioni` | ✓ | previsioni_acquisti |
| GET | `/api/previsioni-acquisti/prodotti` | — | previsioni_acquisti |
| GET | `/api/previsioni-acquisti/statistiche` | ✓ | previsioni_acquisti |

## Prima Nota  (83)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/prima-nota/anni-disponibili` | — | prima_nota_module.stats |
| POST | `/api/prima-nota/annulla-associazione-fattura-banca` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/arricchisci-pagamenti-banca` | — | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/banca` | ✓ | prima_nota_module.banca |
| POST | `/api/prima-nota/banca` | ✓ | prima_nota_module.banca |
| GET | `/api/prima-nota/banca/analisi-righe-grezze` | ✓ | prima_nota_module.banca |
| GET | `/api/prima-nota/banca/candidati-per-fattura` | ✓ | prima_nota_module.banca |
| DELETE | `/api/prima-nota/banca/delete-all` | ✓ | prima_nota_module.banca |
| DELETE | `/api/prima-nota/banca/delete-by-source/{source}` | ✓ | prima_nota_module.banca |
| GET | `/api/prima-nota/banca/in-attesa-documento` | ✓ | prima_nota_module.banca |
| POST | `/api/prima-nota/banca/sync-estratto-conto` | ✓ | prima_nota_module.sync |
| GET | `/api/prima-nota/banca/template-csv` | ✓ | prima_nota_module |
| PUT | `/api/prima-nota/banca/{movimento_id}` | ✓ | prima_nota_module.banca |
| DELETE | `/api/prima-nota/banca/{movimento_id}` | ✓ | prima_nota_module.banca |
| GET | `/api/prima-nota/banca/{movimento_id}/fattura` | ✓ | prima_nota_module.banca |
| GET | `/api/prima-nota/cassa` | ✓ | prima_nota_module.cassa |
| POST | `/api/prima-nota/cassa` | ✓ | prima_nota_module.cassa |
| GET | `/api/prima-nota/cassa/analisi-movimenti-bancari-errati` | ✓ | prima_nota_module.cassa |
| POST | `/api/prima-nota/cassa/crea-entrata-da-corrispettivo` | ✓ | prima_nota_module.sync |
| DELETE | `/api/prima-nota/cassa/delete-all` | ✓ | prima_nota_module.cassa |
| DELETE | `/api/prima-nota/cassa/delete-by-source/{source}` | ✓ | prima_nota_module.cassa |
| DELETE | `/api/prima-nota/cassa/elimina-movimenti-bancari-errati` | ✓ | prima_nota_module.cassa |
| POST | `/api/prima-nota/cassa/fix-corrispettivi-importo` | ✓ | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/cassa/sync-corrispettivi` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/cassa/sync-fatture-pagate` | ✓ | prima_nota_module.sync |
| GET | `/api/prima-nota/cassa/template-csv` | ✓ | prima_nota_module |
| GET | `/api/prima-nota/cassa/verifica-entrate-corrispettivi` | ✓ | prima_nota_module.manutenzione |
| PUT | `/api/prima-nota/cassa/{movimento_id}` | ✓ | prima_nota_module.cassa |
| DELETE | `/api/prima-nota/cassa/{movimento_id}` | ✓ | prima_nota_module.cassa |
| GET | `/api/prima-nota/cassa/{movimento_id}/fattura` | ✓ | prima_nota_module.cassa |
| POST | `/api/prima-nota/cleanup-orphan-movements` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/collega-banca-estratto-conto` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/collega-corrispettivi` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/collega-fatture` | — | prima_nota_module.sync |
| GET | `/api/prima-nota/corrispettivi-status` | — | prima_nota_module.sync |
| POST | `/api/prima-nota/dedup-fatture` | ✓ | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/dedup-righe-estratto-conto` | — | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/diagnostica-corrispettivi` | ✓ | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/diagnostica-metodi` | ✓ | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/export/excel` | — | prima_nota_module.stats |
| POST | `/api/prima-nota/fix-categories-and-duplicates` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/fix-date-formato-italiano` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/fix-tipo-movimento` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/fix-versamenti-duplicati` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/import-batch` | — | prima_nota_module.sync |
| POST | `/api/prima-nota/migra-pos-accrediti-reali` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/migrazione-pulisci-bancari-cassa` | — | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/movimenti-ec-non-in-prima-nota` | ✓ | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/movimento` | — | prima_nota_module.sync |
| GET | `/api/prima-nota/provvisori` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/annulla-auto-conferma` | ✓ | prima_nota_module.sync |
| GET | `/api/prima-nota/provvisori/assegni-proposti` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/associa-assegno` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/attendi-banca` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/auto-conferma-per-metodo` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/conferma` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/conferma-divisione` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/conferma-multipla` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/da-decidere` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/provvisori/segnala-dubbio` | ✓ | prima_nota_module.sync |
| POST | `/api/prima-nota/pulizia-pre-anno` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/recalculate-balances` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/regenerate-from-invoices` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/registra-fattura` | — | prima_nota_module.sync |
| POST | `/api/prima-nota/ripristina-fatture-movimento-cancellato` | — | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/ripristina-provvisori-metodo-errato` | — | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/salari` | — | prima_nota_module.salari |
| POST | `/api/prima-nota/salari` | — | prima_nota_module.salari |
| GET | `/api/prima-nota/salari/stats` | — | prima_nota_module.salari |
| DELETE | `/api/prima-nota/salari/{movimento_id}` | — | prima_nota_module.salari |
| GET | `/api/prima-nota/saldi-finanziari` | — | prima_nota_module.stats |
| GET | `/api/prima-nota/saldo-finale` | — | prima_nota_module.stats |
| GET | `/api/prima-nota/saldo-iniziale` | ✓ | prima_nota_module.stats |
| PUT | `/api/prima-nota/saldo-iniziale` | ✓ | prima_nota_module.stats |
| DELETE | `/api/prima-nota/saldo-iniziale/{tipo}/{anno}` | ✓ | prima_nota_module.stats |
| POST | `/api/prima-nota/sposta-cassa-pagate-in-banca` | — | prima_nota_module.sync |
| POST | `/api/prima-nota/sposta-movimento` | ✓ | prima_nota_module.manutenzione |
| POST | `/api/prima-nota/sposta-scrittura` | ✓ | prima_nota_module.sync |
| GET | `/api/prima-nota/stats` | ✓ | prima_nota_module.stats |
| GET | `/api/prima-nota/sumup` | ✓ | prima_nota_module.banca |
| POST | `/api/prima-nota/sync-corrispettivi` | — | prima_nota_module.sync |
| POST | `/api/prima-nota/unifica-categorie` | — | prima_nota_module.manutenzione |
| GET | `/api/prima-nota/verifica-metodo-fattura/{fattura_id}` | — | prima_nota_module.manutenzione |

## Prima Nota Salari  (20)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/prima-nota-salari/consolida-record` | — | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/dipendenti-lista` | ✓ | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/export-appdipendenti/download` | ✓ | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/export-appdipendenti/preview` | — | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/export-excel` | — | accounting.prima_nota_salari |
| POST | `/api/prima-nota-salari/import-bonifici` | ✓ | accounting.prima_nota_salari |
| POST | `/api/prima-nota-salari/import-paghe` | ✓ | accounting.prima_nota_salari |
| DELETE | `/api/prima-nota-salari/pulisci-righe-vuote` | — | accounting.prima_nota_salari |
| POST | `/api/prima-nota-salari/ricalcola-progressivi` | ✓ | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/salari` | ✓ | accounting.prima_nota_salari |
| POST | `/api/prima-nota-salari/salari/aggiustamento` | ✓ | accounting.prima_nota_salari |
| DELETE | `/api/prima-nota-salari/salari/reset` | ✓ | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/salari/riepilogo` | ✓ | accounting.prima_nota_salari |
| DELETE | `/api/prima-nota-salari/salari/{record_id}` | ✓ | accounting.prima_nota_salari |
| PUT | `/api/prima-nota-salari/salari/{record_id}` | ✓ | accounting.prima_nota_salari |
| POST | `/api/prima-nota-salari/salari/{record_id}/bonifico-pdf` | ✓ | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/salari/{record_id}/bonifico-pdf` | ✓ | accounting.prima_nota_salari |
| GET | `/api/prima-nota-salari/salari/{record_id}/cedolino-pdf` | ✓ | accounting.prima_nota_salari |
| POST | `/api/prima-nota-salari/salari/{record_id}/cedolino-pdf` | ✓ | accounting.prima_nota_salari |
| PUT | `/api/prima-nota-salari/salari/{record_id}/riconcilia` | ✓ | accounting.prima_nota_salari |

## Public API  (26)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/assegni` | ✓ | public_api |
| GET | `/api/assegni-legacy` | ✓ | public_api |
| GET | `/api/bank/statements` | ✓ | public_api |
| POST | `/api/bank/statements` | ✓ | public_api |
| GET | `/api/cash` | ✓ | public_api |
| POST | `/api/cash` | ✓ | public_api |
| GET | `/api/dashboard/stats-legacy` | — | public_api |
| GET | `/api/f24-public/alerts` | ext | public_api |
| GET | `/api/f24-public/dashboard` | ext | public_api |
| GET | `/api/pianificazione/events` | ✓ | public_api |
| POST | `/api/pianificazione/events` | ✓ | public_api |
| POST | `/api/portal/upload` | ext | public_api |
| GET | `/api/ricerca-globale` | — | public_api |
| POST | `/api/suppliers-legacy` | ✓ | public_api |
| GET | `/api/suppliers/{supplier_id}/inventory` | ✓ | public_api |
| GET | `/api/v1/fatture` | ext | public_api |
| GET | `/api/v1/keys` | ext | public_api |
| POST | `/api/v1/keys/generate` | ext | public_api |
| GET | `/api/v1/movimenti` | ext | public_api |
| GET | `/api/v1/stats` | ext | public_api |
| GET | `/api/warehouse/movements` | — | public_api |
| POST | `/api/warehouse/movements` | — | public_api |
| GET | `/api/warehouse/products` | ✓ | public_api |
| POST | `/api/warehouse/products` | ✓ | public_api |
| PUT | `/api/warehouse/products/{product_id}` | ✓ | public_api |
| DELETE | `/api/warehouse/products/{product_id}` | ✓ | public_api |

## Quietanze Drive  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/f24/quietanze/drive/quadratura` | ✓ | drive_quietanze |
| GET | `/api/f24/quietanze/drive/status` | ✓ | drive_quietanze |
| POST | `/api/f24/quietanze/drive/sync` | ✓ | drive_quietanze |

## Regole  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/regole` | ✓ | accounting.regole_categorizzazione |
| POST | `/api/regole/categorie` | ✓ | accounting.regole_categorizzazione |
| POST | `/api/regole/descrizione` | ✓ | accounting.regole_categorizzazione |
| GET | `/api/regole/download-regole` | ✓ | accounting.regole_categorizzazione |
| DELETE | `/api/regole/elimina/{tipo}/{pattern}` | ✓ | accounting.regole_categorizzazione |
| POST | `/api/regole/fornitore` | ✓ | accounting.regole_categorizzazione |
| POST | `/api/regole/upload-regole` | ✓ | accounting.regole_categorizzazione |

## Riconciliazione F24 Banca  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/f24-riconciliazione/estratti-conto` | ✓ | bank.riconciliazione_f24_banca |
| GET | `/api/f24-riconciliazione/movimenti-f24-banca` | ✓ | bank.riconciliazione_f24_banca |
| POST | `/api/f24-riconciliazione/riconcilia-f24` | ✓ | bank.riconciliazione_f24_banca |
| GET | `/api/f24-riconciliazione/stato-riconciliazione` | ✓ | bank.riconciliazione_f24_banca |
| POST | `/api/f24-riconciliazione/upload-estratto-bpm` | ✓ | bank.riconciliazione_f24_banca |

## Riconciliazione Stats  (1)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/riconciliazione/stats` | — | riconciliazione_stats_api |

## Ritenute  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/ritenute` | ✓ | ritenute |
| GET | `/api/ritenute/codici-ravvedimento` | ✓ | ritenute |
| POST | `/api/ritenute/scan` | ✓ | ritenute |

## Scadenzario  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/scadenzario-fornitori/` | ✓ | scadenzario_fornitori |
| PUT | `/api/scadenzario-fornitori/aggiorna-scadenza` | ✓ | scadenzario_fornitori |
| GET | `/api/scadenzario-fornitori/aging` | ✓ | scadenzario_fornitori |
| GET | `/api/scadenzario-fornitori/cash-flow-previsionale` | ✓ | scadenzario_fornitori |
| GET | `/api/scadenzario-fornitori/scadenze-integrate` | ✓ | scadenzario_fornitori |
| GET | `/api/scadenzario-fornitori/urgenti` | ✓ | scadenzario_fornitori |

## Scadenze  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/scadenze` | ✓ | scadenze |
| GET | `/api/scadenze/` | ✓ | scadenze |
| PUT | `/api/scadenze/completa/{notifica_id}` | ✓ | scadenze |
| POST | `/api/scadenze/crea` | ✓ | scadenze |
| GET | `/api/scadenze/dashboard-widget` | ✓ | scadenze |
| GET | `/api/scadenze/iva-mensile/{anno}` | ✓ | scadenze |
| GET | `/api/scadenze/prossime` | ✓ | scadenze |
| GET | `/api/scadenze/tutte` | ✓ | scadenze |
| DELETE | `/api/scadenze/{notifica_id}` | ✓ | scadenze |

## Settings  (9)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/settings/anthropic` | — | settings_router |
| POST | `/api/settings/anthropic` | — | settings_router |
| POST | `/api/settings/anthropic/test` | — | settings_router |
| GET | `/api/settings/gmail` | ✓ | settings_router |
| POST | `/api/settings/gmail` | ✓ | settings_router |
| POST | `/api/settings/gmail/test` | ✓ | settings_router |
| GET | `/api/settings/openai` | ✓ | settings_router |
| POST | `/api/settings/openai` | ✓ | settings_router |
| POST | `/api/settings/openai/test` | ✓ | settings_router |

## Settings Base  (6)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/settings` | ✓ | settings |
| PUT | `/api/settings` | ✓ | settings |
| GET | `/api/settings/logo` | — | settings |
| POST | `/api/settings/logo` | — | settings |
| GET | `/api/settings/user-preferences` | — | settings |
| PUT | `/api/settings/user-preferences` | — | settings |

## Situazione fiscale  (20)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/fiscal/ader-snapshots` | ✓ | fiscal_control |
| POST | `/api/fiscal/ader-snapshots/dry-run` | ✓ | fiscal_control |
| POST | `/api/fiscal/ader-snapshots/import` | ✓ | fiscal_control |
| POST | `/api/fiscal/collection-snapshots/dry-run` | — | fiscal_control |
| POST | `/api/fiscal/collection-snapshots/import` | — | fiscal_control |
| GET | `/api/fiscal/collections` | ✓ | fiscal_control |
| GET | `/api/fiscal/collections/{claim_id}` | ✓ | fiscal_control |
| POST | `/api/fiscal/collections/{claim_id}/events` | ✓ | fiscal_control |
| GET | `/api/fiscal/crosswalk` | ✓ | fiscal_control |
| GET | `/api/fiscal/documents/{document_id}/content` | — | fiscal_control |
| GET | `/api/fiscal/dossier.pdf` | ✓ | fiscal_control |
| GET | `/api/fiscal/evidence-package.zip` | ✓ | fiscal_control |
| GET | `/api/fiscal/evidence/{entity_type}/{entity_id}` | — | fiscal_control |
| GET | `/api/fiscal/f24-documents` | — | fiscal_control |
| GET | `/api/fiscal/f24-rows` | ✓ | fiscal_control |
| GET | `/api/fiscal/obligations` | ✓ | fiscal_control |
| POST | `/api/fiscal/ravvedimento/calculate` | — | fiscal_control |
| GET | `/api/fiscal/review` | ✓ | fiscal_control |
| GET | `/api/fiscal/summary` | ✓ | fiscal_control |
| POST | `/api/fiscal/vat-credit-chain/rebuild` | — | fiscal_control |

## SumUp  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/sumup/bonifica-accrediti-numia` | — | sumup |
| GET | `/api/sumup/bonifica-pos-xml` | — | sumup |
| POST | `/api/sumup/bonifica-pos-xml` | — | sumup |
| POST | `/api/sumup/normalizza-descrizioni-pos` | — | sumup |
| GET | `/api/sumup/riepilogo` | ✓ | sumup |
| POST | `/api/sumup/sincronizza` | — | sumup |
| GET | `/api/sumup/stato` | — | sumup |

## Suppliers  (32)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/suppliers` | ✓ | suppliers_module.base |
| POST | `/api/suppliers` | ✓ | suppliers_module.base |
| POST | `/api/suppliers/aggiorna-dizionario-metodo` | ✓ | suppliers_module.validation |
| POST | `/api/suppliers/aggiorna-metodi-bulk` | ✓ | suppliers_module.bulk |
| POST | `/api/suppliers/aggiorna-tutti-bulk` | ✓ | suppliers_module.bulk |
| POST | `/api/suppliers/correggi-nomi-mancanti` | ✓ | suppliers_module.bulk |
| GET | `/api/suppliers/dizionario-metodi-pagamento` | ✓ | suppliers_module.validation |
| POST | `/api/suppliers/elimina-senza-fatture` | ✓ | suppliers_module.bulk |
| GET | `/api/suppliers/filtered` | ✓ | suppliers_module.base |
| POST | `/api/suppliers/import-excel` | ✓ | suppliers_module.import_export |
| GET | `/api/suppliers/payment-methods` | ✓ | suppliers_module.validation |
| GET | `/api/suppliers/payment-terms` | ✓ | suppliers_module.validation |
| POST | `/api/suppliers/ricerca-iban-singolo/{supplier_id}` | ✓ | suppliers_module.iban |
| POST | `/api/suppliers/ricerca-iban-web` | ✓ | suppliers_module.iban |
| POST | `/api/suppliers/ripara-sconosciuti` | ✓ | suppliers_module.bulk |
| GET | `/api/suppliers/scadenze` | ✓ | suppliers_module.base |
| GET | `/api/suppliers/search-piva/{partita_iva}` | ✓ | suppliers_module.base |
| POST | `/api/suppliers/sincronizza-da-fatture` | ✓ | suppliers_module.bulk |
| GET | `/api/suppliers/stats` | ✓ | suppliers_module.base |
| POST | `/api/suppliers/sync-iban` | ✓ | suppliers_module.iban |
| POST | `/api/suppliers/upload-excel` | ✓ | suppliers_module.import_export |
| GET | `/api/suppliers/validazione-p0` | ✓ | suppliers_module.validation |
| GET | `/api/suppliers/{supplier_id}` | ✓ | suppliers_module.base |
| PUT | `/api/suppliers/{supplier_id}` | ✓ | suppliers_module.base |
| DELETE | `/api/suppliers/{supplier_id}` | ✓ | suppliers_module.base |
| GET | `/api/suppliers/{supplier_id}/dati-da-fatture` | ✓ | suppliers_module.base |
| GET | `/api/suppliers/{supplier_id}/fatturato` | ✓ | suppliers_module.base |
| GET | `/api/suppliers/{supplier_id}/fatture` | ✓ | suppliers_module.base |
| GET | `/api/suppliers/{supplier_id}/iban-from-invoices` | ✓ | suppliers_module.base |
| PUT | `/api/suppliers/{supplier_id}/metodo-pagamento` | ✓ | suppliers_module.base |
| PUT | `/api/suppliers/{supplier_id}/nome` | ✓ | suppliers_module.base |
| POST | `/api/suppliers/{supplier_id}/toggle-active` | ✓ | suppliers_module.base |

## Sync Relazionale  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/sync/fatture-cassa-dettaglio` | — | sync_relazionale |
| POST | `/api/sync/match-fatture-banca` | ✓ | sync_relazionale |
| POST | `/api/sync/match-fatture-cassa` | ✓ | sync_relazionale |
| GET | `/api/sync/stato-sincronizzazione` | ✓ | sync_relazionale |
| POST | `/api/sync/sync-all-corrispettivi` | — | sync_relazionale |
| POST | `/api/sync/sync-corrispettivo/{corrispettivo_id}` | — | sync_relazionale |
| POST | `/api/sync/sync-fattura/{fattura_id}` | — | sync_relazionale |
| PUT | `/api/sync/update-fattura-everywhere/{fattura_id}` | — | sync_relazionale |

## TFR  (17)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/tfr/accantonamento` | — | tfr |
| POST | `/api/tfr/acconti` | — | tfr |
| PUT | `/api/tfr/acconti/{acconto_id}` | — | tfr |
| DELETE | `/api/tfr/acconti/{acconto_id}` | — | tfr |
| POST | `/api/tfr/acconti/{acconto_id}/annulla-riconciliazione-banca` | — | tfr |
| GET | `/api/tfr/acconti/{acconto_id}/candidati-banca` | — | tfr |
| POST | `/api/tfr/acconti/{acconto_id}/riconcilia-banca` | — | tfr |
| GET | `/api/tfr/acconti/{dipendente_id}` | — | tfr |
| POST | `/api/tfr/calcola-batch/{anno}` | — | tfr |
| POST | `/api/tfr/cedolini/{cedolino_id}/annulla-scalatura-acconti` | — | tfr |
| GET | `/api/tfr/cedolini/{cedolino_id}/preview-scalatura-acconti` | — | tfr |
| POST | `/api/tfr/cedolini/{cedolino_id}/scala-acconti` | — | tfr |
| POST | `/api/tfr/liquidazione` | — | tfr |
| GET | `/api/tfr/parse-payslips` | — | tfr |
| GET | `/api/tfr/riepilogo-aziendale` | ✓ | tfr |
| GET | `/api/tfr/situazione/{dipendente_id}` | ✓ | tfr |
| GET | `/api/tfr/storico-tfr/{dipendente_id}` | — | tfr |

## Utenti  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/utenti` | ✓ | utenti |
| POST | `/api/utenti` | ✓ | utenti |
| PUT | `/api/utenti/{utente_id}` | ✓ | utenti |
| DELETE | `/api/utenti/{utente_id}` | ✓ | utenti |

## Verbali API  (2)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/verbali-noleggio/dettaglio/{numero_verbale:path}` | ✓ | verbali_noleggio_api |
| POST | `/api/verbali-noleggio/{verbale_id}/upload-quietanza` | — | verbali_noleggio_api |

## Verbali Noleggio  (3)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/verbali-noleggio/dettaglio/{numero_verbale}` | ✓ | verbali_noleggio |
| GET | `/api/verbali-noleggio/pdf/{numero_verbale:path}` | — | verbali_noleggio |
| GET | `/api/verbali-noleggio/verbali-completi` | — | verbali_noleggio |

## Verbali Riconciliazione  (8)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/verbali-riconciliazione/collega-driver-massivo` | ✓ | verbali_riconciliazione |
| GET | `/api/verbali-riconciliazione/dashboard` | ✓ | verbali_riconciliazione |
| GET | `/api/verbali-riconciliazione/lista` | ✓ | verbali_riconciliazione |
| POST | `/api/verbali-riconciliazione/pulisci-duplicati` | ✓ | verbali_riconciliazione |
| POST | `/api/verbali-riconciliazione/riconcilia/{numero_verbale}` | ✓ | verbali_riconciliazione |
| POST | `/api/verbali-riconciliazione/scan-email` | — | verbali_riconciliazione |
| POST | `/api/verbali-riconciliazione/scan-fatture-verbali` | ✓ | verbali_riconciliazione |
| POST | `/api/verbali-riconciliazione/scan-gmail-attendibili` | — | verbali_riconciliazione |

## Verifica Coerenza  (7)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| GET | `/api/verifica-coerenza/completa/{anno}` | ✓ | verifica_coerenza |
| GET | `/api/verifica-coerenza/confronto-iva-completo/{anno}` | ✓ | verifica_coerenza |
| GET | `/api/verifica-coerenza/discrepanze/{anno}` | — | verifica_coerenza |
| GET | `/api/verifica-coerenza/iva/{anno}/{mese}` | ✓ | verifica_coerenza |
| GET | `/api/verifica-coerenza/riepilogo-giornaliero` | — | verifica_coerenza |
| GET | `/api/verifica-coerenza/verifica-bonifici-vs-banca/{anno}` | — | verifica_coerenza |
| GET | `/api/verifica-coerenza/widget` | — | verifica_coerenza |

## Voci Bilancio Manuali  (4)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/voci-bilancio/` | ✓ | voci_bilancio |
| GET | `/api/voci-bilancio/codici-disponibili` | ✓ | voci_bilancio |
| GET | `/api/voci-bilancio/{anno}` | ✓ | voci_bilancio |
| DELETE | `/api/voci-bilancio/{voce_id}` | ✓ | voci_bilancio |

## WhatsApp  (5)

| Metodo | Path | FE | File |
|---|---|:-:|---|
| POST | `/api/whatsapp/send` | ext | whatsapp_webhook |
| POST | `/api/whatsapp/send-test` | ext | whatsapp_webhook |
| GET | `/api/whatsapp/status` | ext | whatsapp_webhook |
| GET | `/api/whatsapp/webhook` | ext | whatsapp_webhook |
| POST | `/api/whatsapp/webhook` | ext | whatsapp_webhook |

