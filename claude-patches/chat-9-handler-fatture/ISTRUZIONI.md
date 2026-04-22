# PATCH Chat 9 — Handler eventi Fatture↔Fornitori
## Data: 22 Aprile 2026

---

## Cosa contiene questa patch

Handler eventi per il ciclo passivo. Quando una fattura XML viene importata,
il sistema ora automaticamente:
1. Crea una partita aperta nel scadenziario materializzato
2. Genera alert strutturati se il fornitore ha dati incompleti
3. Logga l'operazione nell'audit trail
4. Quando la fattura viene pagata, risolve gli alert collegati
5. Quando il fornitore viene aggiornato (MP/IBAN), risolve gli alert a cascata

### File nuovi da copiare

```
app/services/handlers/__init__.py
app/services/handlers/fattura_handlers.py
```

**Destinazione**: `app/services/handlers/` nel repo.

---

## Modifiche da fare in file esistenti

### 1. Aggiornare `app/services/event_bus.py`

Nella funzione `register_all_handlers()`, sostituire i commenti della Fase 2 con:

```python
    # --- Fase 2: Fatture ↔ Fornitori ↔ Prima Nota (Chat 9) ---
    from app.services.handlers.fattura_handlers import (
        on_fattura_created_crea_partita,
        on_fattura_created_alert_fornitore,
        on_fattura_created_audit,
        on_fattura_pagata_risolvi,
        on_fornitore_aggiornato_risolvi,
    )
    register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_crea_partita)
    register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_alert_fornitore)
    register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_audit)
    register_handler(EventTypes.FATTURA_PAGATA, on_fattura_pagata_risolvi)
    register_handler(EventTypes.FORNITORE_UPDATED, on_fornitore_aggiornato_risolvi)
```

### 2. Aggiungere `propagate_event()` in `app/routers/fatture_module/import_xml.py`

Dopo la riga `await db[COL_FATTURE_RICEVUTE].insert_one(fattura.copy())` (circa riga 149),
aggiungere:

```python
    # --- EVENT BUS: propaga evento fattura creata ---
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(EventTypes.FATTURA_CREATED, {
            "fattura_id": fattura_id,
            "numero_documento": numero_doc,
            "tipo_documento": parsed.get("tipo_documento", "TD01"),
            "importo_totale": parsed.get("total_amount", 0),
            "fornitore_id": fornitore_result.get("fornitore_id"),
            "fornitore_ragione_sociale": fornitore_result.get("ragione_sociale"),
            "fornitore_nuovo": fornitore_result.get("nuovo", False),
            "fornitore_iban": fornitore_obj.get("iban"),
            "metodo_pagamento": metodo_pagamento_finale,
            "data_documento": parsed.get("invoice_date", ""),
            "data_scadenza": parsed.get("pagamento", {}).get("data_scadenza"),
            "stato": stato,
            "pagato": False,
        }, db, source_module="import_xml")
    except Exception:
        logger.exception("Errore propagazione evento fattura.created")
```

### 3. Aggiungere `propagate_event()` nel flusso pagamento fattura

Nei punti dove la fattura viene segnata come pagata (auto-routing in import_xml.py,
conferma manuale in pagamento.py, riconciliazione), aggiungere dopo l'update:

```python
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(EventTypes.FATTURA_PAGATA, {
            "fattura_id": fattura_id,
            "metodo_pagamento": dest,
            "data_pagamento": data_pag,
        }, db, source_module="auto_routing")
    except Exception:
        logger.exception("Errore propagazione evento fattura.pagata")
```

### 4. Aggiungere `propagate_event()` nel router fornitori

In `app/routers/suppliers_module/base.py`, dopo l'update del fornitore (quando l'utente
modifica metodo pagamento o IBAN), aggiungere:

```python
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(EventTypes.FORNITORE_UPDATED, {
            "fornitore_id": fornitore_id,
            "metodo_pagamento": updated_data.get("metodo_pagamento"),
            "iban": updated_data.get("iban"),
        }, db, source_module="fornitori")
    except Exception:
        logger.exception("Errore propagazione evento fornitore.updated")
```

---

## Come verificare che funziona

1. Importare una fattura XML di un fornitore SENZA metodo pagamento
2. Verificare in MongoDB:
   - `partite_aperte`: deve esserci una partita con tipo=fattura_fornitore
   - `alerts`: deve esserci FORN_MP_MANCANTE + FAT_MP_NON_DEFINITO
   - `audit_log`: deve esserci un record "fattura creata"
3. Impostare il metodo pagamento del fornitore dalla pagina Fornitori
4. Verificare che gli alert FORN_MP_MANCANTE e FAT_MP_NON_DEFINITO siano stati risolti
5. Importare una fattura dello stesso fornitore — non deve generare alert duplicati

---

## Prossima patch (Chat 10-11)

Handler per Banca↔Riconciliazione: quando arriva un movimento dall'estratto conto,
il sistema cerca automaticamente partite aperte compatibili con scoring a 4 livelli.
