# Audit Database — GestionaleCloud

_Audit canonico Fase F, 13/07/2026. Sola lettura._

Fonti: `app/db_collections.py` (registro `COLL_*`) e `app/database.py` (classe
`Collections` legacy + `_create_indexes`). Metodo: incrocio nomi registro con usi
reali (`db["nome"]`, `Collections.NOME`, costante `COLL_*`).

## Bug trovato e già corretto
- **`Collections.SCADENZARIO_FORNITORI` non esiste** ma era usato in
  `websocket_realtime.py:83` → `AttributeError` inghiottito dal try/except esterno
  → **i KPI live della dashboard restituivano sempre `{}`**. Corretto usando la
  stringa canonica `"scadenziario_fornitori"` (commit di questa fase).

## (b) Gruppi duplicati → canonica

1. **Magazzino inventario** — canonica `warehouse_inventory`. Legacy: `warehouse_stocks`
   (marcata DEPRECATA in `db_collections.py:166` ma ancora 3 usi:
   `warehouse_helpers.py:327`, `cascade_operations.py:245`, `suppliers_module/base.py:604`),
   `warehouse_products` (1 uso `reports/simple_exports.py:95`), `magazzino`/`magazzino_articoli` (morte).
2. **Movimenti magazzino** — canonica `warehouse_movements`. Morte: `magazzino_movimenti`, `movimenti_magazzino`.
3. **Estratto conto** — canonica `estratto_conto_movimenti`. `estratto_conto` già in
   archiviazione. Ambigua: `estratti_conto` (plurale) usata solo in
   `bank/riconciliazione_f24_banca.py:83,342` → unificare.
4. **Prima Nota** — canoniche `prima_nota_cassa` + `prima_nota_banca`. `prima_nota`
   unificata: 5 usi + indice solo in `scripts/create_indexes.py` → stato ibrido da chiarire.
5. **F24** — canonica `f24_unificato`. **Incoerenza**: collection fisica letterale
   `f24_commercialista` scritta/letta in `post_download_pipeline.py:101-103`,
   `llm_document_parser.py:316-338`, `scadenze.py:646`, `f24_email_settings.py:258-259`,
   mentre la costante `COLL_F24_COMMERCIALISTA` → `f24_unificato`: **due collection
   fisiche per lo stesso scopo**. Da unificare.
6. **Fatture passive** — canonica `invoices`. `fatture_passive` ancora 4 usi
   (`erp_bridge.py:118,146`, `fatture_module/crud.py:264`, `anagrafica_fornitori_xml.py:40`).
7. **Fatture emesse** — canonica `fatture_emesse` (indicizzata). `invoices_emesse`
   legacy ma 9 usi vivi → convergere.
8. **Dipendenti** — canonica `dipendenti`. Stringa letterale `employees` usata 2x
   (`trattenute_verbali_service.py:228`, `paypal_statements.py:604`) → viola la
   regola "MAI employees" (`db_collections.py:45`).

## (c) Candidate all'archiviazione (35 DEFINITA-MA-MAI-USATA)
Già coperte: `estratto_conto`, `prima_nota_provvisori`, `movimenti_bancari`
(`archivia_collection_morte.py`), `schede_tecniche*` (`archivia_collection_haccp.py`).

Nuove sicure (nessun riferimento nel codice):
- Magazzino/prodotti legacy: `magazzino`, `magazzino_articoli`, `magazzino_movimenti`,
  `magazzino_differenze`, `product_catalog`, `product_mappings`, `warehouse_config`.
- Presenze/HR mai usate: `attendance_assenze`, `attendance_timbrature`,
  `attendance_presenze_calendario` (le prime due hanno solo indici orfani in
  `database.py:146-147`), `giustificativi_dipendente`, `giustificativi_saldi_finali`,
  `riporti_ferie`, `shifts`, `staff`.
- Contabilità/fatture: `chart_of_accounts`, `aliquote_iva`, `saldi_giornalieri`,
  `corrispettivi_manuali`, `invoice_metadata_templates`, `failed_invoices`,
  `incasso_reale`, `pagamenti_anticipati`, `abbuoni_arrotondamenti`.
- Fornitori/comparatore/noleggio: `supplier_orders`, `comparatore_cart`,
  `comparatore_supplier_exclusions`, `fornitori_dizionario`, `costi_noleggio`,
  `fatture_noleggio_xml`, `estratto_conto_fornitori`, `documenti_commercialista`,
  `portal_documents`, `carts`, `aruba_elaborazioni`, `ocr_assegni`.

Da consolidare PRIMA (residui vivi, non archiviare a freddo): `warehouse_stocks`,
`warehouse_products`, `fatture_passive`→`invoices`, `f24_commercialista`→`f24_unificato`,
`invoices_emesse`→`fatture_emesse`, `estratti_conto`→`estratto_conto_movimenti`,
`employees`→`dipendenti`, `movimenti_f24_banca`.

## (d) Indici mancanti consigliati
Collezioni interrogate senza indici (`_create_indexes`, `database.py:61-258`):

| Collection | Uso | Consigliato |
|---|---|---|
| `scadenziario_fornitori` | 16 | `data_scadenza`, `fornitore_piva`, `pagato` |
| `cespiti` | 20 | `anno`, `categoria`/`stato` |
| `quietanze_f24` | 14 | `periodo`/`anno`, `f24_id`(sparse), `status` |
| `contratti_dipendenti` | 13 | `dipendente_id`, `attivo` |
| `documenti_non_associati` | 14 | `created_at`, `stato`/`tipo` |
| `fatture_passive` (se mantenuta) | 4 | `data` (sort in crud.py:264), `source` |
| `f24_commercialista` (fisica) | 7 | `status`, `pdf_hash` unique |

Ben indicizzate (nessuna azione): `invoices`, `estratto_conto_movimenti`,
`prima_nota_cassa`/`banca`, `corrispettivi`, `f24_unificato`, `alerts`,
`prima_nota_salari`, `documents_inbox`, `verbali_noleggio`, `acconti_dipendenti`,
`paypal_transactions`.

## Note trasversali
- Doppia governance dei nomi (`db_collections.py` `COLL_*` + classe `Collections` in
  `database.py`) genera disallineamenti (F24, magazzino, lo `SCADENZARIO_FORNITORI`
  mancante). Consigliata un'unica fonte di verità.
- `LIBRETTI_SANITARI` è in `database.py:342` ma non nel registro `db_collections.py`.
