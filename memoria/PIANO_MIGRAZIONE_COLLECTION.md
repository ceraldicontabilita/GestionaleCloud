# PIANO MIGRAZIONE COLLECTION (P1 §5) — GestionaleCloud

Deliverable del consolidamento collezioni. Ogni blocco: sorgenti legacy → canonica,
script di migrazione non distruttivo, stato.

## 5.1 F24 — ✅ FATTO (modelli) · sottosistemi rinviati

**Canonica modelli F24:** `f24_unificato` · **Quietanze:** `quietanze_f24` (separata).

**Helper canonico:** `app/services/f24_canonico.py`
- `chiave_f24(doc)` = chiave naturale (contribuente + periodo + saldo + hash PDF +
  protocollo), stabile tra gli schemi storici.
- `salva_f24(db, doc, source)` = unico punto di scrittura idempotente (upsert per
  chiave naturale, non duplica). Indice `f24_unificato.f24_dedup_key` (sparse).

**Migrazione:** `python -m app.scripts.migra_f24_unificato [--esegui]`
- Sorgenti: `f24_models`, `f24_commercialista` (letterale), `f24_uploaded`, `f24`.
- Non distruttiva (legacy NON cancellate), idempotente (dedup per chiave naturale).
- **Eseguire contestualmente al deploy**: i lettori ora leggono solo `f24_unificato`,
  quindi eventuali F24 storici presenti solo nelle legacy vanno migrati per restare visibili.

**Scritture/letture legacy redirette alla canonica:**
- `supervisione_contabile.py` (riconciliazione automatica): read+update → `f24_unificato`.
- `riconciliazione_smart.py`: read F24 non pagati → `f24_unificato`.
- `document_data_saver.py`: già scriveva canonico (etichetta ritorno corretta).
- `scripts/pulizia_dati.py`: update → `f24_unificato`.
- `f24_analisi.py`: legge solo `f24_unificato` (prima leggeva anche il letterale
  `f24_commercialista` → dopo la migrazione avrebbe contato due volte).
- `COLL_F24_MODELS` marcata DEPRECATA in `db_collections.py`.

**Rinviati (sottosistemi VIVI, non modelli):**
- `f24_pagamenti`, `tributi_pagati`, `distinte_f24`: sottosistema parser paghe
  (`f24_parser.py` + `paghe_riconciliazione.py`), usato per import/distinte F24 da
  buste paga. Consolidarlo richiede rifare quel flusso → fase dedicata.
- `f24_tributi`: indice tributi da classificazione documenti
  (`documents_inbox_classify.py`) — cross-check, concetto diverso dal modello F24.

**Verifica:** 293 test verdi · app boota · `tests/test_p1_f24_consolidamento.py`.

## 5.2 Dipendenti — parziale (P0.3)
Canonica `dipendenti`. Legacy `employees` migrata con
`app/scripts/migra_employees_a_dipendenti.py` (non distruttiva; `id` solo in
$setOnInsert). Redirect letture/scritture `libro_unico_parser`, `verbali_noleggio_api`.
Restano da valutare: `staff`, `payslips`, `employee_contracts`.

## 5.4 Fatture passive — ✅ FATTO
**Canonica:** `invoices`. **Legacy:** `fatture_passive` (alimentata solo dal ponte
ERP esterno, oggi disattivato fail-closed).

- Helper `app/services/fatture_canonico.py`: `invoice_key(numero,piva,data)`,
  `mappa_fattura_passiva()` (schema legacy→canonico), `salva_invoice_passiva()`
  (upsert idempotente per invoice_key, non tocca lo stato derivato di fatture esistenti).
- Ponte ERP `erp_bridge.py`: ora scrive/legge `invoices` (dedup per invoice_key),
  non più `fatture_passive`.
- `fatture_module/crud.py`: RIMOSSO il dedup runtime a due sorgenti; legge solo `invoices`.
- Redirect lettori: `pagamento.py` (niente cross-update fatture_passive), `cespiti.py`,
  `anagrafica_fornitori_xml.py` (campi canonici supplier_vat/supplier_name).
- Migrazione: `python -m app.scripts.migra_fatture_passive_a_invoices [--esegui]`
  (non distruttiva, dedup per invoice_key, non sovrascrive stato derivato).
  **Eseguire al deploy**: i lettori ora usano solo `invoices`.
- Verifica: 297 test verdi · `tests/test_p1_fatture_passive.py`.

## 5.3 Cedolini — ✅ FATTO (parziale, con debito documentato)
**Canonica del CEDOLINO ELABORATO:** `cedolini`. Distinzione mantenuta (dal piano):
file ricevuto → `cedolini_email_attachments` (documento origine, NON si tocca);
cedolino elaborato → `cedolini` (canonica); riepilogo aggregato → `riepilogo_cedolini`
(resta separato).

- Helper `app/services/cedolini_canonico.py`: `chiave_cedolino(doc)` = chiave naturale
  contribuente + anno + mese (robusta a schemi diversi: campi espliciti o `periodo`
  tipo '2026-03' / '03/2026'), `salva_cedolino()` upsert idempotente per chiave naturale
  (non sovrascrive un cedolino già presente).
- `payslips` (alias inglese LEGACY del cedolino elaborato): marcata DEPRECATA in
  `db_collections.py` (nessun writer/reader applicativo attivo). Migrazione:
  `python -m app.scripts.migra_payslips_a_cedolini [--esegui]` (non distruttiva,
  dedup per chiave naturale, `payslips` NON cancellata).
- **DEBITO DOCUMENTATO — `buste_paga` NON toccata**: è un sottosistema VIVO (Libro Unico
  Zucchetti + distinte BPM + TFR/acconti) con schema/chiave propri
  (`busta_id`/`stato_pagamento`/`acconti`/`netto_mese`, chiave `{codice_fiscale, periodo}`).
  Writer: `paghe_riconciliazione.py`, `distinte_bpm.py`, `libro_unico_parser.py`.
  Va consolidata in una fase dedicata al flusso paghe per non rompere riconciliazione
  cedolini/distinte/TFR.
- Verifica: 301 test verdi · `tests/test_p1_cedolini.py`.

## 5.5-5.9 — DA FARE
Fatture emesse (`fatture_emesse` vs `invoices_emesse`), estratto
conto (canonica `estratto_conto_movimenti`), fornitori (`fornitori`), documenti
classificati (`documents_classified` vs `documenti_classificati`), magazzino.
Vedi PROMPT_DEFINITIVO §5.2/5.5-5.9.
