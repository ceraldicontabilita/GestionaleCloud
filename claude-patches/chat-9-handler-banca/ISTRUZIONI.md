# PATCH Chat 9b — Handler eventi Banca↔Riconciliazione
## Data: 22 Aprile 2026

---

## Cosa contiene questa patch

Handler per il ciclo bancario. Quando un movimento viene importato dall'estratto conto,
il sistema cerca automaticamente partite aperte compatibili e:
- Score ≥ 0.90 → crea match confermato, aggiorna fattura/F24/stipendio
- Score 0.60-0.90 → crea proposte per l'utente
- Score < 0.30 → genera alert "non riconciliato"

### File nuovi

```
app/services/handlers/banca_handlers.py
```

---

## Modifiche in file esistenti

### 1. Aggiornare `app/services/event_bus.py` → `register_all_handlers()`

Aggiungere dopo gli handler fattura:

```python
    # --- Fase 3: Banca ↔ Riconciliazione (Chat 9b) ---
    from app.services.handlers.banca_handlers import (
        on_movimento_banca_cerca_match,
        on_match_confermato_propaga,
        on_movimento_banca_audit,
    )
    register_handler(EventTypes.MOVIMENTO_BANCA_IMPORTATO, on_movimento_banca_cerca_match)
    register_handler(EventTypes.MOVIMENTO_BANCA_IMPORTATO, on_movimento_banca_audit)
    register_handler(EventTypes.MATCH_CONFERMATO, on_match_confermato_propaga)
```

### 2. Aggiungere `propagate_event()` in `app/routers/bank/bank_statement_import.py`

Dopo la riga `await db[COLLECTION_ESTRATTO_CONTO].insert_one(estratto_doc.copy())` (circa riga 834),
aggiungere:

```python
        # --- EVENT BUS: propaga evento movimento importato ---
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.MOVIMENTO_BANCA_IMPORTATO, {
                "movimento_id": estratto_doc["id"],
                "importo": estratto_doc.get("importo", 0),
                "data": estratto_doc.get("data", ""),
                "descrizione": estratto_doc.get("descrizione", ""),
                "tipo": estratto_doc.get("tipo", ""),
            }, db, source_module="bank_statement_import")
        except Exception:
            logger.exception("Errore propagazione evento movimento_banca")
```

### 3. Aggiungere `propagate_event()` in `app/routers/bank/bank_statement_bulk_import.py`

Dopo la riga `await db[collection].insert_one(record)` (circa riga 212),
aggiungere lo stesso blocco del punto 2, usando `record` al posto di `estratto_doc`.

### 4. Aggiungere `propagate_event()` nella conferma match manuale

In `app/routers/bank/bank_reconciliation.py` o nel router di riconciliazione
usato dalla UI, quando l'utente conferma un match, aggiungere:

```python
    from app.services.event_bus import propagate_event, EventTypes
    await propagate_event(EventTypes.MATCH_CONFERMATO, {
        "match_id": match_id,
    }, db, source_module="riconciliazione_manuale", user="utente")
```

---

## Flusso completo dopo la patch

```
1. Utente importa estratto conto CSV/PDF
2. Per ogni movimento:
   a. Viene salvato in estratto_conto_movimenti
   b. propagate_event("movimento_banca.importato")
   c. Handler cerca_match interroga partite_aperte
   d. Scoring 4 livelli:
      - €3.250 uscita + "F24" in causale → match con partita F24 (score 0.92) → AUTO
      - €1.190 uscita + "STIPENDIO" → match con partita stipendio (score 0.85) → PROPOSTA
      - €500 uscita generica → match con fattura fornitore (score 0.95) → AUTO
      - €12.50 "COMMISSIONI" → skip (commissione bancaria)
   e. Match auto → aggiorna fattura/F24/cedolino come pagato + risolve alert
   f. Match proposta → salva candidato, utente conferma dalla UI
   g. Nessun match → alert RIC_NON_RICONCILIATO
3. Audit log per ogni movimento importato
```

---

## Come verificare

1. Creare manualmente una partita aperta:
   ```python
   from app.services.partite_aperte_engine import crea_partita
   await crea_partita("fattura_fornitore", "test_fat_1", "invoices",
                      "forn_1", "Test SRL", 500.00, db,
                      data_scadenza="2026-04-20")
   ```
2. Importare un estratto conto con un movimento da €500 uscita
3. Verificare in `riconciliazioni_match`: deve esserci un match confermato
4. Verificare in `partite_aperte`: la partita deve essere chiusa (residuo=0)
5. Verificare in `audit_log`: deve esserci "movimento_importato" + "match_cercato"

---

## Prossima patch

Handler per F24, Cedolini, Corrispettivi e Trasferimenti (Fasi 4-7).
