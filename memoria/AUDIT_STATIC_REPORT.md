# Audit statico automatico

Generato da `scripts/audit_static.py`.


## Sintesi

- P1: 279
- P2: 17
- P3: 55
- INFO: 16

## Findings

### INFO - fornitori-api

- File: `frontend/src/api.js:111`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/api.js:116`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:127`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1262`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1300`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1342`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1345`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1381`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1395`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1423`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1449`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1521`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1546`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1599`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1633`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1659`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### P1 - body

- File: `app/routers/accounting/centri_costo.py:210`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/centri_costo.py:603`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_avanzata.py:93`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_avanzata.py:151`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:698`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:958`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:1177`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/piano_conti.py:1135`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/piano_conti.py:1146`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:137`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:257`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:455`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/prima_nota_salari.py:623`

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

### P1 - collection

- File: `app/routers/admin.py:24`

- Dettaglio: collection fornitori deprecata: usare costante che punta a fornitori

### P1 - collection

- File: `app/routers/admin.py:25`

- Dettaglio: collection dipendenti deprecata: usare dipendenti

### P1 - collection

- File: `app/routers/admin.py:100`

- Dettaglio: collection fornitori deprecata: usare costante che punta a fornitori

### P1 - collection

- File: `app/routers/admin.py:102`

- Dettaglio: collection dipendenti deprecata: usare dipendenti

### P1 - body

- File: `app/routers/admin.py:159`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin.py:245`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin_rollback.py:255`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin_rollback.py:262`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/agenti.py:212`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/agenti.py:219`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:26`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:112`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:184`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:240`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:319`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:441`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:461`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:491`

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

- File: `app/routers/auto_repair.py:15`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:631`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:883`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1254`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1595`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1643`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1677`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1694`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1863`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2032`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2086`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2221`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2314`

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

- File: `app/routers/bank/bank_statement_import.py:665`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bank_statement_import.py:912`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bank_statement_import.py:970`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/bonifici_import_unificato.py:26`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:166`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:801`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:943`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:944`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1556`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1773`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1813`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bonifici_module/associazioni.py:18`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bonifici_module/associazioni.py:119`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bonifici_module/associazioni.py:283`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:126`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:427`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:564`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:652`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:763`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/chiusura_esercizio.py:238`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/chiusura_esercizio.py:367`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/collaudo.py:20`

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

- File: `app/routers/documenti.py:38`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:59`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:91`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:121`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:249`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:453`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:506`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:542`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:593`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:713`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:985`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1136`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1303`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1464`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1535`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1589`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1832`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti_fiscali.py:35`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documents_inbox_classify.py:153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documents_inbox_classify.py:291`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documents_inbox_classify.py:468`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_cedolini.py:24`

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

- File: `app/routers/f24/email_f24.py:31`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:99`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:403`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:46`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:157`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:389`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:486`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:767`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:837`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_public.py:237`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_public.py:576`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:80`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:322`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:505`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:721`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:782`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:966`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1068`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1361`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:86`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:109`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:171`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24_email_settings.py:202`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/finanziamenti_soci.py:48`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:681`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:811`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:867`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:942`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:217`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:289`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:401`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:466`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:716`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:845`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:54`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:87`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:173`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:224`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:293`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:494`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:575`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:739`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:816`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:829`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:842`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:858`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:1682`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:1708`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_drive.py:27`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_drive.py:43`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1200`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1661`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1757`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1860`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2003`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:2183`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:54`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:251`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:297`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:381`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:440`

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

- File: `app/routers/nexi_carta.py:38`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/nexi_carta.py:45`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/noleggio.py:123`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_automotive.py:94`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_automotive.py:165`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_imprese.py:60`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:93`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:206`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:293`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:515`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/openapi_it.py:569`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pagopa.py:154`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pagopa.py:192`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pagopa.py:266`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_api.py:428`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:903`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:977`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:1038`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pos_corrispettivi_check.py:413`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/previsioni_acquisti.py:356`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/public_api.py:610`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/rapido.py:123`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ritenute.py:201`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/scadenzario_fornitori.py:319`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/scadenze.py:453`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings.py:108`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings_router.py:77`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings_router.py:162`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/base.py:429`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/routers/suppliers_module/base.py:629`

- Dettaglio: warehouse_stocks legacy: non usare come fonte primaria

### P1 - body

- File: `app/routers/suppliers_module/base.py:664`

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

- File: `app/routers/verbali_riconciliazione.py:102`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:261`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:373`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:450`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:549`

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

- File: `frontend/src/pages/ArchivioFattureRicevute.jsx:88`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/pages/Fornitori.jsx:1450`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/pages/Fornitori.jsx:1685`

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

- File: `app/routers/iva.py:105`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:222`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:313`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:397`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:409`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:458`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:628`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

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

- File: `app/services/verbali_fattura_linker.py:58`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_gmail_scanner.py:262`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_gmail_scanner.py:283`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_gmail_scanner.py:297`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_pagamento_finder.py:367`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P3 - fetch-race

- File: `frontend/src/App.jsx:36`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/AgentiPanel.jsx:57`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/NotificationBell.jsx:19`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/PaypalTransactionDetailModal.jsx:99`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/layout/TopNav.jsx:364`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/contexts/AuthContext.jsx:15`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/hooks/useData.js:73`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Admin.jsx:80`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Agenti.jsx:292`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ArchivioBonifici.jsx:138`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ArchivioFattureRicevute.jsx:145`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BatchProcessor.jsx:298`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BatchReprocessing.jsx:25`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Bilancio.jsx:69`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BilancioVerifica.jsx:53`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BudgetPrevisionale.jsx:83`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/CalendarioFiscale.jsx:58`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ChiusuraEsercizio.jsx:52`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/CoerenzaPOSCorrispettivi.jsx:55`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Commercialista.jsx:74`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ContabilitaAvanzata.jsx:152`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ControlloMensile.jsx:135`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Corrispettivi.jsx:72`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/DashboardRelazionale.jsx:49`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/DettaglioVerbale.jsx:27`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Documenti.jsx:133`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/FattureEstereVerifica.jsx:113`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/FinanziamentoSoci.jsx:40`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneAssegni.jsx:137`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneCespiti.jsx:213`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneIVA.jsx:68`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestionePagoPA.jsx:47`

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

- File: `frontend/src/pages/LibroGiornale.jsx:38`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/MittentiEmail.jsx:33`

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

- File: `frontend/src/pages/PianoDeiConti.jsx:44`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/PrevisioniAcquisti.jsx:29`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/PrimaNota.jsx:213`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RegoleCategorizzazione.jsx:52`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RiconciliazionePaypal.jsx:128`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RiconciliazioneUnificata.jsx:304`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Ritenute.jsx:35`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Scadenze.jsx:55`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Utenti.jsx:29`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/UtileObiettivo.jsx:24`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerbaliRiconciliazione.jsx:58`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerificaCoerenza.jsx:47`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerificaMovimentiBanca.jsx:33`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.
