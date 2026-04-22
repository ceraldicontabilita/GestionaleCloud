# PATCH Chat 9d — Handler Dipendenti, Magazzino, Documenti/Inbox
## Data: 22 Aprile 2026

## Questa patch colma i 3 moduli mancanti dalle specifiche operative.

---

## File nuovi

```
app/services/handlers/dipendente_handlers.py   — 3 handler
app/services/handlers/magazzino_handlers.py     — 2 handler
app/services/handlers/documento_handlers.py     — 2 handler
```

## File da patchare

### 1. `app/services/deduplica.py` — aggiungere `cerca_duplicato_dipendente`
Copiare il contenuto di `deduplica_dipendente_patch.py` in fondo a `deduplica.py`.

### 2. `app/services/event_bus.py` → `register_all_handlers()`
Aggiungere:

```python
    # --- Dipendenti (Chat 9d) ---
    from app.services.handlers.dipendente_handlers import (
        on_dipendente_created,
        on_dipendente_updated_risolvi,
        on_dipendente_cessato,
    )
    register_handler(EventTypes.DIPENDENTE_CREATED, on_dipendente_created)
    register_handler(EventTypes.DIPENDENTE_UPDATED, on_dipendente_updated_risolvi)
    register_handler(EventTypes.DIPENDENTE_CESSATO, on_dipendente_cessato)

    # --- Documenti/Inbox (Chat 9d) ---
    from app.services.handlers.documento_handlers import (
        on_documento_acquisito,
        on_documento_instradato,
    )
    register_handler(EventTypes.DOCUMENTO_ACQUISITO, on_documento_acquisito)
    register_handler(EventTypes.DOCUMENTO_INSTRADATO, on_documento_instradato)
```

**NOTA**: Il magazzino handler `on_fattura_righe_magazzino` va aggiunto
a `EventTypes.FATTURA_CREATED` come handler aggiuntivo:

```python
    from app.services.handlers.magazzino_handlers import (
        on_fattura_righe_magazzino,
        on_verifica_sotto_scorta,
    )
    register_handler(EventTypes.FATTURA_CREATED, on_fattura_righe_magazzino)
    # on_verifica_sotto_scorta va chiamato da scheduler/cron, non da evento
```

### 3. Aggiungere nuovi EventTypes in `event_bus.py`
Nella classe `EventTypes` aggiungere (se non già presenti):

```python
    DOCUMENTO_INSTRADATO = "documento.instradato"
```

### 4. Dove inserire `propagate_event()` nei router

#### Dipendenti — `app/routers/employees/dipendenti.py`
Dopo creazione dipendente:
```python
    await propagate_event(EventTypes.DIPENDENTE_CREATED, {
        "dipendente_id": dip["id"],
        "nome": dip.get("nome"),
        "cognome": dip.get("cognome"),
        "codice_fiscale": dip.get("codice_fiscale"),
        "iban_cedolino": dip.get("iban_cedolino"),
        "tipo_contratto": dip.get("tipo_contratto"),
        "stato": dip.get("stato", "attivo"),
    }, db, source_module="dipendenti")
```

Dopo cessazione dipendente:
```python
    await propagate_event(EventTypes.DIPENDENTE_CESSATO, {
        "dipendente_id": dip_id,
        "nome_completo": f"{dip.get('nome', '')} {dip.get('cognome', '')}",
    }, db, source_module="dipendenti")
```

#### Documenti — `app/routers/email_download.py` o `documents_inbox_classify.py`
Dopo salvataggio documento in inbox:
```python
    await propagate_event(EventTypes.DOCUMENTO_ACQUISITO, {
        "documento_id": doc["id"],
        "filename": doc.get("filename"),
        "origine": "gmail",  # o "pec" o "upload"
        "mime_type": doc.get("mime_type"),
        "hash_file": doc.get("hash_file"),
        "mittente": doc.get("mittente"),
    }, db, source_module="email_download")
```

#### Magazzino — sottoscotra va schedulato
`on_verifica_sotto_scorta` va chiamato periodicamente (es. ogni ora) dallo scheduler:
```python
    from app.services.handlers.magazzino_handlers import on_verifica_sotto_scorta
    await on_verifica_sotto_scorta({}, Database.get_db())
```

---

## Riepilogo COMPLETO di tutti gli handler dopo questa patch

| # | Evento | Handler | File |
|---|--------|---------|------|
| 1 | fattura.created | crea_partita | fattura_handlers.py |
| 2 | fattura.created | alert_fornitore | fattura_handlers.py |
| 3 | fattura.created | audit | fattura_handlers.py |
| 4 | fattura.created | righe_magazzino | magazzino_handlers.py |
| 5 | fattura.pagata | risolvi | fattura_handlers.py |
| 6 | fornitore.updated | risolvi | fattura_handlers.py |
| 7 | movimento_banca.importato | cerca_match | banca_handlers.py |
| 8 | movimento_banca.importato | audit | banca_handlers.py |
| 9 | match.confermato | propaga | banca_handlers.py |
| 10 | f24.acquisito | crea_partita | f24_handlers.py |
| 11 | f24.pagato | risolvi | f24_handlers.py |
| 12 | cedolino.importato | crea_partita+alert | cedolino_handlers.py |
| 13 | cedolino.pagato | risolvi | cedolino_handlers.py |
| 14 | corrispettivo.registrato | split_contanti_pos | corrispettivo_handlers.py |
| 15 | trasferimento.creato | lato_opposto | trasferimento_handlers.py |
| 16 | dipendente.created | deduplica+alert | dipendente_handlers.py |
| 17 | dipendente.updated | risolvi_alert | dipendente_handlers.py |
| 18 | dipendente.cessato | verifica_flussi | dipendente_handlers.py |
| 19 | documento.acquisito | classifica+instrada | documento_handlers.py |
| 20 | documento.instradato | aggiorna_stato | documento_handlers.py |
| **TOTALE** | **13 tipi evento** | **20 handler** | **9 file** |

Tutti i 10 moduli delle specifiche operative sono ora coperti.
