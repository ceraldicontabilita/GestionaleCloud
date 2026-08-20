# 03 — Fatture Fornitori, Corrispettivi, Fornitori e moduli collegati

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. La specifica normativa unica è `PROMPT_MASTER.md`; questo file non può contraddirla.

Documentazione operativa degli endpoint dei moduli: invoices (`/api/invoices`), fatture (`/api/fatture`), corrispettivi (`/api/corrispettivi`), fatture-ricevute (`/api/fatture-ricevute`), suppliers (`/api/suppliers` + alias `/api/fornitori`), fornitori-learning, scadenzario-fornitori, schede-tecniche, previsioni-acquisti.

**Ordine di registrazione (router_registry.py) — determina chi vince sui path uguali:**
`invoices_emesse` (prefisso `/api/invoices/emesse`) → `invoices_main_overlay` → `invoices_main` → `invoices_export` (tutti su `/api/invoices`); `fatture_overlay` → `fatture_upload` → `fatture_drive` (tutti su `/api/fatture`). Gli **overlay sono montati PRIMA** dei router legacy: sui path identici (es. `POST /api/fatture/upload-xml`) risponde SEMPRE l'overlay, il legacy è irraggiungibile.

**Convenzioni chiave:** collezione fatture passive canonica = `invoices` (doppio schema campi EN/IT: `total_amount|importo_totale`, `invoice_number|numero_fattura|numero_documento`, `supplier_vat|cedente_piva`, `invoice_date|data_fattura|data_documento`). Fattura pagata = `pagato`/`paid`/`status="paid"`/`stato_pagamento="pagata"`. Collezione fornitori canonica = `fornitori` (P.IVA in `partita_iva`/`piva`/`vat_number`). Il metodo di pagamento viene SOLO da `fornitori.metodo_pagamento`, mai dall'XML.

---

## fatture_upload.py (`/api/fatture`) — il CUORE dell'import XML/P7M

Contiene la pipeline condivisa `process_xml_bytes(db, content, filename, source)`: estrazione P7M (CAdES, anche base64), decodifica multi-encoding, `parse_fattura_xml`, dedup su `invoice_key` (NUMERO_PIVA_DATA), `ensure_supplier_exists` (crea/aggiorna fornitore in `fornitori` + alert `fornitore_senza_metodo_pagamento` se nuovo), insert in `invoices` con campi speculari EN+IT, poi `auto_registra_prima_nota`: metodo fornitore contanti/cassa → insert in `prima_nota_cassa` (pagata); metodo bancario (bonifico/carta/SEPA/RID/PayPal…) → insert in `prima_nota_banca` (pagata) con link best-effort al movimento estratto conto (`estratto_conto_movimenti`, marcato `riconciliato`); nessun metodo/misto/sospesa → resta provvisoria. Chiude con event bus `FATTURA_CREATED` (crea partita scadenziario, alert, audit, righe magazzino). Usata da upload bulk legacy, ingest Google Drive e import documenti (`process_fattura_to_db`, transazionale). **NB:** i commenti nel codice ("banca SOLO se trovato in EC") mentono: la registrazione in banca avviene SEMPRE per metodo bancario, l'EC serve solo per collegare il movimento.

### POST /api/fatture/upload-xml — upload singolo XML/P7M (LEGACY, SHADOWATO)
**Cosa fa**: importa una singola fattura elettronica con riconciliazione automatica EC e prima nota.
**Logica codice**: estrae P7M, parsa, dedup su `invoice_key`; `ensure_supplier_exists`; se il fornitore non ha metodo usa **default "bonifico"** (viola la regola "sospesa"); `riconcilia_con_estratto_conto` (match a punteggio: nome fornitore 50pt, numero fattura 40pt, importo 30pt, soglia 50) può SOVRASCRIVERE il metodo del fornitore; ricerca numeri assegni; insert in `invoices` (con `xml_content`); associazione PDF archiviato; registra prima nota via `prima_nota_module.sync.registra_pagamento_fattura` e marca `pagato=True` anche senza evidenza EC; automazione verbali noleggio.
**Note**: **route morta**: intercettata da `fatture_overlay.upload_fattura_xml_overlay` (registrato prima). Il comportamento effettivo in produzione è quello dell'overlay.

### POST /api/fatture/upload-xml-bulk — upload massivo XML/ZIP (LEGACY, SHADOWATO)
**Cosa fa**: importa N file XML/P7M o ZIP (anche annidati).
**Logica codice**: `extract_xml_from_zip` ricorsivo, poi per ogni file `process_xml_bytes(source="xml_bulk_upload")`; risposta con imported/duplicates/errors.
**Note**: anche questa è shadowata dall'overlay (stesso path); quindi il bulk effettivo NON passa da `process_xml_bytes` ma dall'upsert dell'overlay (vedi anomalie in fondo).

### DELETE /api/fatture/all — elimina tutte le fatture
**Cosa fa**: cancella fisicamente TUTTA la collection `invoices`.
**Logica codice**: richiede `?confirm=CONFERMA_ELIMINAZIONE`, poi `delete_many({})`.
**Note**: nessuna pulizia di prima nota/scadenze collegate.

### POST /api/fatture/cleanup-duplicates — pulizia duplicati (LEGACY, SHADOWATO)
**Cosa fa**: elimina fatture duplicate per (numero, P.IVA, data).
**Logica codice**: aggregazione `$group` su `invoices`, tiene il primo `id` per gruppo, `delete_many` degli altri.
**Note**: shadowato da `fatture_overlay.cleanup-duplicates` (che aggrega su più campi e fonde i dati); non considera l'importo né lo schema IT.

### POST /api/fatture/sync-suppliers — sincronizza fornitori dalle fatture
**Cosa fa**: crea/aggiorna fornitori per ogni `supplier_vat` presente in `invoices`.
**Logica codice**: `$group` per P.IVA su `invoices`; se il fornitore esiste aggiorna campi mancanti + `fatture_count`; se non esiste lo crea con **`metodo_pagamento: "bonifico"` di default** e backfilla `supplier_id` sulle fatture.
**Note**: il default "bonifico" contraddice la regola dell'import (nuovo fornitore → metodo None/sospesa).

### POST /api/fatture/categorize-movements — categorizza prima nota
**Cosa fa**: assegna una `categoria` (utenze, affitto, stipendi, …) a TUTTI i movimenti di `prima_nota_cassa`, `prima_nota_banca` e `estratto_conto_movimenti`.
**Logica codice**: match keyword su descrizione+fornitore con mappa hardcoded (14 categorie); update one-by-one (fino a 10k documenti per collection).
**Note**: sovrascrive categorie già assegnate manualmente; O(n) update singoli.

### GET /api/fatture/{invoice_id} — dettaglio fattura (LEGACY, SHADOWATO)
**Cosa fa**: ritorna il documento `invoices` per `id`.
**Logica codice**: `find_one({"id": invoice_id})`, 404 se assente.
**Note**: shadowato dall'overlay che delega a `fatture_module.crud.get_fattura_dettaglio` (lookup più tollerante + righe + allegati).

### PUT /api/fatture/{invoice_id} — aggiorna fattura (LEGACY, SHADOWATO)
**Cosa fa**: aggiorna campi consentiti (metodo_pagamento, pagato/paid, status, data_pagamento, numeri_assegni, note, centro_costo…).
**Logica codice**: whitelist campi, sincronizza `pagato`↔`paid`, `update_one` su `invoices`.
**Note**: shadowato dall'overlay che delega a `fatture_module.crud.update_fattura` (whitelist più ristretta: pagato, data_pagamento, metodo_pagamento, riconciliato, note).

### PUT /api/fatture/{invoice_id}/classifica — classificazione manuale centro di costo
**Cosa fa**: assegna la fattura a un centro di costo.
**Logica codice**: legge `centri_costo` per `codice`, setta `centro_costo_id/_nome` + `classificazione_manuale=True` su `invoices`.

### PUT /api/fatture/{invoice_id}/metodo-pagamento — cambio metodo su fattura
**Cosa fa**: aggiorna solo `metodo_pagamento` della fattura.
**Logica codice**: `update_one` su `invoices`; 404 se non trovata.

### PUT /api/fatture/{invoice_id}/paga — segna pagata (propagazione)
**Cosa fa**: paga la fattura con il metodo già impostato, propagando su prima nota e fornitore.
**Logica codice**: valida (non già pagata, metodo presente), poi `DataPropagationService.propagate_invoice_payment` (crea movimento cassa/banca, aggiorna stato fattura e saldo fornitore).

