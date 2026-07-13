# Audit Prestazioni — GestionaleCloud

_Audit canonico Fase E, 13/07/2026. Sola lettura._

## Report finale — ordinato per impatto

### ALTO
1. **`sync_relazionale.py:187-218`** — N+1 fino a 10k `find_one` + `$regex` non
   indicizzato su `movimenti_cassa`. Fix: unico caricamento fatture + match in
   memoria (dizionario per numero/importo) e `bulk_write` per gli update.
2. **Paginazione finta fatture** (`fatture_module/crud.py:379`,
   `invoices/invoices_main.py:110`): carica 3000+3000 doc, dedup+arricchimento in
   Python, poi slice `[skip:skip+limit]`. Fix: skip/limit e ordinamento nel DB,
   dedup via indice/aggregation.
3. **`sync_relazionale.py:286-296`** — N+1 fino a 5k `find_one` su
   `estratto_conto_movimenti`. Fix: pre-caricare i movimenti in dizionario indicizzato.
4. **`prima_nota_module/manutenzione.py:596`** (`to_list(100000)`) e
   **`stats.py:121`** (`to_list(None)`). Fix: `$group`/`count_documents` in
   aggregation invece di materializzare l'intera collection.

### MEDIO
5. **Import pesanti top-level** (girano all'avvio via `router_registry`):
   `reports/report_pdf.py:10-15` e `accounting/contabilita_avanzata.py:27-32`
   (reportlab), `libro_unico_parser.py:15`/`mutui_parser.py:10`/`f24_parser.py:19`
   (pdfplumber), trascinati: `accounting_engine.py:16` (pandas),
   `enhanced_document_parser.py:17`/`document_ai_extractor.py:15` (fitz/PIL). Fix:
   import lazy dentro la funzione che li usa.
6. **Assenza cache** su bilancio (`accounting/bilancio.py`), prima nota stats
   (`stats.py`), controllo mensile (`manutenzione.py`). `SimpleCache`
   (`middleware/performance.py:21-63`) è usato solo in dashboard e lista fornitori.
   Fix: `cache.get/set` TTL 60-300s + invalidazione su scrittura.
7. **`email_document_downloader.py:885-889`** N+1 su `file_hash`. Fix:
   `find({file_hash: {$in: [...]}})` una volta + set in memoria.

### BASSO
8. **`vite.config.js`** senza `manualChunks` (`:62` solo `chunkSizeWarningLimit`):
   React/router/query/UI tutti in `index-*.js` (401 kB, unico vero peso all'avvio).
   Fix: `build.rollupOptions.manualChunks` per separare i vendor.
9. **N+1 minori** in background/scheduler: `fiscale_sentinella.py:194`,
   `verbali_fattura_trigger.py:59`, `verbali_pagamento_finder.py:73`,
   `aruba_notifiche.py:409`. Fix: batch `find_one` con `$in`.

## Note

- **Bundle > 300 kB**: `jspdf.plugin.autotable` 420 kB (lazy, solo export PDF),
  `index-*.js` 401 kB (entry, sempre caricato), `Dashboard` 359 kB (lazy).
- **Lazy loading**: usato in modo estensivo (`main.jsx:27-54`, tutti gli hub). Unica
  pagina non-lazy: `Login.jsx` (corretto).
- **Query senza limite (runtime)**: `stats.py:121` `to_list(None)`, `mutui.py:301`
  `to_list(None)`, `manutenzione.py:596` `100000`, `cassa.py:290,401` `50000`,
  `sync.py:465` `15000`, `crud.py:263-264` `3000`+`3000`, `bonifici/transfers.py:205,279` `10000`.
- **Paginazione vera** (corretta) su: prima nota banca (`banca.py:49`), cassa
  (`cassa.py:52`), mutui (`mutui.py:61`).
- **Non-N+1 (positivo)**: `fatture_module/crud.py:335-374` arricchisce fornitori con
  singola `find({$in: pive})` + lookup in memoria.
