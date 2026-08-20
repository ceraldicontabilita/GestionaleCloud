# Audit statico automatico

Generato da `scripts/audit_static.py`.


## Sintesi

- P1: 317
- P2: 6
- P3: 67
- INFO: 16

## Findings

### INFO - fornitori-api

- File: `frontend/src/api.js:116`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/api.js:121`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:126`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1501`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1542`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1586`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1589`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1632`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1655`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1689`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1713`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1785`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1810`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1863`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1899`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1925`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### P1 - body

- File: `app/routers/accounting/centri_costo.py:210`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/centri_costo.py:612`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_avanzata.py:95`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_avanzata.py:153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:560`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:820`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:1196`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/piano_conti.py:1228`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/piano_conti.py:1239`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:330`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:398`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:577`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:699`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:1002`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:1205`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/regole_categorizzazione.py:467`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/regole_categorizzazione.py:504`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/regole_categorizzazione.py:553`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin.py:60`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin.py:187`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin.py:210`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin.py:249`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/routers/admin.py:263`

- Dettaglio: collection fornitori deprecata: usare costante che punta a fornitori

### P1 - collection

- File: `app/routers/admin.py:264`

- Dettaglio: collection dipendenti deprecata: usare dipendenti

### P1 - collection

- File: `app/routers/admin.py:325`

- Dettaglio: collection fornitori deprecata: usare costante che punta a fornitori

### P1 - collection

- File: `app/routers/admin.py:327`

- Dettaglio: collection dipendenti deprecata: usare dipendenti

### P1 - body

- File: `app/routers/admin.py:507`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin_rollback.py:255`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin_rollback.py:262`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/agenti.py:228`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/agenti.py:235`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:26`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:121`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:193`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:261`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:340`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:462`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:482`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:512`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/alerts.py:147`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/alerts.py:163`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/alerts.py:196`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - missing-required-file

- File: `app/routers/attendance_module/export_consulente.py:0`

- Dettaglio: File richiesto mancante.

### P1 - missing-required-file

- File: `app/routers/attendance_module/no_import_pdf.py:0`

- Dettaglio: File richiesto mancante.

### P1 - body

- File: `app/routers/auto_repair.py:16`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/auto_repair.py:74`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1070`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1427`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1864`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2206`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2277`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2311`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2328`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2518`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2570`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2740`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2794`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2939`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:3042`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:33`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:143`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:311`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:497`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bank_statement_import.py:666`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bank_statement_import.py:913`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bank_statement_import.py:971`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bonifici_import_unificato.py:26`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:221`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1105`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1220`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1221`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1818`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:2040`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:2080`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/batch_reprocessing.py:127`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/batch_reprocessing.py:141`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/batch_reprocessing.py:153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bonifici_module/associazioni.py:25`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bonifici_module/associazioni.py:206`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bonifici_module/associazioni.py:455`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:186`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:662`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:845`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:996`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:1153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/chiusura_esercizio.py:289`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/chiusura_esercizio.py:471`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/collaudo.py:22`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/configurazioni.py:115`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/configurazioni.py:140`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/configurazioni.py:223`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/configurazioni.py:249`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/configurazioni.py:292`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:44`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:130`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:166`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:175`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:184`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:146`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:172`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:180`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:221`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:229`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:258`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:279`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:311`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:341`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:674`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:878`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:931`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:967`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1018`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1138`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1417`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1584`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1751`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1912`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1983`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:2037`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:2748`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:2782`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti_fiscali.py:25`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documents_inbox_classify.py:155`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documents_inbox_classify.py:339`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documents_inbox_classify.py:516`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_cedolini.py:48`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_corrispettivi.py:27`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_corrispettivi.py:41`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_quietanze.py:28`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_quietanze.py:44`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:45`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:92`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:128`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:154`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:169`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:187`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:360`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:540`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:567`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:583`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:598`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:615`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:632`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:647`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:663`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:676`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:688`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:704`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:725`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:748`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:762`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:920`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:1064`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:1077`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_scanner.py:35`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_scanner.py:66`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_scanner.py:92`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:319`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:1270`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:1454`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:33`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:101`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:493`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:50`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:163`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:399`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:505`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:805`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:882`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_public.py:254`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_public.py:620`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:84`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:312`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:509`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:733`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:794`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1033`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1135`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1427`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:87`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:110`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:172`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:203`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/finanziamenti_soci.py:48`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:375`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:394`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:426`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:463`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:468`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:486`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscal_control.py:494`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:702`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:934`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:1003`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:1097`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:1180`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:222`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:310`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:430`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:495`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:765`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:905`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:62`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:95`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:181`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:232`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:301`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:526`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:607`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:771`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:848`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:861`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:874`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:890`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:1690`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:1716`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_drive.py:27`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_drive.py:43`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1628`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2119`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2215`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2318`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2461`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2641`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:158`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:386`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:452`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:610`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:673`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:937`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:949`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:961`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:973`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:985`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:996`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/learning_machine.py:311`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/learning_machine.py:388`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/learning_universal.py:563`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/mfa.py:61`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/mfa.py:74`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/mfa.py:140`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/mfa.py:166`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/nexi_carta.py:38`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/nexi_carta.py:45`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/noleggio.py:142`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_automotive.py:88`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_imprese.py:60`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:93`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:296`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:518`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:572`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pagopa.py:171`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pagopa.py:242`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pagopa.py:339`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_api.py:482`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:1453`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:1465`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:1488`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:1555`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pos_corrispettivi_check.py:606`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/previsioni_acquisti.py:369`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/public_api.py:610`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/rapido.py:123`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ritenute.py:398`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/scadenzario_fornitori.py:319`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/scadenze.py:388`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings.py:108`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings_router.py:78`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings_router.py:168`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings_router.py:235`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/base.py:642`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/routers/suppliers_module/base.py:871`