### DELETE /api/fatture/{invoice_id} — eliminazione con business rules e cascade
**Cosa fa**: elimina (default: archivia) una fattura con doppia conferma.
**Logica codice**: `CascadeOperations.is_fattura_registrata/get_entita_correlate` + `BusinessRules.can_delete_invoice`; se warning e `force=false` risponde `status:"warning"` senza eliminare; altrimenti `delete_fattura_cascade` (righe, prima nota, scadenze, movimenti magazzino, assegni); `hard_delete=true` per eliminazione fisica.

### GET /api/fatture/{invoice_id}/entita-correlate — anteprima cascade
**Cosa fa**: elenca cosa verrebbe toccato eliminando la fattura.
**Logica codice**: stessi helper CascadeOperations; ritorna stato registrazione, entità correlate, flag `eliminabile`/`richiede_conferma`.

### POST /api/fatture/recalculate-iva — ricalcolo IVA/imponibile massivo
**Cosa fa**: ricalcola IVA e imponibile per tutte le fatture e backfilla `data_ricezione`.
**Logica codice**: se c'è `riepilogo_iva` somma imponibile/imposta; altrimenti stima con scorporo 22% (flag `iva_stimata`); aggiorna solo se scostamento > 0.01.
**Note**: la stima 22% è arbitraria per fatture con aliquote diverse.

---

## fatture_overlay.py (`/api/fatture`) — overlay di compatibilità (VINCE sui path legacy)

Intercetta i 5 endpoint più fragili di fatture_upload. Filosofia diversa dal legacy: mantiene il metodo del fornitore (`metodo_pagamento_predefinito || metodo_pagamento || "da_configurare"`), NON registra prima nota definitiva senza certezza del pagamento (fattura `provvisorio=True` finché non riconciliata con EC), e fa **upsert** dei duplicati invece di rifiutarli (409). Scrive su `invoices` (`COL_FATTURE_RICEVUTE`), `dettaglio_righe_fatture`, `allegati_fatture` usando gli helper di fatture_module (`get_or_create_fornitore`, `salva_dettaglio_righe`, `salva_allegato_pdf`).

### POST /api/fatture/upload-xml — upload singolo (EFFETTIVO)
**Cosa fa**: importa/aggiorna una fattura XML; se pagamento trovato in EC la marca pagata/riconciliata, altrimenti resta provvisoria.
**Logica codice**: `_upsert_invoice_from_xml`: parse → `_find_existing_duplicate` (match multi-campo su P.IVA+data+numero normalizzato+importo, sceglie il candidato con `_invoice_score` più alto) → `get_or_create_fornitore` → metodo dal fornitore → `riconcilia_con_estratto_conto` (riusa quella di fatture_upload) → insert o update con `source="legacy_fatture_overlay"`; su update preserva `metodo_pagamento_modificato_manualmente` e stato pagato pregresso; riscrive righe e allegati; warnings se metodo mancante o pagamento non confermato.
**Note**: **accetta solo `.xml`: i P7M vengono rifiutati con 400** (il legacy li gestiva). NON emette eventi FATTURA_CREATED (niente partita scadenziario automatica da questo canale).

### POST /api/fatture/upload-xml-bulk — upload massivo (EFFETTIVO)
**Cosa fa**: importa/aggiorna N XML o ZIP di XML.
**Logica codice**: estrae XML dagli ZIP (no annidati, salta `__MACOSX`), per ciascuno chiama `_upsert_invoice_from_xml`; contatori importate/duplicate_aggiornate/errori.
**Note**: come sopra: niente P7M, niente `process_xml_bytes`, niente event bus.

### POST /api/fatture/cleanup-duplicates — dedup con merge (EFFETTIVO)
**Cosa fa**: deduplica `invoices` per (numero normalizzato, P.IVA, data, importo) tenendo il documento più ricco.
**Logica codice**: carica fino a 10k doc, raggruppa in memoria, ordina per `_invoice_score` + updated_at, elimina i doppioni e arricchisce il keeper con campi mancanti (imponibile, iva, linee, xml_content…).

### GET /api/fatture/{invoice_id} — dettaglio (EFFETTIVO)
**Cosa fa**: delega a `fatture_module.crud.get_fattura_dettaglio` (fattura + righe + allegati, lookup anche per ObjectId).

### PUT /api/fatture/{invoice_id} — update (EFFETTIVO)
**Cosa fa**: delega a `fatture_module.crud.update_fattura` (whitelist: pagato, data_pagamento, metodo_pagamento, riconciliato, note).

---

## fatture_drive.py (`/api/fatture`) — ingest da Google Drive

Wrapper sottile sul servizio `drive_invoice_ingest`, che internamente usa `process_xml_bytes` (pipeline unica). Un job schedulato ogni 15 minuti chiama lo stesso sync.

### GET /api/fatture/drive/status — stato ingest Drive
**Cosa fa**: ritorna configurazione (cartella, credenziali) e ultimo sync (`sync_running` per polling UI).
**Logica codice**: `drive_invoice_ingest.get_status(db)`.

### POST /api/fatture/drive/sync — avvia sync manuale
**Cosa fa**: lancia in background un ciclo di import dalla cartella Drive e risponde subito.
**Logica codice**: se non configurato ritorna `not_configured`; se già in corso `status:"running"`; altrimenti `start_background_sync` → `status:"started"`.

---

## invoices_emesse.py (`/api/invoices/emesse`) — fatture emesse (attive)

CRUD minimale sulla collection `invoices_emesse`. Richiede utente autenticato.

### GET /api/invoices/emesse — lista fatture emesse
**Cosa fa**: ultime 500 fatture emesse ordinate per `date` desc. `find({}, {_id:0})`.

### GET /api/invoices/emesse/{invoice_id} — dettaglio
**Cosa fa**: `find_one` per `id`; **ritorna `{}` invece di 404** se assente.

### POST /api/invoices/emesse — crea fattura emessa
**Cosa fa**: inserisce il body così com'è aggiungendo `id` uuid, `created_at`, `user_id`. Nessuna validazione di schema.

### DELETE /api/invoices/emesse/{invoice_id} — elimina
**Cosa fa**: `delete_one` per `id`; risponde sempre "deleted" anche se non esisteva.

### POST /api/invoices/emesse/upload-xml — upload XML emessa
**Cosa fa**: salva SOLO i metadati del file (filename, content_type, size) in `invoices_emesse` con `status:"uploaded"`.
**Note**: **non parsa né salva il contenuto XML**: endpoint placeholder.

---

## invoices_main_overlay.py (`/api/invoices`) — overlay lista/dettaglio (VINCE su invoices_main)

Montato prima di invoices_main per correggere le regressioni più visibili senza riscrivere il modulo legacy: dedup a runtime dei doppioni multi-canale, coalescenza campi EN/IT, e un `GET /{invoice_id}` catch-all funzionante.

### GET /api/invoices — lista fatture (EFFETTIVO)
**Cosa fa**: lista `invoices` con filtri anno/supplier_vat/month_year/status, deduplicata.
**Logica codice**: query su tutti i varianti campo (invoice_date|data_documento|data_fattura; supplier_vat|fornitore_partita_iva|cedente_piva; status|stato|stato_pagamento); carica fino a 5000 doc, `_dedupe_invoices` per chiave (numero|piva|data|importo) tenendo il doc con `_invoice_score` più alto, poi paginazione in memoria.

### GET /api/invoices/bank-pending — fatture da pagare in banca (EFFETTIVO)
**Cosa fa**: fatture con `metodo_pagamento` ∈ {banca, bonifico, riba, sdd} non pagate.
**Logica codice**: query con $or su payment_status/stato_pagamento/pagato, esclude `status="deleted"`, dedup, output formattato con coalescenza campi EN/IT.

### GET /api/invoices/by-month/{year}/{month} — fatture del mese (EFFETTIVO)
**Cosa fa**: lista + statistiche mensili (totale, pagato, non pagato, contatori).
**Logica codice**: match su `month_year` (entrambi i formati YYYY-MM e MM-YYYY) o prefisso data su 3 campi; dedup; stats calcolate in Python.
**Note**: corregge il crash del legacy (che leggeva `_id` dopo averlo escluso dalla projection).

