# Piano di consolidamento collection duplicate

_Audit canonico, 13/07/2026. Scelta utente: **preparare il piano, NON toccare i
dati di produzione.** Questo documento descrive cosa fare; nessuna migrazione è
stata eseguita._

## Principio guida
Ogni consolidamento segue tre passi, sempre **non distruttivi**:
1. **Reindirizzare il codice** alla collection canonica (una sola fonte).
2. **Migrare i dati** dalla collection legacy alla canonica con uno script di
   dry-run + esecuzione, che **copia** (upsert per chiave) senza cancellare.
3. **Archiviare** la legacy con `rename` a `_archiviata_<nome>_<timestamp>`
   (come `archivia_collection_morte.py`), recuperabile.

Nessuno `drop`/`delete_many`. La legacy resta leggibile finché non si conferma
che la canonica è completa.

## Gruppi da consolidare (in ordine di rischio crescente)

### 1. `f24_commercialista` → `f24_unificato`  (PRIORITÀ ALTA)
- **Problema**: parte del codice usa la costante `COLL_F24_COMMERCIALISTA`
  (→ `f24_unificato`), parte usa la stringa letterale `"f24_commercialista"`
  → due collection fisiche per lo stesso scopo, rischio F24 divisi.
- **Punti da reindirizzare** (stringa → costante): `post_download_pipeline.py:101,103`,
  `llm_document_parser.py:316,338`, `scadenze.py:646`, `f24_email_settings.py:258-259`.
- **Migrazione**: upsert dei doc di `f24_commercialista` in `f24_unificato` per
  chiave (hash PDF / periodo+causale+importo). Poi archiviare `f24_commercialista`.
- **Attenzione**: rispettare la SPECIFICA F24 (memoria/SPECIFICA_...): non
  duplicare RC01/DM10, mantenere stati pagamento.

### 2. `estratti_conto` (plurale) → `estratto_conto_movimenti`  (ALTA)
- **Problema**: `bank/riconciliazione_f24_banca.py:83,342` scrive/legge una
  collection al plurale distinta dalla canonica dei movimenti banca.
- **Reindirizzare**: quei due punti su `estratto_conto_movimenti`.
- **Migrazione**: verificare che i doc non siano già presenti (per data+importo+
  descrizione) prima dell'upsert. Poi archiviare `estratti_conto`.

### 3. `invoices_emesse` → `fatture_emesse`  (MEDIA)
- **Problema**: `fatture_emesse` è la registrata/indicizzata; `invoices_emesse`
  è alias legacy ma con 9 usi vivi (`db["invoices_emesse"]`).
- **Reindirizzare**: i 9 usi su `fatture_emesse`.
- **Migrazione**: upsert per numero+anno. Portare gli indici sulla canonica
  (già presenti su `fatture_emesse`: `data_emissione`, `stato`).

### 4. `fatture_passive` → `invoices`  (MEDIA, ma attenzione)
- **Problema**: `invoices` è la "collezione UNICA fatture passive"
  (`db_collections.py:22`), ma `fatture_passive` è ancora usata 4x
  (`erp_bridge.py:118,146`, `fatture_module/crud.py:264`,
  `anagrafica_fornitori_xml.py:40`).
- **Verifica preliminare necessaria**: capire se `fatture_passive` contiene
  davvero fatture "vere" o è un indice ridotto/proiezione. Se sono le stesse
  fatture con schema diverso, allineare lo schema PRIMA di migrare.
- **Reindirizzare**: i 4 usi su `invoices` con il mapping campi corretto.

### 5. `employees` (letterale) → `dipendenti`  (BASSA)
- **Problema**: viola la regola "MAI employees" (`db_collections.py:45`); 2 usi:
  `trattenute_verbali_service.py:228`, `paypal_statements.py:604`.
- **Reindirizzare**: entrambi su `dipendenti`. Verificare che non abbiano già
  scritto doc in `employees` da migrare (probabile collection vuota/quasi).

### 6. `warehouse_stocks` / `warehouse_products` → `warehouse_inventory`  (BASSA)
- **Problema**: `warehouse_stocks` marcata DEPRECATA ma 3 usi residui
  (`warehouse_helpers.py:327`, `cascade_operations.py:245`,
  `suppliers_module/base.py:604`); `warehouse_products` 1 uso
  (`reports/simple_exports.py:95`).
- **Reindirizzare**: tutti su `warehouse_inventory` (il Dizionario Articoli
  contabile canonico rimasto dopo la rimozione HACCP).
- **Migrazione**: probabilmente non serve (dati errati/vuoti per doc), solo
  archiviazione dopo il reindirizzo.

## Collection morte da archiviare (nessun codice le usa)
Sicure, nessun reindirizzo necessario — solo `archivia_collection_*`:
`magazzino`, `magazzino_articoli`, `magazzino_movimenti`, `magazzino_differenze`,
`product_catalog`, `product_mappings`, `warehouse_config`, `attendance_assenze`,
`attendance_timbrature`, `attendance_presenze_calendario`, `giustificativi_dipendente`,
`giustificativi_saldi_finali`, `riporti_ferie`, `shifts`, `staff`, `chart_of_accounts`,
`aliquote_iva`, `saldi_giornalieri`, `corrispettivi_manuali`, `invoice_metadata_templates`,
`failed_invoices`, `incasso_reale`, `pagamenti_anticipati`, `abbuoni_arrotondamenti`,
`supplier_orders`, `comparatore_cart`, `comparatore_supplier_exclusions`,
`fornitori_dizionario`, `costi_noleggio`, `fatture_noleggio_xml`,
`estratto_conto_fornitori`, `documenti_commercialista`, `portal_documents`,
`carts`, `aruba_elaborazioni`, `ocr_assegni`.

> Nota: prima di archiviare gli indici orfani `attendance_assenze`/
> `attendance_timbrature` (creati in `database.py:146-147` su collection morte),
> rimuovere anche la creazione di quegli indici.

## Come procederò quando darai l'ok
Un gruppo alla volta, in ordine di priorità, ciascuno in un commit separato con:
1. reindirizzo codice + test,
2. script di migrazione dry-run (ti mostro i numeri prima di eseguire),
3. archiviazione solo dopo la tua conferma sui numeri.
