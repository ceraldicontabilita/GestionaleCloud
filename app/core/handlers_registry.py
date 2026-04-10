"""
HANDLERS REGISTRY — Registro centrale di tutti gli handler.
Importa qui UNA VOLTA all'avvio. Registra tutto sul bus degli eventi.

TABELLA COMPLETA:
  fattura.importata         → magazzino, scadenziario, learning_cdc,
                              fornitore_learning, ricette, notifica
  fattura.pagata            → prima_nota_fattura, notifica
  cedolino.importato        → prima_nota_cedolino, tfr, notifica
  estratto_conto.importato  → matching_banca (fatture, cedolini, f24, pos)
  corrispettivi.importati   → prima_nota_corrispettivi, check_pos
  fornitore.creato          → learning_fornitore, controlla_iban
  fornitore.aggiornato      → learning_fornitore
  ingrediente.prezzo_cambiato → aggiorna_costo_ricette
"""
import logging
from app.core.event_bus import bus

logger = logging.getLogger(__name__)


def registra_tutti_gli_handler():
    """Chiama questa funzione UNA VOLTA all'avvio del server."""

    # Import lazy per evitare circular imports
    from app.handlers.magazzino    import handler_carico_magazzino
    from app.handlers.scadenziario import handler_crea_scadenza
    from app.handlers.prima_nota   import (handler_prima_nota_fattura,
                                            handler_prima_nota_cedolino)
    from app.handlers.tfr          import handler_aggiorna_tfr
    from app.handlers.learning     import handler_classifica_cdc
    from app.handlers.notifiche    import (handler_notifica_fattura,
                                            handler_notifica_cedolino)
    from app.handlers.estratto_conto import handler_matching_estratto_conto
    from app.handlers.corrispettivi  import (handler_prima_nota_corrispettivi,
                                              handler_check_coerenza_pos)
    from app.handlers.fornitore      import (handler_aggiorna_learning_fornitore,
                                              handler_controlla_iban_mancante)
    from app.handlers.ricette        import handler_aggiorna_costo_ricette

    # ─── FATTURA IMPORTATA ────────────────────────────────────────────────
    bus.register("fattura.importata", handler_carico_magazzino,
                 priority=10, name="magazzino_carico")

    bus.register("fattura.importata", handler_crea_scadenza,
                 priority=20, name="scadenziario_pagamento")

    bus.register("fattura.importata", handler_classifica_cdc,
                 priority=30, name="learning_centro_costo")

    bus.register("fattura.importata", handler_aggiorna_learning_fornitore,
                 priority=35, name="learning_fornitore_keywords")

    bus.register("fattura.importata", handler_aggiorna_costo_ricette,
                 priority=40, name="ricette_aggiorna_costi")

    bus.register("fattura.importata", handler_notifica_fattura,
                 priority=90, name="notifica_ws_fattura")

    # ─── FATTURA PAGATA ───────────────────────────────────────────────────
    bus.register("fattura.pagata", handler_prima_nota_fattura,
                 priority=10, name="prima_nota_pagamento")

    bus.register("fattura.pagata", handler_notifica_fattura,
                 priority=90, name="notifica_ws_pagamento")

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
    bus.register("fornitore.creato", handler_aggiorna_learning_fornitore,
                 priority=10, name="learning_fornitore_nuovo")

    bus.register("fornitore.creato", handler_controlla_iban_mancante,
                 priority=20, name="check_iban_mancante")

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
