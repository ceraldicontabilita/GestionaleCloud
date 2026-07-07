# Documentazione endpoint — indice

Ogni file spiega, per ogni endpoint del backend, **cosa fa** (lato operativo) e **come funziona nel codice**
(collezioni Mongo, algoritmo, validazioni, helper). Generata leggendo i sorgenti per intero, non i docstring
(quando un docstring mente rispetto al codice, è segnalato in "Note").

| File | Area | Endpoint documentati |
|---|---|---:|
| [01-prima-nota.md](01-prima-nota.md) | Prima Nota (cassa/banca/salari/sync/manutenzione), dati provvisori | 94 |
| [02-contabilita.md](02-contabilita.md) | Contabilità, piano conti, bilancio, IVA, cespiti, mutui, centri di costo | 187 |
| [03-fatture-fornitori.md](03-fatture-fornitori.md) | Fatture (invoices/fatture/fatture-ricevute), corrispettivi, fornitori | ~250 |
| [04-banca-riconciliazione.md](04-banca-riconciliazione.md) | Banca, assegni, bonifici, riconciliazione, PayPal, PagoPA | 228 |
| [05-f24.md](05-f24.md) | F24 e quietanze | 91 |
| [06-documenti-email-ai.md](06-documenti-email-ai.md) | Documenti, email, parser AI, learning machine | 146 |
| [07-hr-noleggio-verbali.md](07-hr-noleggio-verbali.md) | Dipendenti, paghe, TFR, noleggio, verbali | 185 |
| [08-sistema-admin.md](08-sistema-admin.md) | Auth, admin, config, dashboard, integrazioni, varie | 245 |

**Totale: ~1.426 endpoint documentati** (la route table reale ne conta 1.378: la differenza è dovuta a route
duplicate/shadowate contate una volta per modulo che le implementa).

## Anomalie per gravità (sintesi trasversale)

### 🔴 Bug bloccanti (crash a runtime, dati corrotti)

1. **Assegni**: quattro schemi diversi coesistono per collegare un assegno a una fattura (fix parziale già applicato: nuovo endpoint canonico `PUT /api/assegni/{id}/fatture-collegate`, ma i 3 meccanismi legacy — `auto-associa`, `ricostruisci-dati`, `associa-beneficiari-robusto`, `cerca-combinazioni-assegni`, `sync-da-estratto-conto` — scrivono ancora solo campi flat). *(04)*
2. ✔ RISOLTO (lug 2026) — `POST /api/pagamenti/assegno-multi-fatture` e `/fattura-multi-metodo`: ora chiamano `registra_pagamento` con dict diretto (prima TypeError certo). *(04)*
3. ✔ RISOLTO (lug 2026) — `/api/cash/*`: `get_cash_service` ora inietta un vero `CorrissettivoRepository` (prima `CashService(repo, None)` → AttributeError certo). *(04)*
4. ✔ RISOLTO (lug 2026) — `POST /api/riconciliazione-auto/correggi-metodi-pagamento`: il router `riconciliazione_automatica.py` che conteneva il KeyError è stato eliminato interamente nell'audit router (motore duplicato, mai la fonte di verità). *(04)*
5. ✔ RISOLTO (lug 2026) — `sposta-cassa`/`sposta-banca` (dati_provvisori) ora salvano l'importo sempre **positivo** (il segno lo porta `tipo`, come da convenzione della collezione); aggiunti anche i campi `data`/`descrizione` mancanti su sposta-banca. *(01)*
6. ✔ RISOLTO (lug 2026) — `riconciliazione_f24_banca.py` ora definisce localmente `COLL_F24_COMMERCIALISTA = "f24_commercialista"` invece di importare l'alias fuorviante da `db_collections.py` (che vale `"f24_unificato"`), allineandosi alla collezione realmente usata da `f24_riconciliazione.py`/`email_f24.py`. *(05)*
7. ✔ RISOLTO (lug 2026) — `PUT /api/sync/update-fattura-everywhere`: aggiorna in prima nota solo i campi realmente inviati (prima azzerava a null quelli assenti). *(08)*
8. ✔ RISOLTO (lug 2026) — verbali-riconciliazione: lookup fattura ora prova prima l'id UUID e usa ObjectId solo se valido (il crash su driver_id era già stato corretto in precedenza). *(07)*
9. ✔ RISOLTO (lug 2026) — Ammortamenti cespiti: non vengono più scritti in `prima_nota_cassa` (costo non monetario); migrazione all'avvio soft-deleta i movimenti già creati dal bug. *(02)*
10. ✔ RISOLTO (lug 2026) — Ricavi gonfiati: `chiusura_esercizio`, `indici_bilancio` e `controllo_gestione` ora trattano `invoices` come sole fatture ricevute (ricavi = corrispettivi, costi = tutte le fatture − note credito). *(02)*

