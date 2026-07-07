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
2. `POST /api/pagamenti/assegno-multi-fatture` e `/fattura-multi-metodo` → **TypeError certo** (`registra_pagamento(Body(**dict))`). *(04)*
3. `POST/GET /api/cash/corrispettivi` → **AttributeError certo** (`CashService(repo, None)`). *(04)*
4. `POST /api/riconciliazione-auto/correggi-metodi-pagamento` → **KeyError** (`_id` letto dopo proiezione che lo esclude): la bonifica non fa nulla. *(04)*
5. `sposta-cassa`/`sposta-banca` (dati_provvisori) salvano importi **negativi** con `tipo:"uscita"`: nelle aggregate un'uscita negativa **aumenta** il saldo cassa/banca invece di diminuirlo. *(01)*
6. **F24**: `COLL_F24_COMMERCIALISTA` in `db_collections.py` vale `"f24_unificato"`, ma le costanti omonime locali in `f24_riconciliazione.py`/`email_f24.py` valgono `"f24_commercialista"` → sotto lo stesso prefisso, moduli diversi scrivono/leggono **due archivi diversi** senza saperlo. *(05)*
7. `PUT /api/sync/update-fattura-everywhere` **azzera a null** importo/data/pagato dei movimenti di prima nota per i campi non inviati nel body. *(08)*
8. `POST /verbali-riconciliazione/riconcilia/{n}` — `ObjectId(driver_id)` su un id in formato UUID → 500 non gestito. *(07)*
9. **Ammortamenti cespiti** registrati come uscita di cassa reale in `prima_nota_cassa` (`cespiti/registra/{anno}`) — un costo non monetario altera il saldo cassa. *(02)*
10. **Ricavi gonfiati**: TD01/TD24/TD26 (fatture emesse) classificate come "ricavi" dentro `chiusura_esercizio`, `indici_bilancio`, `controllo_gestione` — pur essendo la collezione `invoices` dedicata alle sole fatture **ricevute**. *(02)*

### 🟠 Shadowing / route irraggiungibili (il codice "vince" non è quello che sembra)

