# Documentazione endpoint — indice

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi legacy/collection restano contesto storico. MongoDB è rimosso e non va usato.

> ⚠️ **Aggiornamento lug 2026**: la mappa endpoint aggiornata e rigenerabile è
> `memoria/MAPPA_ENDPOINT_COMPLETA.md` (ogni endpoint reale con uso frontend) +
> `memoria/MAPPA_MODULI.md` (come funziona ogni dominio + codice morto/duplicati).
> I file numerati qui sotto (01-09) restano come analisi di dettaglio storica.


Ogni file spiega, per ogni endpoint del backend, **cosa fa** (lato operativo) e **come funziona nel codice**
(fogli Drive/Sheets, algoritmo, validazioni, helper). Generata leggendo i sorgenti per intero, non i docstring
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
8. ✔ RISOLTO (lug 2026) — verbali-riconciliazione: lookup fattura ora prova prima l'id UUID e usa identificatore interno solo se valido (il crash su driver_id era già stato corretto in precedenza). *(07)*
9. ✔ RISOLTO (lug 2026) — Ammortamenti cespiti: non vengono più scritti in `prima_nota_cassa` (costo non monetario); migrazione all'avvio soft-deleta i movimenti già creati dal bug. *(02)*
10. ✔ RISOLTO (lug 2026) — Ricavi gonfiati: `chiusura_esercizio`, `indici_bilancio` e `controllo_gestione` ora trattano `invoices` come sole fatture ricevute (ricavi = corrispettivi, costi = tutte le fatture − note credito). *(02)*

### 🟠 Shadowing / route irraggiungibili (il codice "vince" non è quello che sembra)

11. ✔ RISOLTO (lug 2026) — **`/api/fatture` upload**: `fatture_overlay` eliminato nel consolidamento router, resta il solo `fatture_upload.py` canonico (`process_xml_bytes`, accetta P7M, emette `FATTURA_CREATED`). *(03)*
12. ✔ RISOLTO (lug 2026) — **`/api/invoices`**: `invoices_main_overlay` e lo stub morto `invoices_export.py` eliminati nel consolidamento router; `GET /{invoice_id}` in `invoices_main.py` non ha più il decoratore duplicato (route `/bank-pending` registrata correttamente prima di `/{invoice_id}`). *(03)*
13. ~ RIVERIFICATO (lug 2026) — `/stats` e `/pdf/{n}` sono ora definiti solo in `verbali_noleggio.py` (non più duplicati). `/dettaglio/{n}` resta in entrambi i router sotto lo stesso prefisso, ma non è vero shadowing totale: `verbali_noleggio.py` usa un path-param `str` (non matcha `/`), `verbali_noleggio_api.py` usa `{numero_verbale:path}` — per i numeri verbale SENZA slash vince sempre il primo, per quelli CON slash (es. "S/2259") il primo non matcha e la richiesta cade sul secondo. È quindi uno split funzionale non documentato, non un endpoint morto: da chiarire con un commento nel codice, non urgente. `GET /api/dipendenti/contratti` non è più duplicato (un solo GET + un solo POST in `dipendenti.py`). *(07)*
14. ✔ RISOLTO (lug 2026) — `GET /api/f24/{f24_id}` è ora registrato per ultimo: `/quietanze` non è più shadowata. *(05)*
15. ✔ RISOLTO (lug 2026) — `GET /api/iva/daily/{date_param}`: path param allineato al parametro Python. *(02)*
16. ✔ RIMOSSO (lug 2026) — `POST /api/verbali-noleggio/unifica-verbali`: endpoint tronco eliminato. *(07)*

### 🟡 Architetture parallele non comunicanti (stessa funzione, N implementazioni)

17. **Fatture**: 3 pipeline di import (`process_xml_bytes` "cuore", overlay upsert, `InvoiceService.process_xml_invoice` in invoices_main) + Excel import con `invoice_key` in formato diverso → dedup incrociato impossibile. *(03)*
18. **Riconciliazione**: 4 gruppi paralleli — `/api/riconciliazione`, `/api/riconciliazione-auto`, `/api/riconciliazione-intelligente` (25 route), `/api/operazioni-da-confermare` — più 3 importer estratto conto con schemi/dedup diversi sulla stessa collezione, e 3 circuiti banca↔PayPal con flag diversi. *(04)*
19. **Contabilità**: 3 motori paralleli (`prima_nota_righe` Odoo/CEE, `movimenti_contabili`+saldi piano conti GG.SS.CC, `scritture_contabili` accounting-engine) che non si parlano; 2 sistemi cespiti, 2 chiusure esercizio, 2 sistemi budget, 2 sistemi regole di categorizzazione sulle stesse collezioni con schemi diversi. *(02)*
20. **Fatture ricevute**: `paga-manuale` (fatture-ricevute) duplica `PUT /{id}/paga` (fatture); `cambia-metodo-pagamento` duplica `PUT /{id}/metodo-pagamento`; `archivio` duplica la lista di `/api/invoices`. *(03)*
21. **Email/documenti**: 5 moduli scaricano/classificano la stessa posta verso collezioni diverse (email_download, documenti, email_scanner, email_drive_sheets, learning_machine); import fatture da email bypassa ancora la pipeline unificata in 2 punti (`email_download/processa-fatture-email`, `ai_parser/parse-fattura`). *(06)*
22. **F24** frammentato su 5 collezioni/moduli; **dipendenti**: doppia anagrafica `employees` (condivisa con AppDipendenti) vs `dipendenti` (locale) — moduli diversi cercano la persona in collezioni diverse. *(05, 07)*
23. `fornitori/sync-suppliers` (in `/api/fatture`) duplica quasi esattamente `suppliers/sincronizza-da-fatture`; due Excel-import fornitori quasi identici. Tutti i punti di creazione automatica fornitore usano **default "bonifico"**, violando la regola "nuovo fornitore → nessun metodo finché non configurato". *(03)*

