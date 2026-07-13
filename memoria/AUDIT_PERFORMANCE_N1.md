# Audit prestazioni §11 — query illimitate & N+1
> Generato per la FASE P1 §11. NON modificare a blocco: ogni query va valutata
> singolarmente (alcune aggregazioni FINANZIARIE necessitano di TUTTI i record —
> es. calcolo pregresso IVA — e un cap le troncherebbe). Questo file elenca i
> punti da rivedere con la correzione consigliata.

## §11.3 Query con tetto alto/illimitato (23)
| File | Riga | Codice | Azione consigliata |
|---|---|---|---|
| `app/routers/bank/assegni.py` | 365 | `fatture_cursor = await db["invoices"].find({}, {"_id": 0}).to_list(50000)` | VERIFICARE: aggregazione potenzialmente completa → usare $group/aggregation server-side, NON troncare |
| `app/routers/bank/assegni.py` | 2101 | `}, {"_id": 0}).to_list(50000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/bank/bank_statement_import.py` | 997 | `}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/bonifici_module/jobs.py` | 144 | `existing_docs = await db.bonifici_transfers.find({}, {'_id': 0, 'dedup_key': 1}).to_list(50000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/bonifici_module/riconciliazione.py` | 49 | `movimenti = await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(50000)` | VERIFICARE: aggregazione potenzialmente completa → usare $group/aggregation server-side, NON troncare |
| `app/routers/bonifici_module/riconciliazione.py` | 135 | `movimenti = await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(50000)` | VERIFICARE: aggregazione potenzialmente completa → usare $group/aggregation server-side, NON troncare |
| `app/routers/chat_router.py` | 129 | `tutti = await db[Collections.F24_MODELS].find({}, {"_id": 0}).to_list(50000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/invoices/corrispettivi_helpers.py` | 400 | `corrispettivi = await db["corrispettivi"].find(query, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/invoices/corrispettivi_helpers.py` | 453 | `dupes = await db["corrispettivi"].aggregate(pipeline).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/prima_nota_module/cassa.py` | 320 | `).to_list(50000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/prima_nota_module/cassa.py` | 431 | `).to_list(50000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/prima_nota_module/manutenzione.py` | 596 | `).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/routers/prima_nota_module/manutenzione.py` | 704 | `movimenti = await db[collection_name].find(query, {"_id": 0}).to_list(50000)` | VERIFICARE: aggregazione potenzialmente completa → usare $group/aggregation server-side, NON troncare |
| `app/routers/verbali_noleggio.py` | 297 | `}, {"_id": 0}).to_list(50000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_documents_classified.py` | 42 | `docs = await db[LEGACY].find({}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_employee_contracts_a_contratti.py` | 34 | `docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_employees_a_dipendenti.py` | 22 | `legacy_docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_f24_unificato.py` | 34 | `docs = await db[coll].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_fatture_passive_a_invoices.py` | 24 | `docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_invoices_emesse_a_fatture.py` | 31 | `docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_payslips_a_cedolini.py` | 28 | `docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/scripts/migra_staff_a_dipendenti.py` | 24 | `docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |
| `app/services/email_document_downloader.py` | 791 | `# §11.3: niente to_list(None) illimitato. Lookup in memoria (pattern §11.1)` | Valutare tetto esplicito + log se raggiunto (come email_message_index §11) |

## §11.1 N+1 — pattern da correggere con $in / aggregation / bulk_write
Aree citate dal prompt: sincronizzazione relazionale, estratto conto, downloader, scheduler.
Correzione tipo: sostituire `for x: await coll.find_one({k: x})` con un'unica
`coll.find({k: {'$in': [...]}})` + lookup in un dict in memoria; per gli update usare `bulk_write`.

## §11.4 Stato job persistente — GIÀ FATTO
`app/routers/batch_reprocessing.py` persiste lo stato job (P0.10: job_state + heartbeat
`_job_stallato`, STALE_DOPO_MIN=30) con job_id/tipo/stato/progresso/totale/errori/timestamp.

## Fix applicati in questa fase
- `email_document_downloader.py`: `to_list(None)` → tetto esplicito 500000 + log se raggiunto
  (lookup in memoria per la dedup message-id, pattern §11.1 raccomandato).