11. **`/api/fatture` upload**: `fatture_overlay` è montato PRIMA di `fatture_upload` → `POST /api/fatture/upload-xml[-bulk]` gira SEMPRE sull'overlay, che **rifiuta i P7M** e non emette l'evento `FATTURA_CREATED` (niente scadenzario/alert automatici). La pipeline "cuore" (`process_xml_bytes`) su questo canale non gira mai. *(03)*
12. **`/api/invoices`**: `invoices_main_overlay` vince su `invoices_main`; dentro `invoices_main` un decoratore duplicato fa sì che `GET /{invoice_id}` risponda con la lista `bank-pending` (bug indipendente dallo shadowing, mascherato dall'overlay). `invoices_export.py` è un intero modulo-stub mai raggiunto. *(03)*
13. **Verbali noleggio**: `/stats`, `/pdf/{n}`, `/dettaglio/{n}` definiti in due router sotto lo stesso prefisso — vince sempre `verbali_noleggio.py`, la versione più ricca in `verbali_noleggio_api.py` è morta. Anche `GET /api/dipendenti/contratti` definito due volte. *(07)*
14. `GET /api/f24/quietanze` shadowato da `GET /api/f24/{f24_id}` (registrato prima) → risponde sempre "F24 non trovato". *(05)*
15. `GET /api/iva/daily/{date}`: il path param si chiama `{date}` ma il parametro Python è `date_param` → FastAPI lo tratta come query obbligatoria, il segmento path è ignorato. *(02)*
16. `POST /api/verbali-noleggio/unifica-verbali`: endpoint tronco/morto, il corpo del loop non fa nulla, ritorna sempre `null` nonostante il docstring. *(07)*

### 🟡 Architetture parallele non comunicanti (stessa funzione, N implementazioni)

17. **Fatture**: 3 pipeline di import (`process_xml_bytes` "cuore", overlay upsert, `InvoiceService.process_xml_invoice` in invoices_main) + Excel import con `invoice_key` in formato diverso → dedup incrociato impossibile. *(03)*
18. **Riconciliazione**: 4 gruppi paralleli — `/api/riconciliazione`, `/api/riconciliazione-auto`, `/api/riconciliazione-intelligente` (25 route), `/api/operazioni-da-confermare` — più 3 importer estratto conto con schemi/dedup diversi sulla stessa collezione, e 3 circuiti banca↔PayPal con flag diversi. *(04)*
19. **Contabilità**: 3 motori paralleli (`prima_nota_righe` Odoo/CEE, `movimenti_contabili`+saldi piano conti GG.SS.CC, `scritture_contabili` accounting-engine) che non si parlano; 2 sistemi cespiti, 2 chiusure esercizio, 2 sistemi budget, 2 sistemi regole di categorizzazione sulle stesse collezioni con schemi diversi. *(02)*
20. **Fatture ricevute**: `paga-manuale` (fatture-ricevute) duplica `PUT /{id}/paga` (fatture); `cambia-metodo-pagamento` duplica `PUT /{id}/metodo-pagamento`; `archivio` duplica la lista di `/api/invoices`. *(03)*
21. **Email/documenti**: 5 moduli scaricano/classificano la stessa posta verso collezioni diverse (email_download, documenti, email_scanner, email_mongodb, learning_machine); import fatture da email bypassa ancora la pipeline unificata in 2 punti (`email_download/processa-fatture-email`, `ai_parser/parse-fattura`). *(06)*
22. **F24** frammentato su 5 collezioni/moduli; **dipendenti**: doppia anagrafica `employees` (condivisa con AppDipendenti) vs `dipendenti` (locale) — moduli diversi cercano la persona in collezioni diverse. *(05, 07)*
23. `fornitori/sync-suppliers` (in `/api/fatture`) duplica quasi esattamente `suppliers/sincronizza-da-fatture`; due Excel-import fornitori quasi identici. Tutti i punti di creazione automatica fornitore usano **default "bonifico"**, violando la regola "nuovo fornitore → nessun metodo finché non configurato". *(03)*

### 🔵 Sicurezza / esposizione

24. **Webhook WhatsApp e ponte ERP non in whitelist auth** → Meta e l'app Tracciabilità ricevono 401 (probabilmente le integrazioni esterne sono di fatto rotte in produzione). `/api/f24-public/*` è totalmente pubblico ed espone dati fiscali. Le pagine legali (`/privacy`, `/terms`) sono dietro JWT (dovrebbero essere pubbliche). *(08)*
25. **WebSocket**: il controllo token è scritto in un middleware HTTP che non intercetta lo scope `websocket` → controllo di fatto non applicato (codice morto silenzioso). *(08)*
26. Diversi endpoint distruttivi (delete-all, riconciliazioni automatiche con `dry_run=False` di default) senza alcun controllo di ruolo. *(04, 08)*

### ⚪ Stub / codice morto che finge di funzionare

27. OCR assegni (`estrai-dati`, `leggi-carnet`), `bank/reconcile`, `bank-reconciliation/reconcile|upload`, `cash-register/stats-pos-comparison`, upload ricevute PagoPA, `accounting_extended` (balance-sheet/income-statement/tax-simulation) — tutti rispondono "successo" senza fare il lavoro dichiarato. *(02, 04)*
28. Numerosi endpoint AI/automazione con `BackgroundTasks` dichiarato ma esecuzione sincrona (nessun reale vantaggio asincrono), e diversi con `force_import`/parametri accettati e mai letti.

---

## Come usare questi file

- **Prima di modificare un endpoint**: cerca il suo prefisso qui, leggi la sezione — ti dice subito se è shadowato/morto, quali collezioni tocca davvero, e se il docstring è affidabile.
- **Prima di "consolidare" due router che sembrano fare la stessa cosa**: controlla la sezione Note di entrambi — spesso uno dei due contiene la logica corretta (es. metodo dal fornitore, dedup più robusto) e l'altro è quello da eliminare, ma la scelta va verificata caso per caso confrontando anche i chiamanti reali nel frontend.
- Questi file **descrivono lo stato del codice**, non prescrivono come dovrebbe essere: per la logica di business corretta vedi `memoria/LOGICA_OPERATIVA.md`.
