# Audit statico automatico

Generato da `scripts/audit_static.py`.


## Sintesi

- P1: 307
- P2: 17
- P3: 54
- INFO: 16

## Findings

### INFO - fornitori-api

- File: `frontend/src/api.js:111`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/api.js:116`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:125`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1240`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1278`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1320`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1323`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1359`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1373`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1399`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1423`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1466`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1491`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1544`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1578`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### INFO - fornitori-api

- File: `frontend/src/pages/Fornitori.jsx:1604`

- Dettaglio: API compatibile /api/suppliers: ok se backend usa collection fornitori.

### P1 - body

- File: `app/routers/accounting/centri_costo.py:197`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/centri_costo.py:612`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_avanzata.py:92`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_avanzata.py:150`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:696`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/contabilita_gestionale.py:956`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/piano_conti.py:1130`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/accounting/piano_conti.py:1228`

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

- File: `app/routers/admin.py:319`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin_rollback.py:255`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/admin_rollback.py:262`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:26`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:112`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:178`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:244`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:323`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:445`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:465`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/ai_parser.py:495`

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

- File: `app/routers/bank/assegni.py:618`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:849`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1227`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1568`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1616`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1650`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1667`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:1838`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2007`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2061`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2194`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni.py:2287`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:32`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:141`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:309`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/assegni_learning.py:495`

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

- File: `app/routers/bank/estratto_conto.py:69`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:698`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1324`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/bank/estratto_conto.py:1541`

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

- File: `app/routers/cespiti.py:360`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:490`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:572`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/cespiti.py:683`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/chiusura_esercizio.py:238`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/chiusura_esercizio.py:357`

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

- File: `app/routers/contabilita_italiana.py:477`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:569`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:697`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:736`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:779`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:840`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:968`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/contabilita_italiana.py:1057`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/controllo_gestione.py:268`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:61`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:119`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:202`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:310`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:396`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:432`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:441`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/dati_provvisori.py:450`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:36`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:57`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:89`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:119`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:247`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:447`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:500`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:555`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:675`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:947`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1087`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1248`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1453`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1735`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1896`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:1967`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:2021`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/documenti.py:2263`

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

- File: `app/routers/drive_cedolini.py:71`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/drive_cedolini.py:87`

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

- File: `app/routers/email_download.py:44`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:91`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:127`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:168`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:186`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:359`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:539`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:566`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:582`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:597`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:614`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:631`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:646`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:662`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:675`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:687`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:703`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:724`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:747`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:761`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/email_download.py:1050`

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

- File: `app/routers/employees/dipendenti.py:330`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:1408`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:1711`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:1885`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:2127`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:2289`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/employees/dipendenti.py:2473`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:31`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:99`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/email_f24.py:333`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:50`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:161`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:386`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:483`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:764`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_main.py:834`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_public.py:237`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_public.py:576`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:36`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:257`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:440`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:656`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:717`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:901`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1003`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/f24/f24_riconciliazione.py:1296`

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

- File: `app/routers/fiscalita_italiana.py:682`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:812`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:927`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:1002`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:1144`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fiscalita_italiana.py:1297`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:217`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:289`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:400`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:464`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:656`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/fornitori_learning.py:785`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:52`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:85`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:171`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:222`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:291`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:492`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:573`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:737`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:814`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:827`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:840`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:856`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/corrispettivi.py:1680`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_drive.py:27`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_drive.py:43`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:990`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1182`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1278`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1381`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1524`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/fatture_upload.py:1694`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/invoices/invoices_emesse.py:74`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:52`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:249`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:295`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:364`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/iva.py:423`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/learning_machine.py:309`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/learning_machine.py:384`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/learning_universal.py:547`

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

- File: `app/routers/paypal_api.py:422`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/routers/paypal_statements.py:604`

- Dettaglio: collection dipendenti deprecata: usare dipendenti

### P1 - body

