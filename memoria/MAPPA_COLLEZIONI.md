# MAPPA COLLEZIONI — MongoDB `Gestionale`

> Rigenerata 13/07/2026. Fonte: registro canonico `app/db_collections.py`
> (158 costanti `COLL_*`) + conteggio usi reali nel codice.
> Colonna Usi = occorrenze `db["nome"]`/`get_collection` + costante `COLL_*`.
>
> **Aggiornamento manuale 14/07/2026** (sessione Dipendenti + Fatture Estere,
> vedi `AUDIT_DEFINITIVO_SESSIONE_20260714.md`): `contratti_dipendenti` ed
> `employee_contracts` rimosse dal codice (righe sotto marcate); nuova
> `fatture_estere_verifiche` aggiunta. `libretti_sanitari` (mai registrata
> come costante `COLL_*`, solo stringa letterale) è stata rimossa dal codice
> nella stessa sessione — non compariva in questa mappa nemmeno prima
> perché generata solo dalle costanti di `db_collections.py`.

Totale collezioni distinte nel registro: **158** (snapshot 13/07; non
rigenerato oggi — i 2 aggiornamenti sopra sono manuali, mirati).

| Collezione | Usi | Costanti | Nota |
|---|---:|---|---|
| `invoices` | 256 | COLL_INVOICES | 3856 docs - Collezione UNICA per fatture passive |
| `f24_unificato` | 148 | COLL_F24, COLL_F24_UNIFICATO | 83 docs - Collezione UNICA per F24 |
| `documents_inbox` | 123 | COLL_DOCUMENTS_INBOX | 803 docs |
| `verbali_noleggio` | 116 | COLL_VERBALI_NOLEGGIO | 52 docs |
| `estratto_conto_movimenti` | 113 | COLL_ESTRATTO_CONTO | 4261 docs - Collezione UNICA |
| `corrispettivi` | 107 | COLL_CORRISPETTIVI | 1051 docs |
| `prima_nota_cassa` | 82 | COLL_PRIMA_NOTA_CASSA | 1428 docs |
| `dipendenti` | 81 | COLL_EMPLOYEES, COLL_DIPENDENTI | Regola assoluta: MAI "employees". Era "employees", rinominato. |
| `prima_nota_banca` | 78 | COLL_PRIMA_NOTA_BANCA | 1138 docs |
| `fornitori` | 67 | COLL_SUPPLIERS, COLL_FORNITORI | FIX: ora punta a "fornitori" (canonica). "suppliers" era alias inglese |
| `cedolini` | 58 | COLL_CEDOLINI | 916 docs - Collezione principale |
| `prima_nota_salari` | 51 | COLL_PRIMA_NOTA_SALARI | 696 docs |
| `paypal_transactions` | 39 | COLL_PAYPAL_TRANSACTIONS | =========================================== |
| `alerts` | 30 | COLL_ALERTS |  |
| `warehouse_inventory` | 25 | COLL_WAREHOUSE, COLL_WAREHOUSE_INVENTORY | 5372 docs - Collezione UNICA |
| `assegni` | 22 | COLL_ASSEGNI | 210 docs |
| `cespiti` | 22 | COLL_CESPITI | Chiusure e Aperture Esercizio |
| `acconti_dipendenti` | 18 | COLL_ACCONTI_DIPENDENTI | TFR |
| `scadenziario_fornitori` | 18 | COLL_SCADENZIARIO_FORNITORI | 903 docs |
| `fornitori_keywords` | 17 | COLL_FORNITORI_KEYWORDS | 244 docs - Learning Machine keywords |
| `f24_riconciliazione_alerts` | 16 | COLL_F24_ALERTS | 50 docs |
| `quietanze_f24` | 16 | COLL_QUIETANZE_F24 | 303 docs |
| `documenti_non_associati` | 15 | COLL_DOCUMENTI_NON_ASSOCIATI | 285 docs |
| `contratti_dipendenti` | 0 | — | RIMOSSA dal codice il 14/07/2026 (HR spostato su AppDipendenti esterna). Dati storici non purgati su MongoDB, costante COLL_* rimossa da db_collections.py |
| `documenti_email` | 13 | COLL_DOCUMENTI_EMAIL | 218 docs |
| `fatture_email_attachments` | 13 | COLL_FATTURE_EMAIL | 158 docs |
| `movimenti_contabili` | 13 | COLL_MOVIMENTI_CONTABILI |  |
| `piano_conti` | 13 | COLL_PIANO_CONTI | 259 docs |
| `veicoli_noleggio` | 13 | COLL_VEICOLI_NOLEGGIO |  |
| `documents_classified` | 12 | COLL_DOCUMENTS_CLASSIFIED |  |
| `verbali_noleggio_completi` | 12 | COLL_VERBALI_NOLEGGIO_COMPLETI |  |
| `settings` | 11 | COLL_SETTINGS |  |
| `tfr_accantonamenti` | 11 | COLL_TFR_ACCANTONAMENTI |  |
| `acquisti_prodotti` | 10 | COLL_ACQUISTI_PRODOTTI | 15065 docs |
| `invoices_emesse` | 10 | COLL_INVOICES_EMESSE | Alias legacy |
| `partite_aperte` | 10 | COLL_PARTITE_APERTE | Riconciliazione Match (N:M tra movimenti e partite) |
| `regole_categorizzazione_descrizioni` | 10 | COLL_REGOLE_CATEGORIZZAZIONE_DESC |  |
| `regole_categorizzazione_fornitori` | 10 | COLL_REGOLE_CATEGORIZZAZIONE_FORN |  |
| `scadenzario` | 10 | COLL_SCADENZARIO |  |
| `archivio_bonifici` | 9 | COLL_ARCHIVIO_BONIFICI |  |
| `bonifici_transfers` | 9 | COLL_BONIFICI_TRANSFERS | 97 docs |
| `calendario_fiscale` | 9 | COLL_CALENDARIO_FISCALE |  |
| `extracted_documents` | 9 | COLL_EXTRACTED_DOCUMENTS |  |
| `fatture_emesse` | 9 | COLL_FATTURE_EMESSE | Da implementare |
| `riepilogo_cedolini` | 9 | COLL_RIEPILOGO_CEDOLINI | 190 docs |
| `centri_costo` | 8 | COLL_CENTRI_COSTO |  |
| `api_clients` | 7 | COLL_API_CLIENTS |  |
| `cedolini_email_attachments` | 7 | COLL_CEDOLINI_EMAIL | 224 docs |
| `commercialista_log` | 7 | COLL_COMMERCIALISTA_LOG | =========================================== |
| `presenze` | 7 | COLL_PRESENZE |  |
| `prima_nota_righe` | 7 | COLL_PRIMA_NOTA_RIGHE | Assegni |
| `agevolazioni_fiscali` | 6 | COLL_AGEVOLAZIONI_FISCALI | Riconciliazioni |
| `audit_log` | 6 | COLL_AUDIT_LOG | Alert Definitions (catalogo codici) |
| `chiusure_esercizio` | 6 | COLL_CHIUSURE_ESERCIZIO |  |
| `f24_email_attachments` | 6 | COLL_F24_EMAIL |  |
| `notifiche_scadenze` | 6 | COLL_NOTIFICHE_SCADENZE |  |
| `prima_nota` | 6 | COLL_PRIMA_NOTA | Unificata (se usata) |
| `regole_categorie` | 6 | COLL_REGOLE_CATEGORIE |  |
| `supplier_payment_methods` | 6 | COLL_SUPPLIER_PAYMENT_METHODS |  |
| `warehouse_movements` | 6 | COLL_WAREHOUSE_MOVEMENTS | 3935 docs |
| `budget` | 5 | COLL_BUDGET |  |
| `email_documents` | 5 | COLL_EMAIL_DOCUMENTS |  |
| `paypal_statements` | 5 | COLL_PAYPAL_STATEMENTS |  |
| `tfr_liquidazioni` | 5 | COLL_TFR_LIQUIDAZIONI | Presenze e Giustificativi |
| `adr_definizione_agevolata` | 4 | COLL_ADR |  |
| `commercialista_config` | 4 | COLL_COMMERCIALISTA_CONFIG |  |
| `costi_previsionali` | 4 | COLL_COSTI_PREVISIONALI |  |
| `dettaglio_righe_fatture` | 4 | COLL_DETTAGLIO_RIGHE_FATTURE | 11076 docs |
| `dizionario_prodotti` | 4 | COLL_DIZIONARIO_PRODOTTI | 112 docs |
| `estratto_conto_nexi` | 4 | COLL_ESTRATTO_CONTO_NEXI | 52 docs |
| `export_log` | 4 | COLL_EXPORT_LOG |  |
| `price_history` | 4 | COLL_PRICE_HISTORY | 860 docs |
| `riconciliazioni` | 4 | COLL_RICONCILIAZIONI |  |
| `riconciliazioni_match` | 4 | COLL_RICONCILIAZIONI_MATCH | Audit Log unificato |
| `warehouse_stocks` | 4 | COLL_WAREHOUSE_STOCKS | 1484 docs - DEPRECATA (dati errati) |
| `acconti_stipendi` | 3 | COLL_ACCONTI_STIPENDI |  |
| `alert_definitions` | 3 | COLL_ALERT_DEFINITIONS | =========================================== |
| `aperture_esercizio` | 3 | COLL_APERTURE_ESERCIZIO |  |
| `bonifici_email_attachments` | 3 | COLL_BONIFICI_EMAIL | Corrispettivi |
| `costi_finanziari` | 3 | COLL_COSTI_FINANZIARI |  |
| `delibere_fonsi` | 3 | COLL_DELIBERE_FONSI |  |
| `opening_balances` | 3 | COLL_OPENING_BALANCES |  |
| `planning_events` | 3 | COLL_PLANNING_EVENTS |  |
| `settings_assets` | 3 | COLL_SETTINGS_ASSETS |  |
| `turni_dipendenti` | 3 | COLL_TURNI_DIPENDENTI |  |
| `utile_obiettivo` | 3 | COLL_UTILE_OBIETTIVO |  |
| `accounting_entries` | 2 | COLL_ACCOUNTING_ENTRIES |  |
| `config` | 2 | COLL_CONFIG |  |
| `configurazioni` | 2 | COLL_CONFIGURAZIONI |  |
| `email_accounts` | 2 | COLL_EMAIL_ACCOUNTS |  |
| `employee_contracts` | 0 | — | RIMOSSA dal codice il 14/07/2026 (era già alias legacy morto). Costante COLL_* rimossa da db_collections.py |
| `fatture_estere_verifiche` | 3 | — (stringa letterale) | NUOVA il 14/07/2026 — storico conferme/correzioni lettura AI fatture estere, fonte del rating per fornitore. Vedi `app/routers/fatture_estera_verifica.py` |
| `estratto_conto_bnl` | 2 | COLL_ESTRATTO_CONTO_BNL |  |
| `giustificativi` | 2 | COLL_GIUSTIFICATIVI | Permessi/ferie |
| `learning_feedback` | 2 | COLL_LEARNING_FEEDBACK | Feedback utente |
| `libro_unico_presenze` | 2 | COLL_LIBRO_UNICO_PRESENZE |  |
| `magazzino_doppia_verita` | 2 | COLL_MAGAZZINO_DOPPIA_VERITA |  |
| `notifications` | 2 | COLL_NOTIFICATIONS |  |
| `operazioni_da_confermare` | 2 | COLL_OPERAZIONI_DA_CONFERMARE | 277 docs |
| `richieste_assenza` | 2 | COLL_RICHIESTE_ASSENZA |  |
| `ritenute_acconto` | 2 | COLL_RITENUTE_ACCONTO | =========================================== |
| `scheduled_exports` | 2 | COLL_SCHEDULED_EXPORTS | =========================================== |
| `supplier_payment_history` | 2 | COLL_SUPPLIER_PAYMENT_HISTORY |  |
| `warehouse_products` | 2 | COLL_WAREHOUSE_PRODUCTS |  |
| `abbuoni_arrotondamenti` | 1 | COLL_ABBUONI |  |
| `aliquote_iva` | 1 | COLL_ALIQUOTE_IVA | 55 docs |
| `allegati_fatture` | 1 | COLL_ALLEGATI_FATTURE | Fatture Emesse (fatture attive) |
| `aruba_elaborazioni` | 1 | COLL_ARUBA_ELABORAZIONI | 100 docs |
| `assegni_learning` | 1 | COLL_ASSEGNI_LEARNING | 50 docs |
| `attendance_assenze` | 1 | COLL_ATTENDANCE_ASSENZE |  |
| `attendance_presenze_calendario` | 1 | COLL_ATTENDANCE_CALENDARIO | 114 docs |
| `attendance_timbrature` | 1 | COLL_ATTENDANCE_TIMBRATURE |  |
| `bank_statements` | 1 | COLL_BANK_STATEMENTS | Alias inglese |
| `bonifici_stipendi` | 1 | COLL_BONIFICI_STIPENDI | 736 docs |
| `carts` | 1 | COLL_CARTS |  |
| `chart_of_accounts` | 1 | COLL_CHART_OF_ACCOUNTS | Alias inglese |
| `clients` | 1 | COLL_CLIENTS | Da implementare |
| `comparatore_cart` | 1 | COLL_COMPARATORE_CART |  |
| `comparatore_supplier_exclusions` | 1 | COLL_COMPARATORE_EXCLUSIONS | =========================================== |
| `corrispettivi_manuali` | 1 | COLL_CORRISPETTIVI_MANUALI | Piano dei Conti e Contabilità |
| `costi_noleggio` | 1 | COLL_COSTI_NOLEGGIO | =========================================== |
| `dimissioni` | 1 | COLL_DIMISSIONI | =========================================== |
| `documenti_classificati` | 1 | COLL_DOCUMENTI_CLASSIFICATI | 1967 docs |
| `documenti_commercialista` | 1 | COLL_DOCUMENTI_COMMERCIALISTA |  |
| `documents` | 1 | COLL_DOCUMENTS |  |
| `estratto_conto` | 1 | COLL_ESTRATTO_CONTO_LEGACY | 4244 docs - Legacy backup |
| `estratto_conto_fornitori` | 1 | COLL_ESTRATTO_CONTO_FORNITORI |  |
| `f24_models` | 1 | COLL_F24_MODELS | 68 docs - Legacy, da migrare |
| `failed_invoices` | 1 | COLL_FAILED_INVOICES |  |
| `fatture_noleggio_xml` | 1 | COLL_FATTURE_NOLEGGIO_XML | 111 docs |
| `fornitori_dizionario` | 1 | COLL_FORNITORI_DIZIONARIO | Clienti |
| `giustificativi_dipendente` | 1 | COLL_GIUSTIFICATIVI_DIPENDENTE |  |
| `giustificativi_saldi_finali` | 1 | COLL_GIUSTIFICATIVI_SALDI_FINALI | NUOVO: Saldi finali per foglio progressivo |
| `incasso_reale` | 1 | COLL_INCASSO_REALE |  |
| `indice_documenti` | 1 | COLL_INDICE_DOCUMENTI | DEPRECATA - dati migrati in invoices. Tenere per email_reconciliation  |
| `invoice_metadata_templates` | 1 | COLL_INVOICES_METADATA |  |
| `learning_rules` | 1 | COLL_LEARNING_RULES | Regole apprese |
| `magazzino` | 1 | COLL_MAGAZZINO |  |
| `magazzino_articoli` | 1 | COLL_MAGAZZINO_ARTICOLI | Movimenti |
| `magazzino_differenze` | 1 | COLL_MAGAZZINO_DIFFERENZE |  |
| `magazzino_movimenti` | 1 | COLL_MAGAZZINO_MOVIMENTI |  |
| `movimenti_magazzino` | 1 | COLL_MOVIMENTI_MAGAZZINO | Acquisti |
| `note_credito` | 1 | COLL_NOTE_CREDITO |  |
| `ocr_assegni` | 1 | COLL_OCR_ASSEGNI | Bonifici |
| `pagamenti_anticipati` | 1 | COLL_PAGAMENTI_ANTICIPATI |  |
| `payslips` | 1 | COLL_PAYSLIPS | 480 docs - Alias inglese (legacy) |
| `portal_documents` | 1 | COLL_PORTAL_DOCUMENTS | Email |
| `presenze_mensili` | 1 | COLL_PRESENZE_MENSILI | 211 docs - Da parser Libro Unico |
| `product_catalog` | 1 | COLL_PRODUCT_CATALOG |  |
| `product_mappings` | 1 | COLL_PRODUCT_MAPPINGS | Prezzi |
| `rimanenze` | 1 | COLL_RIMANENZE | Configurazione |
| `riporti_ferie` | 1 | COLL_RIPORTI_FERIE | Contratti |
| `saldi_giornalieri` | 1 | COLL_SALDI_GIORNALIERI | IVA |
| `scadenze` | 1 | COLL_SCADENZE |  |
| `shifts` | 1 | COLL_SHIFTS | =========================================== |
| `staff` | 1 | COLL_STAFF |  |
| `supplier_orders` | 1 | COLL_SUPPLIER_ORDERS |  |
| `tributi_pagati` | 1 | COLL_TRIBUTI_PAGATI |  |
| `warehouse_config` | 1 | COLL_WAREHOUSE_CONFIG | =========================================== |