### Route delegate al legacy (stesso handler di invoices_main, registrate qui per avere priorità sul catch-all `/{invoice_id}`):
- **GET /api/invoices/anni-disponibili** — anni distinti da `invoice_date` e `data_documento` (aggregazioni $substr) + anno corrente.
- **GET /api/invoices/unpaid** — delega a `InvoiceService.get_unpaid_invoices` (per `user_id`, ordinate per scadenza).
- **GET /api/invoices/overdue** — `InvoiceService.get_overdue_invoices` (scadute e non pagate).
- **GET /api/invoices/search?q=** — `InvoiceService.search_invoices` su supplier_name/invoice_number.
- **GET /api/invoices/stats** — `InvoiceService.get_invoice_stats` (totali, conteggi per stato, distribuzione metodi), filtro `month_year` MM-YYYY.
- **GET /api/invoices/archived-months** — aggregazione `$month/$year` su `invoice_date` con `status:"archived"`. **Nota**: `invoice_date` è stringa → l'aggregazione fallisce e il `try/except` ritorna sempre `[]`.
- **GET /api/invoices/export-excel** — genera XLSX (openpyxl) dalle fatture di `InvoiceService.list_invoices` (colonne Data/Numero/Fornitore/P.IVA/Imponibile/IVA/Totale/Stato/Metodo) come StreamingResponse.

### GET /api/invoices/{invoice_id} — dettaglio (EFFETTIVO, catch-all)
**Cosa fa**: ritorna il documento `invoices` per `id`, con fallback lookup per `_id` ObjectId; 404 se assente.
**Note**: fondamentale: nel legacy questo path era rotto (vedi anomalie invoices_main).

---

## invoices_main.py (`/api/invoices`) — router legacy fatture (in parte shadowato)

Modulo storico basato su service-layer (`InvoiceService` con repository invoices/suppliers/warehouse/accounting/cash). Molti endpoint presuppongono uno schema "service" (`payment_status`, `month_year` MM-YYYY, `user_id`) che le fatture importate da XML NON hanno: su quei documenti i filtri non matchano.

### POST /api/invoices — crea fattura (service)
**Cosa fa**: crea fattura da payload strutturato `InvoiceCreate` via `InvoiceService.create_invoice` (con user_id).

### GET /api/invoices — lista (SHADOWATO dall'overlay)
**Logica codice**: filtro anno su invoice_date|data_documento, aggregazione con sort su `data_effettiva`; niente dedup. Route morta.

### GET /api/invoices/unpaid | /overdue | /search | /stats | /anni-disponibili | /archived-months — (registrati anche qui; raggiungibili solo tramite la delega dell'overlay, che usa le stesse funzioni)

### GET /api/invoices/bank-pending — (SHADOWATO)
**Logica codice**: query per `user_id` + `payment_method`/`payment_status` (schema service). **Bug**: la funzione è decorata ANCHE con `@router.get("/{invoice_id}")` (decoratore orfano alle righe 363-368): dentro questo router `GET /{invoice_id}` risponde con la lista bank-pending, e il vero `get_invoice` (riga 476) non è mai raggiungibile. L'overlay maschera il problema.

### POST /api/invoices/paga-anno/{anno} — paga tutte le fatture di un anno
**Cosa fa**: marca pagate in massa tutte le fatture dell'anno non pagate.
**Logica codice**: regex `^{anno}` su data|invoice_date|data_fattura|data_documento, `update_many` con `pagato/paid=True`, `data_pagamento=now`, `note_pagamento` batch.
**Note**: irreversibile; NON crea movimenti di prima nota (stato pagato senza contropartita contabile).

### GET /api/invoices/{invoice_id} — dettaglio (service) — route irraggiungibile nel router (vedi bug sopra); il dettaglio effettivo è nell'overlay.

### PUT /api/invoices/{invoice_id} — update via `InvoiceService.update_invoice` (solo campi InvoiceUpdate).

### POST /api/invoices/{invoice_id}/payment — registra pagamento (anche parziale)
**Cosa fa**: `InvoiceService.record_payment(amount, payment_method)`; aggiorna payment_status.

### POST /api/invoices/{invoice_id}/archive — archivia (soft) via `InvoiceService.archive_invoice`.

### POST /api/invoices/{invoice_id}/reconcile — collega a transazione bancaria via `InvoiceService.reconcile_with_bank(bank_transaction_id)`.

### GET /api/invoices/by-state/{state} — fatture per stato pagamento
**Cosa fa**: filtra per stato: paid/unpaid/partial/overdue + stati frontend (registered_cash, registered_bank, paid_not_reconciled, pending).
**Logica codice**: mappa stato→query su `payment_status`/`registered_in`/`reconciled`/`due_date`; count + find paginato; output formattato con remaining_amount.
**Note**: basato solo sullo schema service (`payment_status`): le fatture XML (che usano `pagato`/`stato_pagamento`) non vengono conteggiate.

### GET /api/invoices/by-supplier/{supplier_id} — fatture di un fornitore
**Logica codice**: `find({"supplier_id": ...})` paginato, output ridotto.

### GET /api/invoices/by-month/{year}/{month} — (SHADOWATO dall'overlay)
**Note**: **bug nel legacy**: query su `month_year` formato YYYY-MM (il service salva MM-YYYY) e `str(invoice['_id'])` dopo projection `{"_id": 0}` → KeyError. Route morta, l'overlay la sostituisce.

### POST /api/invoices/upload — upload singolo XML (pipeline service)
**Cosa fa**: `InvoiceService.process_xml_invoice(xml, filename, user_id)`; errori catturati e ritornati come `status:"error"`.
**Note**: pipeline di import PARALLELA a `process_xml_bytes` (schema service): terzo canale di import, non allineato alla regola prima nota.

### POST /api/invoices/upload-bulk — upload multiplo/ZIP (pipeline service)
**Cosa fa**: come sopra per N file; estrae XML da ZIP; accetta anche `.p7m` "provandoci" (nessuna estrazione CAdES dedicata).

### POST /api/invoices/import-excel — import fatture da Excel
**Cosa fa**: crea fatture "sintetiche" da righe Excel (Numero, Data, Fornitore, P.IVA, Importo, Stato).
**Logica codice**: mappa header case-insensitive, upsert per `invoice_key` `{piva}_{numero}_{data}` con `$setOnInsert` (non sovrascrive esistenti), `source:"excel_import"`.
**Note**: la invoice_key ha formato diverso da quella dell'import XML (`NUMERO_PIVA_DATA` uppercase): il dedup incrociato Excel↔XML non funziona.

### GET /api/invoices/export-excel — export XLSX (vedi delega overlay).

### POST /api/invoices/metadata/update — update campi arbitrari
**Cosa fa**: setta su `invoices` QUALSIASI campo passato nel body (tranne id).
**Note**: nessuna whitelist → può corrompere campi di sistema; usato dal frontend per metodo pagamento/assegni.

### POST /api/invoices/delete-by-month — elimina fatture del mese
**Logica codice**: `delete_many({user_id, month_year: "YYYY-MM"})`.
**Note**: doppio problema: `month_year` è salvato dal service come MM-YYYY (mismatch formato) e le fatture da XML non hanno `user_id` → in pratica elimina 0 documenti.

### POST /api/invoices/delete-by-year — elimina fatture dell'anno
**Logica codice**: `delete_many({user_id, month_year: regex "-YYYY$"})` (qui il formato MM-YYYY è corretto).
**Note**: sempre limitato a `user_id`: non tocca le fatture importate da XML.

### DELETE /api/invoices/all — elimina tutte le fatture dell'utente
**Logica codice**: `delete_many({user_id})`. Stessa limitazione: le fatture XML senza user_id sopravvivono.

### DELETE /api/invoices/{invoice_id} — soft-delete con business rules
**Cosa fa**: valida con `BusinessRules.can_delete_invoice`; se warning richiede `force=true`; poi setta `entity_status="deleted"`, `status="deleted"`, `deleted_at/by`.
**Note**: a differenza di `DELETE /api/fatture/{id}` NON fa cascade su prima nota/scadenze.

---

## invoices_export.py (`/api/invoices`)

### GET /api/invoices/export-excel — export (STUB, mai raggiunto)
**Cosa fa**: ritorna `{"message": "Excel export not yet implemented"}`.
**Note**: route morta: sia l'overlay sia invoices_main registrano lo stesso path prima di questo router. Modulo di fatto inutile.

---

## corrispettivi.py (`/api/corrispettivi`) — corrispettivi telematici RT

Gestisce la collection `corrispettivi` (incassi giornalieri da registratore telematico). L'ingest XML passa dall'helper condiviso `corrispettivi_helpers.ingest_corrispettivo_parsed` (anti-duplicato + propagazione automatica a `prima_nota_cassa` e `prima_nota_banca` per la quota POS).

### GET /api/corrispettivi — lista
**Cosa fa**: lista corrispettivi filtrati per anno o range date; senza filtri usa l'anno corrente (performance).
**Logica codice**: regex `^{anno}` o range su `data`, sort desc, skip/limit.
**Note**: NON esclude i record soft-deleted (`entity_status="deleted"` da DELETE /all): gli archiviati restano visibili.