### 🟠 Shadowing / route irraggiungibili (il codice "vince" non è quello che sembra)

11. **`/api/fatture` upload**: `fatture_overlay` è montato PRIMA di `fatture_upload` → `POST /api/fatture/upload-xml[-bulk]` gira SEMPRE sull'overlay, che **rifiuta i P7M** e non emette l'evento `FATTURA_CREATED` (niente scadenzario/alert automatici). La pipeline "cuore" (`process_xml_bytes`) su questo canale non gira mai. *(03)*
12. **`/api/invoices`**: `invoices_main_overlay` vince su `invoices_main`; dentro `invoices_main` un decoratore duplicato fa sì che `GET /{invoice_id}` risponda con la lista `bank-pending` (bug indipendente dallo shadowing, mascherato dall'overlay). `invoices_export.py` è un intero modulo-stub mai raggiunto. *(03)*
13. ~ RIVERIFICATO (lug 2026) — `/stats` e `/pdf/{n}` sono ora definiti solo in `verbali_noleggio.py` (non più duplicati). `/dettaglio/{n}` resta in entrambi i router sotto lo stesso prefisso, ma non è vero shadowing totale: `verbali_noleggio.py` usa un path-param `str` (non matcha `/`), `verbali_noleggio_api.py` usa `{numero_verbale:path}` — per i numeri verbale SENZA slash vince sempre il primo, per quelli CON slash (es. "S/2259") il primo non matcha e la richiesta cade sul secondo. È quindi uno split funzionale non documentato, non un endpoint morto: da chiarire con un commento nel codice, non urgente. `GET /api/dipendenti/contratti` non è più duplicato (un solo GET + un solo POST in `dipendenti.py`). *(07)*
14. ✔ RISOLTO (lug 2026) — `GET /api/f24/{f24_id}` è ora registrato per ultimo: `/quietanze` non è più shadowata. *(05)*
15. ✔ RISOLTO (lug 2026) — `GET /api/iva/daily/{date_param}`: path param allineato al parametro Python. *(02)*
16. ✔ RIMOSSO (lug 2026) — `POST /api/verbali-noleggio/unifica-verbali`: endpoint tronco eliminato. *(07)*

### 🟡 Architetture parallele non comunicanti (stessa funzione, N implementazioni)

17. **Fatture**: 3 pipeline di import (`process_xml_bytes` "cuore", overlay upsert, `InvoiceService.process_xml_invoice` in invoices_main) + Excel import con `invoice_key` in formato diverso → dedup incrociato impossibile. *(03)*
18. **Riconciliazione**: 4 gruppi paralleli — `/api/riconciliazione`, `/api/riconciliazione-auto`, `/api/riconciliazione-intelligente` (25 route), `/api/operazioni-da-confermare` — più 3 importer estratto conto con schemi/dedup diversi sulla stessa collezione, e 3 circuiti banca↔PayPal con flag diversi. *(04)*
19. **Contabilità**: 3 motori paralleli (`prima_nota_righe` Odoo/CEE, `movimenti_contabili`+saldi piano conti GG.SS.CC, `scritture_contabili` accounting-engine) che non si parlano; 2 sistemi cespiti, 2 chiusure esercizio, 2 sistemi budget, 2 sistemi regole di categorizzazione sulle stesse collezioni con schemi diversi. *(02)*
20. **Fatture ricevute**: `paga-manuale` (fatture-ricevute) duplica `PUT /{id}/paga` (fatture); `cambia-metodo-pagamento` duplica `PUT /{id}/metodo-pagamento`; `archivio` duplica la lista di `/api/invoices`. *(03)*
21. **Email/documenti**: 5 moduli scaricano/classificano la stessa posta verso collezioni diverse (email_download, documenti, email_scanner, email_mongodb, learning_machine); import fatture da email bypassa ancora la pipeline unificata in 2 punti (`email_download/processa-fatture-email`, `ai_parser/parse-fattura`). *(06)*
22. **F24** frammentato su 5 collezioni/moduli; **dipendenti**: doppia anagrafica `employees` (condivisa con AppDipendenti) vs `dipendenti` (locale) — moduli diversi cercano la persona in collezioni diverse. *(05, 07)*
23. `fornitori/sync-suppliers` (in `/api/fatture`) duplica quasi esattamente `suppliers/sincronizza-da-fatture`; due Excel-import fornitori quasi identici. Tutti i punti di creazione automatica fornitore usano **default "bonifico"**, violando la regola "nuovo fornitore → nessun metodo finché non configurato". *(03)*

### 🔵 Sicurezza / esposizione

24. ✔ RISOLTO (lug 2026) — Webhook WhatsApp e ponte ERP ora whitelistati in `PUBLIC_PATHS` (il ponte ERP protetto da un segreto dedicato `ERP_BRIDGE_SECRET` via header `X-Erp-Secret`, non lasciato aperto). `/api/f24-public/*` rimosso da `PUBLIC_PREFIXES`: esponeva lettura E scrittura di F24 reali (importi, upload/modifica/delete PDF) senza alcuna verifica; l'unico chiamante (Dashboard.jsx) usa già il client autenticato, quindi ora richiede JWT come tutto il resto (verificato: 401 senza token). Le pagine legali (`/privacy`, `/terms`, `/data-deletion`) ora whitelistate in `PUBLIC_PATHS`. *(08)*
25. ✔ RISOLTO (lug 2026) — Aggiunta `_autentica_websocket()` dentro `websocket_dashboard`/`websocket_notifications` (verifica JWT da `?token=` o cookie `access_token` PRIMA di `ws_manager.connect()`), dato che `BaseHTTPMiddleware.dispatch()` non viene mai invocato per lo scope `websocket`. Verificato con `TestClient.websocket_connect()`: connessione rifiutata senza token. *(08)*
26. Diversi endpoint distruttivi (delete-all, riconciliazioni automatiche con `dry_run=False` di default) senza alcun controllo di ruolo. *(04, 08)*

### ⚪ Stub / codice morto che finge di funzionare

27. OCR assegni (`estrai-dati`, `leggi-carnet`), `bank/reconcile`, `bank-reconciliation/reconcile|upload`, `cash-register/stats-pos-comparison`, upload ricevute PagoPA, `accounting_extended` (balance-sheet/income-statement/tax-simulation) — tutti rispondono "successo" senza fare il lavoro dichiarato. *(02, 04)*
28. Numerosi endpoint AI/automazione con `BackgroundTasks` dichiarato ma esecuzione sincrona (nessun reale vantaggio asincrono), e diversi con `force_import`/parametri accettati e mai letti.

---

## Come usare questi file

- **Prima di modificare un endpoint**: cerca il suo prefisso qui, leggi la sezione — ti dice subito se è shadowato/morto, quali collezioni tocca davvero, e se il docstring è affidabile.
- **Prima di "consolidare" due router che sembrano fare la stessa cosa**: controlla la sezione Note di entrambi — spesso uno dei due contiene la logica corretta (es. metodo dal fornitore, dedup più robusto) e l'altro è quello da eliminare, ma la scelta va verificata caso per caso confrontando anche i chiamanti reali nel frontend.
- Questi file **descrivono lo stato del codice**, non prescrivono come dovrebbe essere: per la logica di business corretta vedi `memoria/LOGICA_OPERATIVA.md`.