- File: `app/routers/paypal_statements.py:881`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/paypal_statements.py:951`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/pos_corrispettivi_check.py:374`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/previsioni_acquisti.py:356`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/public_api.py:610`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/rapido.py:122`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/scadenzario_fornitori.py:319`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/scadenze.py:397`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings.py:108`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/settings_router.py:77`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/suppliers_module/base.py:429`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/routers/suppliers_module/base.py:604`

- Dettaglio: warehouse_stocks legacy: non usare come fonte primaria

### P1 - body

- File: `app/routers/suppliers_module/base.py:639`

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

- File: `app/routers/sync_relazionale.py:346`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:357`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:397`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/sync_relazionale.py:407`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:107`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:211`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:421`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:641`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:787`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:1096`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:1165`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/tfr.py:1509`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/trattenute_verbali.py:153`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/trattenute_verbali.py:285`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:99`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:266`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:431`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:517`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:537`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:740`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:815`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio.py:838`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio_api.py:169`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio_api.py:329`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio_api.py:353`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio_api.py:400`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio_api.py:453`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_noleggio_api.py:461`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:243`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:318`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:382`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:494`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:571`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:677`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1026`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1089`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1390`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1455`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1495`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1525`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1572`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/verbali_riconciliazione.py:1793`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:706`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:890`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:983`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - body

- File: `app/routers/warehouse/dizionario_articoli.py:1018`

- Dettaglio: POST/PUT con Dict[str, Any] senza Body(...).

### P1 - collection

- File: `app/services/cascade_operations.py:245`

- Dettaglio: warehouse_stocks legacy: non usare come fonte primaria

### P1 - collection

- File: `app/services/trattenute_verbali_service.py:228`

- Dettaglio: collection dipendenti deprecata: usare dipendenti

### P1 - collection

- File: `app/utils/warehouse_helpers.py:327`

- Dettaglio: warehouse_stocks legacy: non usare come fonte primaria

### P1 - delete-confirm

- File: `frontend/src/hooks/use-toast.js:30`

- Dettaglio: DELETE senza confirm vicino.

### P1 - delete-confirm

- File: `frontend/src/pages/Fornitori.jsx:1424`

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

- File: `app/routers/iva.py:103`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:220`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:311`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:380`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:392`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:441`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/iva.py:611`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:109`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:127`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:175`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/routers/learning_universal.py:181`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/paypal_pdf_fetcher.py:81`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_fattura_linker.py:58`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_gmail_scanner.py:268`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_gmail_scanner.py:289`

- Dettaglio: Sostituire con datetime.now(timezone.utc).

### P2 - timezone

- File: `app/services/verbali_gmail_scanner.py:303`

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

- File: `frontend/src/components/PaypalTransactionDetailModal.jsx:97`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/WidgetAgenti.jsx:37`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/WidgetVerificaCoerenza.jsx:35`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/layout/TopNav.jsx:360`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/components/prima-nota/PrimaNotaSalariTab.jsx:175`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/contexts/AuthContext.jsx:15`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/hooks/useData.js:73`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Admin.jsx:78`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Agenti.jsx:213`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ArchivioBonifici.jsx:138`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/ArchivioFattureRicevute.jsx:100`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BatchProcessor.jsx:298`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BatchReprocessing.jsx:22`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Bilancio.jsx:60`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BilancioVerifica.jsx:53`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/BudgetPrevisionale.jsx:81`

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

- File: `frontend/src/pages/DettaglioVerbale.jsx:23`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Documenti.jsx:132`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/DocumentiFiscali.jsx:39`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneAssegni.jsx:129`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneCespiti.jsx:204`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneIVA.jsx:68`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestionePagoPA.jsx:45`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/GestioneRiservata.jsx:186`

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

- File: `frontend/src/pages/PrimaNota.jsx:149`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RegoleCategorizzazione.jsx:52`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RiconciliazionePaypal.jsx:128`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/RiconciliazioneUnificata.jsx:303`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Scadenze.jsx:55`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/Utenti.jsx:27`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/UtileObiettivo.jsx:24`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerbaliRiconciliazione.jsx:56`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerificaCoerenza.jsx:47`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.

### P3 - fetch-race

- File: `frontend/src/pages/VerificaMovimentiBanca.jsx:32`

- Dettaglio: api.get in componente con useEffect senza AbortController; verificare race condition.
