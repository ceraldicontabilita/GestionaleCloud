# ============================================================
# PATCH — Aggiungere in event_bus.py → register_all_handlers()
# Sostituire i commenti della Fase 2 con il codice reale
# ============================================================

# In event_bus.py, dentro register_all_handlers(), DECOMMENTARE e SOSTITUIRE:

def register_all_handlers():
    """
    Registra tutti gli handler dei moduli.
    Chiamare all'avvio dell'app (in main.py dopo connect_db).
    """
    logger.info("Registrazione handler event bus...")
    
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
    
    # --- Fase 3: Banca ↔ Riconciliazione (Chat 11) ---
    # from app.services.handlers.banca_handlers import ...
    # register_handler(EventTypes.MOVIMENTO_BANCA_IMPORTATO, ...)
    
    registered = sum(len(h) for h in _handlers.values())
    logger.info(f"Event bus pronto: {registered} handler registrati per {len(_handlers)} tipi evento")