### POST /api/corrispettivi/ricalcola-iva — scorporo IVA 10%
**Cosa fa**: per i corrispettivi con IVA 0/null calcola imponibile e IVA con scorporo al 10% e li salva (`iva_calcolata_scorporo=True`).

### POST /api/corrispettivi/ricalcola-annulli-non-riscosso — ricalcolo non riscosso
**Cosa fa**: ricalcola `pagato_non_riscosso = lordo riepiloghi − (contanti + elettronico)` su tutti i corrispettivi; inizializza `totale_ammontare_annulli=0` se mancante.

### GET /api/corrispettivi/totals — totali complessivi
**Cosa fa**: `$group` unico su tutta la collection: totale generale/contanti/elettronico/IVA + count; se IVA=0 stima con scorporo 10%.
**Note**: nessun filtro anno: somma tutta la storia; include i soft-deleted.

### POST /api/corrispettivi/upload-xml — upload singolo XML RT
**Cosa fa**: importa un corrispettivo XML (default `force_update=True`: sovrascrive l'esistente della stessa giornata).
**Logica codice**: decodifica multi-encoding → `parse_corrispettivo_xml` → `ingest_corrispettivo_parsed(source="xml")`; risposta con action created/updated/duplicate e id prima nota cassa/banca generati.
**Note**: è così che il flusso "manuale serale" viene consolidato: l'XML aggiorna il record provvisorio a `definitivo_xml`.

### POST /api/corrispettivi/upload-xml-bulk — upload massivo XML
**Cosa fa**: come sopra per N file (default `force_update=False`: i doppioni vengono segnalati, non aggiornati). Contatori imported/updated/duplicates/errors.

### POST /api/corrispettivi/sincronizza-prima-nota — allinea prima nota cassa
**Cosa fa**: per ogni corrispettivo aggiorna (o crea) il movimento `prima_nota_cassa` con `categoria:"Corrispettivi"` alla stessa data, incluso il blocco `dettaglio` (contanti, elettronico, IVA, matricola RT).
**Note**: match per sola data+categoria: con più punti cassa lo stesso movimento può essere sovrascritto.

### DELETE /api/corrispettivi/all — archivia tutti i non inviati
**Cosa fa**: soft-delete (`entity_status="deleted"`) di tutti i corrispettivi con `status != "sent_ade"`; quelli inviati all'AdE sono preservati.

### DELETE /api/corrispettivi/{corrispettivo_id} — elimina singolo
**Cosa fa**: soft-delete con validazione `BusinessRules.can_delete_corrispettivo` (blocca se inviato AdE o registrato in prima nota); annulla il movimento prima nota collegato (`stato:"annullato"`).

### POST /api/corrispettivi/upload-zip — upload ZIP di XML
**Cosa fa**: estrae gli XML dallo ZIP (salta `__MACOSX`) e li importa con `ingest_corrispettivo_parsed(update_if_exists=False)`.

### POST /api/corrispettivi/scarica-magazzino?data= — scarico ingredienti stimato
**Cosa fa**: scarica dal magazzino gli ingredienti in base ai corrispettivi del giorno via ricette.
**Logica codice**: per OGNI ricetta stima `max(1, totale/100)` porzioni, scala `giacenza_teorica` in `magazzino_doppia_verita` e pusha movimento `SCARICO_VENDITA`.
**Note**: logica puramente STIMATA (distribuzione uniforme su tutte le ricette, 1 porzione/100€): non usa dati scontrino reali; chiamate ripetute scaricano più volte (nessuna idempotenza).

### POST /api/corrispettivi/collega-vendite-ricette — report consumo teorico
**Cosa fa**: nel periodo dato stima porzioni vendute per ricetta (incasso/prezzo medio, distribuzione uniforme) e consumo teorico ingredienti. Solo report, nessuna scrittura.

### POST /api/corrispettivi/import-csv — import CSV Agenzia Entrate
**Cosa fa**: importa corrispettivi dal CSV del portale AdE (separatore `;`, importi "000000003605,60", date DD/MM/YYYY).
**Logica codice**: parse manuale riga per riga; dedup su `id_invio` O (data, totale); insert nuovo (con evento `CORRISPETTIVO_REGISTRATO`) o update dell'esistente.
**Note**: `parse_amount` fa `replace('.','')` poi `replace(',','.')`: corretto per il formato AdE, ma il dedup (data,totale) può agganciare il record sbagliato con più RT nello stesso giorno.

### GET /api/corrispettivi/template-csv — template CSV
**Cosa fa**: restituisce un CSV di esempio scaricabile nel formato AdE.

### POST /api/corrispettivi/elimina-duplicati?anno= — dedup per data (aggressivo)
**Cosa fa**: per ogni DATA dell'anno tiene solo il record con importo più alto ed elimina fisicamente gli altri.
**Note**: assume un solo RT/punto cassa: con più dispositivi cancella dati validi (usare cleanup-duplicati-forte che raggruppa anche per matricola).

### DELETE /api/corrispettivi/hard-delete/{corrispettivo_id} — eliminazione fisica singola.
### POST /api/corrispettivi/hard-delete-bulk — eliminazione fisica per lista di `ids`.

### POST /api/corrispettivi/cleanup-duplicati-forte?anno= — dedup sicuro
**Cosa fa**: delega a `corrispettivi_helpers.cleanup_duplicate_corrispettivi`: raggruppa per (data, matricola_rt, totale±0.01) e tiene il più vecchio.

### POST /api/corrispettivi/rebuild-prima-nota?anno= — rigenera prima nota
**Cosa fa**: delega a `rebuild_prima_nota_from_corrispettivi`: elimina i movimenti `source=corrispettivo_*` del periodo e li ricrea (cassa + banca POS) dai corrispettivi validi.

### POST /api/corrispettivi/auto-ricostruisci-dati — auto-riparazione
**Cosa fa**: ricalcola IVA mancante (scorporo 10%), backfilla `data` da `data_trasmissione`, rimuove duplicati evidenti (stessa data+totale+punto_cassa, tiene il primo).

### GET /api/corrispettivi/view-by-filename?filename= — vista scontrino da filename
**Cosa fa**: cerca il movimento `prima_nota_cassa` con quel `xml_filename`, recupera il corrispettivo per data e renderizza l'HTML "scontrino" (`generate_corrispettivo_html`, brand Ceraldi Caffè hardcoded).

### GET /api/corrispettivi/{corrispettivo_id}/view — vista scontrino per id
**Cosa fa**: come sopra partendo dall'id corrispettivo; integra i dettagli dal movimento prima nota associato (per corrispettivo_id o data+categoria).

### POST /api/corrispettivi/manuale — inserimento serale provvisorio (v2)
**Cosa fa**: registra il totale giornaliero manuale prima dell'arrivo dell'XML AdE; opzionalmente salva anche il POS reale serale.
**Logica codice**: valida data/totale; se esiste già un record `definitivo_xml` per la data → 409; altrimenti update (totale_manuale, stato=provvisorio) o insert nuovo (`source:"manuale_serale"`, contanti/elettronico null); se `pos_reale_serale` fornito upserta un'entrata in `prima_nota_banca` con `source:"chiusura_pos_mobile"`.

### GET /api/corrispettivi/manuali-senza-xml — alert "manca XML"
**Cosa fa**: elenca i corrispettivi in stato provvisorio/manca_xml (o legacy senza stato con source manuale), calcolando `giorni_attesa_xml` e `alert_attivo` (soglia 7 giorni); `giorni_minimi` filtra i più vecchi.

### POST /api/corrispettivi/aggiorna-stati-mancanti — job manutenzione
**Cosa fa**: porta a `manca_xml` i provvisori con data più vecchia di 7 giorni (chiamabile da UI o scheduler).

---

## fatture_module/ (`/api/fatture-ricevute`) — archivio e pagamenti fatture passive

Router composto in `__init__.py` con `add_api_route` (rotte statiche prima delle dinamiche). `common.py`: `COL_FATTURE_RICEVUTE = "invoices"` (fix: era `indice_documenti`). Support: `helpers.py` (get_or_create_fornitore, salva_dettaglio_righe, salva_allegato_pdf, generate_invoice_html), `metodo_pagamento.py` (`normalizza_metodo_pagamento`: contanti/MP01→cassa; bonifico/carta/SEPA/RID/PayPal/MP05-MP21→banca; assegno/MP02/MP03→assegno NON auto-routato; ambiguo→None), `ciclo_utils.py` (cerca_match_bancario, esegui_riconciliazione, COL_SCADENZIARIO="scadenziario_fornitori"). Il vecchio `import_xml.py` (pipeline duplicata) è stato rimosso.

### GET /api/fatture-ricevute/archivio — archivio unificato (crud.py)
**Cosa fa**: lista unificata da DUE collection (`invoices` + `fatture_passive`) con filtri anno/mese/fornitore/stato/search e paginazione.
**Logica codice**: costruisce query separate per i due schemi (per `invoices` copre ENTRAMBI gli schemi EN/IT incluso il filtro stato pagata/importata/anomala su 4 campi); query in parallelo (asyncio.gather, max 3000+3000); normalizza con `_normalizza_da_invoices`/`_normalizza_da_fatture_passive` (imponibile/IVA stimati con scorporo 22% se assenti); doppio dedup: per `xml_filename` (preferisce invoices) e per CONTENUTO (numero+piva+data+importo, tiene il doc collegato a prima nota); arricchisce ogni riga con `fornitore_metodo_pagamento` dall'anagrafica (lookup P.IVA su partita_iva/piva/vat_number).

### GET /api/fatture-ricevute/fornitori — lista fornitori (crud.py)
**Cosa fa**: lista semplice da `fornitori` con search su ragione_sociale/partita_iva e filtro `con_fatture` (fatture_count>0).

### GET /api/fatture-ricevute/statistiche — KPI archivio (crud.py)
**Cosa fa**: statistiche fatture ricevute (totale, importi, pagate, da pagare, fornitori unici, anomale) per anno.
**Logica codice**: aggregation su `invoices` con espressioni che coprono entrambi gli schemi; dedup di contenuto dentro la pipeline ($group su numero/piva/data/importo) per non gonfiare i contatori; "anomale" = importo ≤0/mancante o numero mancante.

### POST /api/fatture-ricevute/pulisci-duplicati — dedup con pulizia contabile (crud.py)
**Cosa fa**: elimina da `invoices` i doppioni di contenuto tenendo il "migliore" (con prima nota/pagato, a parità il più vecchio) ed elimina anche prima nota (cassa+banca) e scadenze generate dai doppioni.
**Note**: eseguita anche in automatico dal job Automazioni ogni 30 min.

### POST /api/fatture-ricevute/paga-manuale — pagamento manuale (pagamento.py)
**Cosa fa**: registra il pagamento di una fattura in Cassa o Banca creando il movimento di prima nota.
**Logica codice**: valida fattura_id/importo/metodo∈{cassa,banca}; dedup: se esiste già un movimento con quel `fattura_id` nella collection target lo riusa; altrimenti insert movimento (`source:"pagamento_manuale"`); aggiorna la scadenza (`scadenziario_fornitori`: stato=pagato, pagato=True); setta su fattura `pagato/status/stato_pagamento`, `metodo_pagamento(=cassa|banca)`, link `prima_nota_*_id` (azzera l'altro); update su `invoices` (due update sulla stessa collection per retrocompat); evento `FATTURA_PAGATA`.
**Note**: il pagamento via banca NON auto-riconcilia (riconciliazione EC è processo separato); sovrascrive il metodo originale del fornitore con il generico cassa/banca.

### POST /api/fatture-ricevute/cambia-metodo-pagamento — cambio metodo (pagamento.py)
**Cosa fa**: cambia `metodo_pagamento` della fattura (salvando precedente + flag `metodo_pagamento_modificato_manualmente`), propaga alle scadenze collegate e, se `aggiorna_fornitore=true`, aggiorna anche il metodo predefinito del fornitore.

### POST /api/fatture-ricevute/riconcilia-con-estratto-conto — riconciliazione manuale (pagamento.py)
**Cosa fa**: collega fattura ↔ movimento `estratto_conto_movimenti`: fattura riconciliata+pagata, movimento riconciliato con `fattura_id`, prima_nota_banca collegata aggiornata; evento `FATTURA_PAGATA`.

### GET /api/fatture-ricevute/verifica-incoerenze-estratto-conto — audit (pagamento.py)
**Cosa fa**: elenca fatture pagate via banca ma senza movimento EC corrispondente (importo ±0.5, stesso giorno).
**Note**: costruzione query data fragile (dict vuoto come condizione se manca data_pagamento); legacy.

### POST /api/fatture-ricevute/aggiorna-metodi-pagamento — backfill metodi (pagamento.py)
**Cosa fa**: per le fatture senza metodo (`None/""/da_configurare`) copia il metodo dal fornitore (lookup batch per P.IVA, no N+1).
**Note**: **rischio**: se il metodo del fornitore è bancario setta `riconciliato=True` SENZA verificare l'estratto conto.

### POST /api/fatture-ricevute/backfill-autoroute — backfill massivo prima nota (pagamento.py)
**Cosa fa**: per ogni fattura non registrata in prima nota e non pagata (su `invoices` E `fatture_passive`), crea il movimento cassa/banca in base al metodo del fornitore e la marca pagata.
**Logica codice**: mappa fornitori→metodo (una query); `normalizza_metodo_pagamento` decide la destinazione (assegno e ambigui SKIPPATI); dedup su movimento esistente per `fattura_id` (in tal caso solo link); insert movimento (`source:"backfill_auto_da_fornitore"`, `riconciliato=False`), update fattura su entrambe le collection, evento `FATTURA_PAGATA`; report dettagliato skip/errori.
**Note**: marca pagate in massa con `data_pagamento = data fattura` (presunzione, non evidenza bancaria).

### POST /api/fatture-ricevute/riconcilia-paypal — riconciliazione PayPal (pagamento.py)
**Cosa fa**: delega a `paypal_riconciliazione.esegui_riconciliazione_completa` usando i pagamenti PayPal estratti da PDF hardcoded nel servizio (2024 + Q4 2025).

### POST /api/fatture-ricevute/auto-ricostruisci-dati — auto-fix (pagamento.py)
**Cosa fa**: wrapper che rilancia `aggiorna_metodi_pagamento_da_fornitori` e ritorna il conteggio. Il campo `fatture_riparate` è sempre 0 (placeholder).

### GET /api/fatture-ricevute/lista-paypal — fatture PayPal (pagamento.py)
**Cosa fa**: lista fatture con `riconciliato_paypal=True` o `metodo_pagamento="PayPal"` + totale importi.
**Note**: match case-sensitive su "PayPal": i valori normalizzati lowercase ("paypal") non matchano.

### POST /api/fatture-ricevute/import-paypal — import estratto PayPal (pagamento.py)
**Cosa fa**: importa CSV PayPal (colonne Data/Descrizione/Lordo, solo importi negativi=uscite) o, per PDF, usa i dataset hardcoded; poi `riconcilia_pagamenti_paypal`.

### GET /api/fatture-ricevute/fattura/{fattura_id}/view-assoinvoice — vista ASSO (crud.py)
**Cosa fa**: renderizza la fattura in HTML con il foglio di stile ufficiale AssoSoftware.
**Logica codice**: lookup tollerante (id → COL → _id ObjectId); XML da disco (`xml_file_path`, con estrazione grezza da P7M cercando `<?xml`) o dai campi `xml_raw`/`xml_content`; trasformazione XSLT (lxml, `static/FoglioStileAssoSoftware.xsl`); fallback HTML generico (`generate_invoice_html`) con righe da `dettaglio_righe_fatture` o `linee`.

### GET /api/fatture-ricevute/fattura/{fattura_id}/pdf/{allegato_id} — download allegato (crud.py)
**Cosa fa**: decodifica il base64 dell'allegato da `allegati_fatture` e lo restituisce come PDF attachment.

### GET /api/fatture-ricevute/fattura/{fattura_id} — dettaglio (crud.py)
**Cosa fa**: fattura (lookup id → invoices → ObjectId) + righe (`dettaglio_righe_fatture`) + allegati (senza base64).

### PUT /api/fatture-ricevute/fattura/{fattura_id} — update (crud.py)
**Cosa fa**: aggiorna solo pagato, data_pagamento, metodo_pagamento, riconciliato, note su `invoices`.

---

## suppliers_module/ (`/api/suppliers` E alias `/api/fornitori`) — anagrafica fornitori

Stesso router montato su due prefissi: ogni endpoint risponde a entrambi. Cache lista fornitori (chiave `suppliers_list`, TTL 300s) invalidata su create/update/toggle/delete e dall'import fatture. `common.py`: PAYMENT_METHODS = SOLO 6 metodi (contanti, assegno, bonifico, misto, rid, carta) con destinazione prima nota; METODI_BANCARI = bonifico/assegno/rid/carta.

### GET /api/suppliers/payment-methods — dizionario 6 metodi con label e destinazione prima nota (validation.py).
### GET /api/suppliers/payment-terms — termini di pagamento standard (VISTA…120GG) (validation.py).

### GET /api/suppliers/validazione-p0 — problemi bloccanti (validation.py)
**Cosa fa**: elenca fornitori senza metodo pagamento e fornitori con metodo bancario senza IBAN (contatori + primi 50 di ciascuno).

### GET /api/suppliers/dizionario-metodi-pagamento — dizionario P.IVA→metodo (validation.py)
**Cosa fa**: aggrega i fornitori per metodo e costruisce la mappa `{piva: {metodo, denominazione, iban}}` usata dalla Learning Machine; include distribuzione e contatori con/senza metodo.

### POST /api/suppliers/aggiorna-dizionario-metodo — apprendimento metodo (validation.py)
**Cosa fa**: aggiorna metodo/IBAN di un fornitore per P.IVA; se `source="learning_machine"` logga il cambiamento in `learning_feedback`. Valida il metodo contro i 6 PAYMENT_METHODS.

### POST /api/suppliers/ricerca-iban-web — ricerca IBAN massiva (iban.py)
**Cosa fa**: per i fornitori con metodo bancario senza IBAN cerca l'IBAN nelle fatture (`pagamento.iban`, regex IBAN IT 27 char) e in fallback scandaglia altri campi pagamento; OpenCorporates usato solo per completare la ragione sociale; salva `iban`+`iban_fonte`.
**Note**: nonostante il docstring citi "TUTTE le fonti/VIES", l'IBAN arriva SOLO dalle fatture XML (le API pubbliche non espongono IBAN).

### POST /api/suppliers/ricerca-iban-singolo/{supplier_id} — ricerca IBAN singolo (iban.py)
**Cosa fa**: cerca `pagamento.iban` nelle fatture del fornitore (per P.IVA), valida formato/lunghezza e lo salva; altrimenti ritorna trovato=False con conteggio fatture.

### POST /api/suppliers/sync-iban — sync lista IBAN (iban.py)
**Cosa fa**: aggrega tutti gli IBAN unici per `cedente_piva` dalle fatture e li salva in `iban_lista` del fornitore (promuove il primo a `iban` principale se mancante).

### POST /api/suppliers/upload-excel — import Excel v1 (import_export.py)
**Cosa fa**: importa fornitori da Excel (pandas, colonne fisse "Partita Iva"/"Denominazione"/…); update dei soli campi anagrafici se esiste (preserva metodo/IBAN), insert con default `metodo_pagamento:"bonifico"` se nuovo; backfilla `supplier_id` sulle fatture con quella P.IVA.

### POST /api/suppliers/import-excel — import Excel v2 (import_export.py)
**Cosa fa**: variante con mapping colonne flessibile (alias multipli), combina indirizzo+civico, dedup per P.IVA o denominazione; nuovo fornitore con default "bonifico".
**Note**: duplicazione quasi totale di upload-excel; entrambi assegnano "bonifico" di default.

### POST /api/suppliers/aggiorna-tutti-bulk — completamento anagrafiche (bulk.py)
**Cosa fa**: per i fornitori con dati incompleti interroga VIES → OpenCorporates → fatture locali e completa ragione sociale/indirizzo/cap/comune/provincia (`dati_completati_da`); sleep 0.3s tra chiamate.

### POST /api/suppliers/aggiorna-metodi-bulk — metodi in blocco (bulk.py)
**Cosa fa**: applica una lista {partita_iva, metodo_pagamento} (normalizza cassa→contanti, banca→bonifico); opzionale `default_per_mancanti` applicato a TUTTI i fornitori senza metodo.
**Note**: nessuna validazione contro PAYMENT_METHODS; il default massivo bypassa il flusso "configura fornitore".

### POST /api/suppliers/correggi-nomi-mancanti — fix nomi (bulk.py)
**Cosa fa**: per i fornitori senza denominazione la recupera dalle fatture (cedente_denominazione/supplier_name).

### POST /api/suppliers/sincronizza-da-fatture — sync massiva (bulk.py)
**Cosa fa**: crea in `fornitori` un record per ogni P.IVA presente nelle fatture e mancante in anagrafica (default `metodo_pagamento:"bonifico"`, `esclude_magazzino:True`), o completa il nome se vuoto.
**Note**: duplica la logica di `/api/fatture/sync-suppliers`; stesso conflitto sul default "bonifico".

### GET /api/suppliers/search-piva/{partita_iva} — lookup P.IVA (base.py)
**Cosa fa**: cerca i dati aziendali per P.IVA: VIES (REST) → fatture locali → anagrafica; parse euristico dell'indirizzo VIES (cap/comune/provincia).

### GET /api/suppliers — lista con statistiche (base.py)
**Cosa fa**: lista fornitori con filtri (search, metodo, attivo, esclude_magazzino, stato_anagrafica nuovo/storico, prodotto in magazzino) arricchita con statistiche fatture.
**Logica codice**: cache 5 min (solo senza filtri); indice alias su TUTTE le P.IVA del fornitore (partita_iva/piva/vat_number); aggregation su `invoices` con coalescenza supplier_vat|cedente_piva|fornitore_partita_iva per fatture_count/totale/non_pagate/prima e ultima fattura; filtro `prodotto` risolto via `warehouse_products` (fornitore_piva); filtro nuovo/storico post-aggregation su `prima_fattura_data` vs soglia `giorni_nuovo`.

### POST /api/suppliers — crea fornitore (base.py)
**Cosa fa**: crea fornitore dal modale UI; ragione sociale obbligatoria, 409 se P.IVA già esistente (su 3 campi), metodo validato contro i 6 PAYMENT_METHODS; scrive sia `partita_iva` sia `piva`; invalida cache.

### GET /api/suppliers/filtered — lista con contatori (base.py)
**Cosa fa**: wrapper di list_suppliers (no cache) che aggiunge badge/contatori coerenti col filtro attivo (totale, popolano/esclusi magazzino, attivi) e echo dei filtri.
**Note**: i contatori sono calcolati sulla PAGINA restituita (skip/limit), non sull'intero result set.

### GET /api/suppliers/stats — statistiche anagrafica (base.py)
**Cosa fa**: totale/attivi/inattivi + distribuzione per metodo pagamento ($group).

### GET /api/suppliers/scadenze — fatture in scadenza (base.py)
**Cosa fa**: fatture non pagate con `data_scadenza` nei prossimi N giorni, raggruppate per fornitore + flag critiche a 7 giorni.
**Note**: confronta `data_scadenza` (YYYY-MM-DD) con `today.isoformat()` (timestamp completo): il range di partenza esclude le scadenze di OGGI.

### GET /api/suppliers/{supplier_id} — dettaglio (base.py)
**Cosa fa**: fornitore per id o P.IVA + ultime 20 fatture (`cedente_piva`).

### PUT /api/suppliers/{supplier_id} — update completo (base.py)
**Cosa fa**: aggiorna il fornitore; se viene configurato il metodo: valida contro i 6 metodi, salva `metodo_pagamento_dal` e pusha in `storico_metodi_pagamento`, risolve gli alert `fornitore_senza_metodo_pagamento`; se `esclude_magazzino=true` ELIMINA i prodotti del fornitore da `warehouse_stocks` e `warehouse_inventory`; pubblica `fornitore.aggiornato` sul bus (Learning Machine).
**Note**: lo storico viene letto DOPO l'update: `metodo_vecchio` registrato è in realtà quello nuovo; `partita_iva` non è modificabile (poppata dal body).

### POST /api/suppliers/{supplier_id}/toggle-active — attiva/disattiva (base.py)
**Cosa fa**: inverte `attivo`; alla disattivazione avvisa se ci sono fatture non pagate; sincronizza il flag `escluso` sui record omonimi (match per prefisso nome sulla STESSA collection fornitori).

### DELETE /api/suppliers/{supplier_id} — elimina (base.py)
**Cosa fa**: blocca se ci sono fatture collegate (per `cedente_piva`) senza `force=true`; poi delete fisico + pulizia relazionale: partite aperte del fornitore → `annullata`, alert aperti → risolti.
**Note**: il conteggio fatture usa solo `cedente_piva`: le fatture con sola `supplier_vat` non bloccano l'eliminazione.

### GET /api/suppliers/{supplier_id}/fatturato?anno= — fatturato annuo (base.py)
**Cosa fa**: aggregation per mese su `invoices` (cedente_piva|supplier_vat, data_fattura|data) con totale/count/pagate + dettaglio mensile.
**Note**: somma solo `importo_totale` (schema IT): le fatture con solo `total_amount` risultano a 0.

### GET /api/suppliers/{supplier_id}/iban-from-invoices — IBAN dalle fatture (base.py)
**Cosa fa**: elenca gli IBAN unici trovati in `pagamento.iban` delle fatture del fornitore + IBAN principale e lista salvata.

### PUT /api/suppliers/{supplier_id}/metodo-pagamento — cambio metodo rapido (base.py)
**Cosa fa**: normalizza (cassa→contanti, banca→bonifico) e valida contro lista propria (include anche riba, non presente in PAYMENT_METHODS); aggiorna e emette evento `FORNITORE_UPDATED`.
**Note**: validazione INCOERENTE con PUT /{id} (che rifiuterebbe "riba"); non aggiorna `metodo_pagamento_predefinito` né lo storico.

### PUT /api/suppliers/{supplier_id}/nome — rinomina (base.py)
**Cosa fa**: setta denominazione+ragione_sociale; se il fornitore NON esiste lo CREA con la P.IVA=supplier_id e default "bonifico".

### GET /api/suppliers/{supplier_id}/fatture — estratto conto fornitore (base.py)
**Cosa fa**: estratto fatture del fornitore con filtri anno/date/importi/tipo (fattura vs nota credito TD04/TD05/NC), paginato; coalescenza campi EN/IT; il metodo mostrato fa fallback su quello del fornitore.

### GET /api/suppliers/{supplier_id}/dati-da-fatture — anagrafica da XML (base.py)
**Cosa fa**: recupera dalla prima fattura disponibile i dati anagrafici del cedente (denominazione, CF, indirizzo…) per precompilare la scheda fornitore.

---

## fornitori_learning.py (`/api/fornitori-learning`) — keywords e classificazione centri di costo

Gestisce `fornitori_keywords` (associazioni fornitore→keywords→centro di costo) usate per classificare le fatture in centri di costo, l'associazione fornitori↔magazzino e la classificazione F24. I centri di costo vengono da `app.services.learning_machine_cdc.CENTRI_COSTO` (ricaricato con importlib.reload a ogni chiamata).

### GET /api/fornitori-learning/stats — copertura learning
**Cosa fa**: contatori: fornitori con keywords vs fornitori unici da fatture, % fatture classificate (`centro_costo_id`), % F24 classificati (`f24_unificato`).

### GET /api/fornitori-learning/lista — tutte le associazioni configurate (sort per fatture_count desc).

### GET /api/fornitori-learning/non-classificati — fornitori da configurare
**Cosa fa**: fornitori con fatture in "Altri costi non classificati" e senza keywords; per ciascuno calcola i totali REALI (tutte le fatture, non solo le non classificate) + esempi di descrizioni linee.
**Note**: query N+1 (un'aggregation per fornitore).

### POST /api/fornitori-learning/salva — crea/aggiorna associazione
**Cosa fa**: upsert in `fornitori_keywords` per nome normalizzato (rimozione suffissi societari); ricalcola fatture_count/totale con regex sul nome.
**Note**: il nome fornitore viene usato NON escapato in `$regex`: nomi con parentesi/caratteri regex fanno fallire la query.

### DELETE /api/fornitori-learning/{fornitore_id} — elimina associazione (per `id` = `fk_<nome>`).

### POST /api/fornitori-learning/riclassifica-con-keywords — riclassificazione massiva
**Cosa fa**: per ogni fornitore configurato trova le fatture non classificate (o in "Altri costi") e assegna il centro di costo suggerito (lookup per chiave o codice in CENTRI_COSTO) o quello dedotto da `classifica_fattura_per_centro_costo`; setta `classificazione_fonte:"keywords_personalizzate"`.
**Note**: nel report `nuovo_centro_costo` usa il cdc dell'ULTIMA fattura del ciclo (impreciso se le fatture ricevono cdc diversi).

### GET /api/fornitori-learning/suggerisci-keywords/{fornitore_nome} — suggerimenti
**Cosa fa**: estrae le 15 parole più frequenti (>3 char, stopword escluse) dalle descrizioni linee di max 20 fatture del fornitore.

### GET /api/fornitori-learning/centri-costo-disponibili — lista CENTRI_COSTO (id, nome, codice).

### POST /api/fornitori-learning/associa-magazzino — collega prodotti↔fornitori
**Cosa fa**: per ogni fornitore configurato trova i prodotti in `warehouse_inventory` (regex su campo `fornitori`) e, se la categoria è "altro"/vuota, assegna la categoria magazzino mappata dal centro di costo (mappa hardcoded CDC_TO_MAGAZZINO_CATEGORIA) + fornitore_principale/keywords.

### GET /api/fornitori-learning/prodotti-per-fornitore/{fornitore_nome} — prodotti a magazzino del fornitore, raggruppati per categoria (max 100).

### GET /api/fornitori-learning/giacenze-fornitore/{fornitore_nome} — giacenze e valore stimato per categoria (aggregation su warehouse_inventory; valore = giacenza × media prezzi min/max).

### POST /api/fornitori-learning/classifica-f24 — classificazione F24 automatica
**Cosa fa**: per gli F24 (`f24_unificato`) senza centro di costo usa `classifica_f24_per_centro_costo` (per codici tributo: 60xx→IVA, 10xx→personale, 391x→IMU…) e salva cdc + tipo_tributo_principale (`classificazione_fonte:"learning_machine"`).

### GET /api/fornitori-learning/f24-statistiche — contatori F24 classificati/non + aggregazione per centro di costo (somma `saldo_finale`).

### POST /api/fornitori-learning/riclassifica-f24/{f24_id} — riclassificazione manuale singolo F24 (valida cdc per chiave o codice; `classificazione_fonte:"manuale"`).

---

## scadenzario_fornitori.py (`/api/scadenzario-fornitori`) — scadenze e cash flow

Lavora principalmente sulla collection `invoices` (fatture non pagate = scadenze implicite) e in due endpoint sulla collection dedicata `scadenziario_fornitori` (partite create dall'event bus del ciclo passivo). Riconciliazione via `ciclo_utils`.

### GET /api/scadenzario-fornitori/ — scadenzario principale
**Cosa fa**: fatture non pagate dell'anno raggruppate per periodo (scadute/oggi/7gg/30gg/oltre) con totali e top-20 fornitori.
**Logica codice**: query `pagato≠True AND status≠"paid"` + anno su invoice_date|data_scadenza; fallback `data_scadenza = invoice_date` se assente; calcolo `giorni_alla_scadenza` in Python.
**Note**: non controlla `stato_pagamento`/`paid` (schema alternativo) — le fatture pagate solo con quei flag apparirebbero come aperte; in pratica i canali di pagamento settano sempre anche `pagato`.

### GET /api/scadenzario-fornitori/urgenti — scadute o in scadenza entro 7 giorni
**Cosa fa**: elenco compatto (id, numero, fornitore, importo, giorni, stato scaduta/oggi/in_scadenza) per dashboard e notifiche, con totali.

### GET /api/scadenzario-fornitori/cash-flow-previsionale?mesi= — previsione uscite
**Cosa fa**: distribuisce le fatture da pagare per mese di scadenza nei prossimi N mesi (bucket YYYY-MM) con totale previsto.
**Note**: i bucket sono generati a passi di 30 giorni: possono saltare un mese di calendario.

### PUT /api/scadenzario-fornitori/aggiorna-scadenza — modifica scadenza
**Cosa fa**: setta `data_scadenza` + `note_scadenza` sulla fattura in `invoices` (body Pydantic ScadenzaUpdate).

### GET /api/scadenzario-fornitori/aging — aging debiti
**Cosa fa**: classifica TUTTE le fatture non pagate per giorni di ritardo (corrente/0-30/31-60/61-90/oltre 90) con importi e percentuali.

### GET /api/scadenzario-fornitori/scadenze-integrate — scadenze da collection dedicata
**Cosa fa**: legge `scadenziario_fornitori` (partite create dall'integrazione ciclo passivo/event bus) per anno e stato (aperte/pagate/tutte), raggruppa per periodo e normalizza i campi per la UI.

### POST /api/scadenzario-fornitori/riconcilia-automatica — riconciliazione batch
**Cosa fa**: per ogni scadenza aperta dell'anno cerca un match in `estratto_conto_movimenti` (`cerca_match_bancario`: importo ±1€, finestra -120/+30gg, match nome fornitore anche fuzzy ≥75, fallback media confidenza per importi ≥100€) e, se `dry_run=false`, esegue `esegui_riconciliazione` (scadenza→saldato/pagato, movimento→riconciliato, log in `riconciliazioni`).
**Note**: default `dry_run=true` (solo anteprima). `esegui_riconciliazione` scrive `fattura_id = scadenza_id` sul movimento EC (id scadenza, non id fattura): ambiguo per chi legge quel campo.

---

## schede_tecniche.py (`/api/schede-tecniche`) — schede tecniche prodotti (HACCP)

Estrae i prodotti dalle fatture XML su disco (`/tmp/uploads/pec_xml`, lookup via `fatture_passive.xml_filename` o glob per P.IVA), usa Claude (haiku, via client Anthropic) per identificare brand/sito/URL PDF, scarica i PDF (httpx) o li cerca negli allegati Gmail (IMAP sincrono in `asyncio.to_thread`), e archivia tutto in `schede_tecniche` (PDF come Binary in MongoDB). Job asincroni in `schede_tecniche_jobs`.

### POST /api/schede-tecniche/popola-fornitore/{fornitore_id} — anagrafica da XML su disco
**Cosa fa**: legge i file XML delle fatture del fornitore, estrae il blocco CedentePrestatore (telefono, email, indirizzo…) e aggiorna SOLO i campi mancanti in `fornitori`.

### POST /api/schede-tecniche/cerca — avvia ricerca schede (background)
**Cosa fa**: crea un job e lancia in BackgroundTasks `_esegui_ricerca`: estrae prodotti dagli XML (o usa `prodotti_manuali`), per max 50 prodotti: skip se scheda già esistente → AI identifica brand/URL → tenta download diretto → scraping homepage sito ufficiale → scansione Gmail; salva scheda con stato trovato/url_trovato/url_suggerito/non_trovato.

### GET /api/schede-tecniche/fornitore/{fornitore_id} — schede + prodotti da cercare
**Cosa fa**: merge delle schede in DB (senza pdf_data) con i prodotti XML non ancora cercati (stato `non_cercato`) + ultimo job.

### GET /api/schede-tecniche/job/{job_id} — stato del job di ricerca.

### GET /api/schede-tecniche/download/{scheda_id} — download PDF
**Cosa fa**: restituisce il PDF binario archiviato o, se assente, redirect all'`url_fonte`; 404 se nessuno dei due.

### DELETE /api/schede-tecniche/{scheda_id} — elimina scheda.

### GET /api/schede-tecniche/prodotti/{fornitore_id} — prodotti estratti dagli XML (max 30)
**Note**: il lookup fornitore usa `{"_id": fornitore_id}` come alternativa (stringa vs ObjectId): di fatto funziona solo il match su `id`.

---

## previsioni_acquisti.py (`/api/previsioni-acquisti`) — previsioni da storico acquisti

Lavora sulla collection `acquisti_prodotti` (una riga per linea fattura, con descrizione normalizzata uppercase per raggruppamento). Costanti: 340 giorni lavorativi/anno.

### GET /api/previsioni-acquisti/prodotti — prodotti acquistati aggregati
**Cosa fa**: aggregation per `descrizione_normalizzata` con quantità totale, spesa, n. acquisti, fornitori (max 5), primo/ultimo acquisto, prezzo medio; filtri anno/fornitore/search.

### GET /api/previsioni-acquisti/statistiche?anno= — statistiche per previsioni
**Cosa fa**: per ogni prodotto (top 100 per quantità) calcola media giornaliera (/340), media settimanale, frequenza acquisti (giorni periodo/n. acquisti) e confronto con l'anno precedente (variazione % + trend ↑↓→).

### GET /api/previsioni-acquisti/previsioni — proposta ordini
**Cosa fa**: dall'anno di riferimento proietta la quantità prevista per le prossime N settimane (media settimanale × N), frequenza ordine, fornitori abituali e costo stimato (prezzo medio), con totale complessivo.

### POST /api/previsioni-acquisti/popola-storico — inizializzazione storico
**Cosa fa**: scorre TUTTE le fatture di `invoices` e registra ogni linea in `acquisti_prodotti` via `registra_acquisto_da_fattura` (dedup per fattura_id+descrizione normalizzata).
**Note**: il docstring di `registra_acquisto_da_fattura` dice "chiamato ogni volta che viene processato un XML", ma NESSUNA pipeline di import lo chiama: lo storico si aggiorna SOLO rilanciando questo endpoint manualmente.

### GET /api/previsioni-acquisti/confronto-ordine — confronto quantità vs media
**Cosa fa**: confronta la quantità che si vuole ordinare con la media per ordine dello storico (±20% = sopra/sotto media) e dà un giudizio/consiglio testuale; 404 se il prodotto non è nello storico.

---

## Anomalie e rischi trasversali (riepilogo)

1. **Shadowing dei router**: gli overlay (`fatture_overlay`, `invoices_main_overlay`) vincono sui path identici dei router legacy. Conseguenze concrete: (a) l'upload effettivo da UI su `/api/fatture/upload-xml[-bulk]` usa l'upsert dell'overlay e NON `process_xml_bytes` — la "pipeline unica" vale solo per Drive/documenti/import automatici; (b) l'overlay **rifiuta i P7M** che il legacy gestiva; (c) l'overlay non emette `FATTURA_CREATED` (niente partita scadenziario per quel canale).
2. **Decoratore orfano in invoices_main** (righe 363-368): `GET /{invoice_id}` legacy risponde con la lista bank-pending; il vero handler dettaglio è irraggiungibile. Mascherato dall'overlay.
3. **Bug reale in invoices_main.get_invoices_by_month**: legge `invoice['_id']` dopo projection `{"_id":0}` → KeyError (route morta grazie all'overlay). `get_archived_months` usa `$month/$year` su date stringa → ritorna sempre `[]`.
4. **delete-by-month**: formato `month_year` sbagliato (YYYY-MM vs MM-YYYY del service) + filtro `user_id` → non elimina nulla per le fatture XML. Tutti i delete "danger zone" di invoices_main filtrano per `user_id` che le fatture importate non hanno.
5. **Regola metodo pagamento violata da più endpoint**: il legacy `POST /api/fatture/upload-xml` defaulta a "bonifico" e lascia che la riconciliazione EC sovrascriva il metodo; `sync-suppliers`, `sincronizza-da-fatture`, `upload-excel`, `import-excel` e `PUT /{id}/nome` creano fornitori con default "bonifico". La regola "metodo SOLO dal fornitore, sospesa se non configurato" è rispettata solo da `process_xml_bytes`/`process_fattura_to_db` e dall'overlay.
6. **Commenti/docstring che mentono**: in `process_fattura_to_db`/`process_xml_bytes` i commenti dicono "banca SOLO se trovato in EC", ma `auto_registra_prima_nota` registra in banca SEMPRE per metodo bancario (l'EC serve solo al collegamento). `ricerca-iban-web` promette VIES/OpenCorporates ma l'IBAN esce solo dalle fatture. `registra_acquisto_da_fattura` dice di essere chiamato a ogni import ma non lo chiama nessuno.
7. **Pagato senza evidenza bancaria**: `aggiorna-metodi-pagamento` setta `riconciliato=True` dal solo metodo fornitore; `backfill-autoroute` e `paga-anno/{anno}` marcano pagate in massa (il secondo senza nemmeno creare prima nota).
8. **Bug minore in process_fattura_to_db**: l'evento FATTURA_CREATED legge `supplier_result.get("nuovo")` ma la chiave è `supplier_created` → `fornitore_nuovo` sempre False (upload manuale/documenti).
9. **ensure_supplier_exists**: fallback di match per PREFISSO nome (primi 30 char, regex case-insensitive) quando la P.IVA non trova nulla → rischio di agganciare la fattura al fornitore sbagliato con nomi simili.
10. **update_supplier**: lo storico metodi registra come "vecchio" il valore già aggiornato; validazione metodi incoerente tra `PUT /{id}` (6 metodi) e `PUT /{id}/metodo-pagamento` (accetta anche riba).
11. **Corrispettivi**: `GET /` e `/totals` non filtrano i soft-deleted; `elimina-duplicati` per sola data è distruttivo con più RT; `scarica-magazzino` è una stima non idempotente.
12. **fornitori_learning**: nomi fornitore usati in `$regex` senza escape in `/salva` e `/suggerisci-keywords` → errore con caratteri speciali; N+1 in `/non-classificati`.
13. **Tre pipeline di import fatture coesistono**: overlay upsert (`/api/fatture/upload-xml*`), `process_xml_bytes` (Drive/bulk legacy/documenti), `InvoiceService.process_xml_invoice` (`/api/invoices/upload*`, schema service con payment_status/month_year). Producono documenti con schemi diversi nella stessa collection `invoices` — è l'origine del doppio schema EN/IT e dei dedup a runtime.