### 🔵 Sicurezza / esposizione

24. ✔ RISOLTO (lug 2026) — Webhook WhatsApp e ponte ERP ora whitelistati in `PUBLIC_PATHS` (il ponte ERP protetto da un segreto dedicato `ERP_BRIDGE_SECRET` via header `X-Erp-Secret`, non lasciato aperto). `/api/f24-public/*` rimosso da `PUBLIC_PREFIXES`: esponeva lettura E scrittura di F24 reali (importi, upload/modifica/delete PDF) senza alcuna verifica; l'unico chiamante (Dashboard.jsx) usa già il client autenticato, quindi ora richiede JWT come tutto il resto (verificato: 401 senza token). Le pagine legali (`/privacy`, `/terms`, `/data-deletion`) ora whitelistate in `PUBLIC_PATHS`. *(08)*
25. ✔ RISOLTO (lug 2026) — Aggiunta `_autentica_websocket()` dentro `websocket_dashboard`/`websocket_notifications` (verifica JWT da `?token=` o cookie `access_token` PRIMA di `ws_manager.connect()`), dato che `BaseHTTPMiddleware.dispatch()` non viene mai invocato per lo scope `websocket`. Verificato con `TestClient.websocket_connect()`: connessione rifiutata senza token. *(08)*
26. ~ PARZIALE (lug 2026) — Aggiunto `get_current_admin_user` (dependency già esistente ma mai usata in nessun router) ai 4 endpoint più distruttivi: `POST /api/admin/reset-collections` (cancella QUALSIASI collezione, prima chiamabile da qualunque utente loggato), `DELETE /api/prima-nota/cassa/delete-all`, `DELETE /api/prima-nota/banca/delete-all`, `DELETE /api/prima-nota-salari/salari/reset` (cancellano l'intero registro cassa/banca/salari). Verificato con registro Sheets effimero: utente non-admin → 403, admin → 200. Restano senza gate di ruolo altri reset meno critici (dizionari, learning machine cache, riconciliazioni con `dry_run=False`) e le riconciliazioni automatiche citate: da riprendere in un prossimo giro, non urgenti quanto la cancellazione diretta dei registri contabili. *(04, 08)*

### ⚪ Stub / codice morto che finge di funzionare

27. ✔ RISOLTO (lug 2026) — Riverificati tutti gli stub elencati: `ocr_assegni.py`, `cash_register.py`, `accounting_extended.py` (router) risultano già eliminati da un audit router precedente (nessun file, nessuna registrazione). `bank-reconciliation/reconcile|upload` era in `bank_reconciliation.py`/`bank_statement_bulk_import.py`, anch'essi già eliminati. `pagopa.py` (upload ricevute) NON è più uno stub: inserisce davvero in DB e associa il movimento. Restava vivo solo `bank_main.py` (`/api/bank/*`): router legacy MAI chiamato dal frontend (`getBankStatements` in `api.js` senza importer), con `/reconcile` e `/assegni` letteralmente `return {"message": "..."}` senza toccare il DB, e uno schema dati (`user_id`/`amount`/`date`) incompatibile con quello reale di `estratto_conto_movimenti` — eliminato interamente (router + service + repository + model dedicati), verificato con test suite (90/90 passati) e boot end-to-end dell'app. *(02, 04)*
28. ~ PARZIALE (lug 2026) — `force_import` non esiste più in nessun router (probabilmente rimosso insieme ai router morti degli audit precedenti). `BackgroundTasks` dichiarato-ma-mai-usato (0 `add_task()`) verificato in 3 file: `documenti.py::/scarica-da-email` ha in realtà un vero percorso asincrono alternativo via `asyncio.create_task` + polling (`GET /task/{task_id}`) quando `background=true` — il parametro `BackgroundTasks` era puro codice morto, rimosso. `f24/email_f24.py::/scarica-email` e `learning_machine.py::/scan` NON hanno alcun percorso asincrono reale: girano sempre sincroni, il parametro `BackgroundTasks` prometteva un comportamento mai implementato — rimosso il parametro morto (nessun cambio di comportamento). Convertirli a un vero pattern async+polling come `documenti.py` resta un miglioramento futuro (non fatto stanotte: tocca il flusso email F24 in produzione, da testare con calma con credenziali reali).

---

## Come usare questi file

- **Prima di modificare un endpoint**: cerca il suo prefisso qui, leggi la sezione — ti dice subito se è shadowato/morto, quali collezioni tocca davvero, e se il docstring è affidabile.
- **Prima di "consolidare" due router che sembrano fare la stessa cosa**: controlla la sezione Note di entrambi — spesso uno dei due contiene la logica corretta (es. metodo dal fornitore, dedup più robusto) e l'altro è quello da eliminare, ma la scelta va verificata caso per caso confrontando anche i chiamanti reali nel frontend.
- Questi file **descrivono lo stato del codice**, non prescrivono come dovrebbe essere: la specifica normativa unica è `PROMPT_MASTER.md`.
