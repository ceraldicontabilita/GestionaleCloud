"""
HANDLERS REGISTRY — Registro centrale di tutti gli handler.
Importa qui UNA VOLTA all'avvio. Registra tutto sul bus degli eventi.

TABELLA COMPLETA (eventi realmente pubblicati — "fattura.importata" e
"fattura.pagata" non lo sono mai, vedi nota nel corpo della funzione):
  cedolino.importato        → prima_nota_cedolino, tfr, notifica
  estratto_conto.importato  → matching_banca (fatture, cedolini, f24, pos)
  corrispettivi.importati   → prima_nota_corrispettivi, check_pos
  fornitore.creato          → learning_fornitore, controlla_iban (mai pubblicato)
  fornitore.aggiornato      → learning_fornitore
  ingrediente.prezzo_cambiato → aggiorna_costo_ricette
"""
import logging
from app.core.event_bus import bus

logger = logging.getLogger(__name__)


def registra_tutti_gli_handler():
    """Chiama questa funzione UNA VOLTA all'avvio del server."""

    # Import lazy per evitare circular imports
    from app.handlers.prima_nota   import handler_prima_nota_cedolino
    from app.handlers.tfr          import handler_aggiorna_tfr
    from app.handlers.notifiche    import handler_notifica_cedolino
    from app.handlers.estratto_conto import handler_matching_estratto_conto
    from app.handlers.corrispettivi  import (handler_prima_nota_corrispettivi,
                                              handler_check_coerenza_pos)
    from app.handlers.fornitore      import handler_aggiorna_learning_fornitore
    from app.handlers.ricette        import handler_aggiorna_costo_ricette

    # NOTA: "fattura.importata" e "fattura.pagata" non vengono MAI pubblicati
    # da nessun punto reale del codice (verificato: nessun bus.publish su questi
    # due eventi in tutto app/) — i relativi handler (magazzino_carico,
    # scadenziario_pagamento, learning_centro_costo, learning_fornitore_keywords,
    # ricette_aggiorna_costi, notifica_ws_fattura/pagamento, prima_nota_pagamento)
    # non si sono MAI attivati in produzione. Migrati sul bus realmente vivo
    # (app/services/event_bus.py, EventTypes.FATTURA_CREATED): il carico
    # magazzino (on_fattura_righe_magazzino), la creazione scadenza
    # (handler_crea_scadenza), la classificazione centro di
    # costo/deducibilità (handler_classifica_cdc) e il controllo IBAN
    # mancante su fornitore nuovo (handler_controlla_iban_mancante, prima
    # su "fornitore.creato", anch'esso mai pubblicato).
    # Restano gap documentati in memoria/moduli/ e
    # memoria/endpoints/RICONCILIAZIONE_AUDIT.md — da migrare in un intervento
    # dedicato: learning fornitore da fattura (keyword extraction al momento
    # della creazione, oggi parte solo su aggiornamento fornitore), costo
    # ricette da fattura diretta, notifiche websocket su fattura importata/
    # pagata, prima nota su pagamento fattura via bus (già coperta altrove
    # da auto_registra_prima_nota, quindi priorità bassa).

    # ─── CEDOLINO IMPORTATO ───────────────────────────────────────────────
    bus.register("cedolino.importato", handler_prima_nota_cedolino,
                 priority=10, name="prima_nota_salari")

    bus.register("cedolino.importato", handler_aggiorna_tfr,
                 priority=20, name="tfr_accantonamento")

    bus.register("cedolino.importato", handler_notifica_cedolino,
                 priority=90, name="notifica_ws_cedolino")

    # ─── ESTRATTO CONTO IMPORTATO ─────────────────────────────────────────
    bus.register("estratto_conto.importato", handler_matching_estratto_conto,
                 priority=10, name="matching_banca_fatture")

    # ─── CORRISPETTIVI IMPORTATI ──────────────────────────────────────────
    bus.register("corrispettivi.importati", handler_prima_nota_corrispettivi,
                 priority=10, name="prima_nota_corrispettivi")

    bus.register("corrispettivi.importati", handler_check_coerenza_pos,
                 priority=20, name="check_coerenza_pos")

    # ─── FORNITORE CREATO / AGGIORNATO ───────────────────────────────────
    # "fornitore.creato" non è mai pubblicato (stesso pattern morto degli
    # altri): handler_aggiorna_learning_fornitore resta comunque vivo tramite
    # "fornitore.aggiornato" (pubblicato da suppliers_module/base.py).
    # handler_controlla_iban_mancante è stato migrato su FATTURA_CREATED
    # (app/services/event_bus.py) — vedi commento in testa al file.
    bus.register("fornitore.creato", handler_aggiorna_learning_fornitore,
                 priority=10, name="learning_fornitore_nuovo")

    bus.register("fornitore.aggiornato", handler_aggiorna_learning_fornitore,
                 priority=10, name="learning_fornitore_update")

    # ─── INGREDIENTE PREZZO CAMBIATO ─────────────────────────────────────
    bus.register("ingrediente.prezzo_cambiato", handler_aggiorna_costo_ricette,
                 priority=10, name="ricette_ricalcola_margini")

    total = bus.handlers_count()
    eventi = len(bus._handlers)
    logger.info(
        f"[Registry] ✅ {total} handler su {eventi} eventi registrati"
    )
    # Log dettaglio
    for event_type, handlers in bus._handlers.items():
        nomi = [n for _, n, _ in handlers]
        logger.debug(f"  {event_type}: {nomi}")