- Dettaglio: warehouse_stocks legacy: non usare come fonte primaria

### P1 - body

- File: `app/routers/suppliers_module/base.py:907`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/bulk.py:20`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/bulk.py:224`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/bulk.py:298`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/iban.py:21`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/iban.py:186`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/iban.py:256`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/import_export.py:18`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/import_export.py:117`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:349`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:360`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:400`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:410`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:129`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:243`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:492`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:712`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:868`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:1177`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:1246`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:1590`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/trattenute_verbali.py:153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/trattenute_verbali.py:285`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:42`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:86`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:107`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:121`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:140`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:496`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:628`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:705`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:923`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/voci_bilancio.py:89`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:707`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:891`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:984`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:1019`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/services/cascade_operations.py:245`

- Dettaglio: warehouse_stocks legacy: non usare come fonte primaria

### P1 - delete-confirm

- File: `frontend/src/hooks/use-toast.js:30`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/pages/ArchivioFattureRicevute.jsx:227`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/pages/Fornitori.jsx:1714`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/pages/Fornitori.jsx:1951`

- Dettaglio: DELETE senza confirm vicino.

### P1 - missing-required-file

- File: `frontend/src/pages/hr/HRPresenzeExport.jsx:0`

- Dettaglio: File richiesto mancante.

### P1 - delete-confirm

- File: `frontend/src/stores/primaNotaStore.js:134`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/stores/primaNotaStore.js:158`

- Dettaglio: DELETE senza confirm vicino.

### P2 - timezone

- File: `app/routers/learning_universal.py:114`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:132`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:180`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:186`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/paypal_pdf_fetcher.py:81`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_fattura_linker.py:61`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P3 - fetch-race

- File: `frontend/src/App.jsx:33`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/AgentiPanel.jsx:57`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/AssociaMovimentoBanca.jsx:35`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/DriveImportControls.jsx:16`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/InAttesaDocumento.jsx:29`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/LinkedEvidencePanel.jsx:12`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/ModalFattura.jsx:30`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/NotificationBell.jsx:19`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/layout/TopNav.jsx:417`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/contexts/AnnoContext.jsx:27`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/contexts/AuthContext.jsx:30`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/hooks/useData.js:73`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Admin.jsx:79`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Agenti.jsx:440`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ArchivioBonifici.jsx:139`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ArchivioFattureRicevute.jsx:286`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/AttiAmministrativi.jsx:53`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BatchProcessor.jsx:298`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BatchReprocessing.jsx:23`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Bilancio.jsx:70`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BilancioVerifica.jsx:54`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BudgetPrevisionale.jsx:83`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/CalendarioFiscale.jsx:62`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/CedoliniSalari.jsx:99`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ChiusuraEsercizio.jsx:54`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/CoerenzaPOSCorrispettivi.jsx:84`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Commercialista.jsx:75`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ContabilitaAvanzata.jsx:152`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ControlloMensile.jsx:138`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Corrispettivi.jsx:91`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/DatiIsa.jsx:23`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/DettaglioVerbale.jsx:37`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Documenti.jsx:136`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/DriveDocumentIndex.jsx:53`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/FattureEstereVerifica.jsx:113`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/FinanziamentoSoci.jsx:40`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Finanziaria.jsx:37`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneAssegni.jsx:229`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneIVA.jsx:78`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestionePagoPA.jsx:59`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneRiservata.jsx:195`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ImpostazioniF24Email.jsx:299`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/IntegrazioniOpenAPI.jsx:29`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/LearningMachine.jsx:160`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/LearningMachineUniversale.jsx:32`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/LibroGiornale.jsx:50`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/MFAAdmin.jsx:22`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/MittentiEmail.jsx:36`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Mutui.jsx:44`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/NoleggioAuto.jsx:96`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Pianificazione.jsx:26`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/PianoDeiConti.jsx:64`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/PrevisioniAcquisti.jsx:29`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/PrimaNota.jsx:402`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RegoleCategorizzazione.jsx:53`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RiconciliazionePaypal.jsx:71`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RiconciliazioneUnificata.jsx:328`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Ritenute.jsx:38`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Scadenze.jsx:52`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/SituazioneFiscale.jsx:86`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Utenti.jsx:29`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/UtileObiettivo.jsx:24`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerbaliRiconciliazione.jsx:67`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerificaCoerenza.jsx:44`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerificaMovimentiBanca.jsx:52`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/hub/DocumentiHub.jsx:78`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/hub/RiconciliazioneHub.jsx:69`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.
