# PATCH Chat 9c — Handler F24, Cedolini, Corrispettivi, Trasferimenti
## Data: 22 Aprile 2026

---

## File nuovi

```
app/services/handlers/f24_handlers.py           — 2 handler (acquisito, pagato)
app/services/handlers/cedolino_handlers.py       — 2 handler (importato, pagato)
app/services/handlers/corrispettivo_handlers.py  — 1 handler (split contanti/POS)
app/services/handlers/trasferimento_handlers.py  — 1 handler (crea lato opposto)
```

---

## Aggiornare `app/services/event_bus.py` → `register_all_handlers()`

Aggiungere dopo gli handler banca:

```python
    # --- Fase 4: F24 (Chat 9c) ---
    from app.services.handlers.f24_handlers import (
        on_f24_acquisito_crea_partita,
        on_f24_pagato_risolvi,
    )
    register_handler(EventTypes.F24_ACQUISITO, on_f24_acquisito_crea_partita)
    register_handler(EventTypes.F24_PAGATO, on_f24_pagato_risolvi)

    # --- Fase 5: Cedolini (Chat 9c) ---
    from app.services.handlers.cedolino_handlers import (
        on_cedolino_importato,
        on_cedolino_pagato_risolvi,
    )
    register_handler(EventTypes.CEDOLINO_IMPORTATO, on_cedolino_importato)
    register_handler(EventTypes.CEDOLINO_PAGATO, on_cedolino_pagato_risolvi)

    # --- Fase 6: Corrispettivi (Chat 9c) ---
    from app.services.handlers.corrispettivo_handlers import (
        on_corrispettivo_split,
    )
    register_handler(EventTypes.CORRISPETTIVO_REGISTRATO, on_corrispettivo_split)

    # --- Fase 7: Trasferimenti (Chat 9c) ---
    from app.services.handlers.trasferimento_handlers import (
        on_trasferimento_crea_lato_opposto,
    )
    register_handler(EventTypes.TRASFERIMENTO_CREATO, on_trasferimento_crea_lato_opposto)
```

---

## Dove aggiungere `propagate_event()` nei router esistenti

### F24 — `app/routers/f24/f24_main.py` (dopo salvataggio F24)
```python
    from app.services.event_bus import propagate_event, EventTypes
    await propagate_event(EventTypes.F24_ACQUISITO, {
        "f24_id": f24_doc["id"],
        "importo_totale": f24_doc.get("importo_totale"),
        "data_scadenza": f24_doc.get("data_scadenza"),
        "periodo": f24_doc.get("periodo"),
        "codice_tributo": f24_doc.get("codice_tributo"),
        "data_acquisizione": f24_doc.get("created_at"),
    }, db, source_module="f24_import")
```

### Cedolini — `app/routers/cedolini.py` (dopo salvataggio cedolino)
```python
    from app.services.event_bus import propagate_event, EventTypes
    await propagate_event(EventTypes.CEDOLINO_IMPORTATO, {
        "cedolino_id": ced["id"],
        "dipendente_id": ced.get("dipendente_id"),
        "dipendente_nome": ced.get("nome_dipendente"),
        "netto": ced.get("netto") or ced.get("netto_mese"),
        "lordo": ced.get("lordo"),
        "mese": ced.get("mese"),
        "anno": ced.get("anno"),
        "tipo_cedolino": ced.get("tipo_cedolino", "mensile"),
    }, db, source_module="cedolini_import")
```

### Corrispettivi — `app/routers/invoices/corrispettivi.py` (dopo salvataggio)
```python
    from app.services.event_bus import propagate_event, EventTypes
    await propagate_event(EventTypes.CORRISPETTIVO_REGISTRATO, {
        "corrispettivo_id": corr["id"],
        "data": corr.get("data"),
        "totale": corr.get("totale") or corr.get("importo_totale"),
        "contanti": corr.get("contanti") or corr.get("quota_contanti"),
        "elettronico": corr.get("elettronico") or corr.get("quota_pos"),
    }, db, source_module="corrispettivi")
```

### Trasferimenti — nel punto dove l'utente crea un versamento cassa→banca
```python
    from app.services.event_bus import propagate_event, EventTypes
    await propagate_event(EventTypes.TRASFERIMENTO_CREATO, {
        "movimento_id": mov["id"],
        "origine": "cassa",  # o "banca" per prelievi
        "importo": mov.get("importo"),
        "data": mov.get("data"),
        "descrizione": mov.get("descrizione"),
    }, db, source_module="prima_nota")
```

---

## Riepilogo handler totali dopo questa patch

| Evento | Handler | File |
|--------|---------|------|
| fattura.created | 3 handler | fattura_handlers.py |
| fattura.pagata | 1 handler | fattura_handlers.py |
| fornitore.updated | 1 handler | fattura_handlers.py |
| movimento_banca.importato | 2 handler | banca_handlers.py |
| match.confermato | 1 handler | banca_handlers.py |
| f24.acquisito | 1 handler | f24_handlers.py |
| f24.pagato | 1 handler | f24_handlers.py |
| cedolino.importato | 1 handler | cedolino_handlers.py |
| cedolino.pagato | 1 handler | cedolino_handlers.py |
| corrispettivo.registrato | 1 handler | corrispettivo_handlers.py |
| trasferimento.creato | 1 handler | trasferimento_handlers.py |
| **TOTALE** | **14 handler** | **6 file** |

Con 14 handler attivi, il gestionale diventa relazionale: ogni modulo comunica
con gli altri attraverso l'event bus, le partite aperte tracciano ogni debito/credito,
e il motore di riconciliazione collega automaticamente movimenti bancari a documenti.
