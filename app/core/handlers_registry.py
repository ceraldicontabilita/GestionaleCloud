"""
HANDLERS REGISTRY — Registro centrale di tutti gli handler.
Questo file va importato UNA VOLTA all'avvio del server (in main.py).
Registra tutti gli handler sul bus degli eventi.

TABELLA COMPLETA HANDLER/EVENTO:
  fattura.importata     → magazzino (p=10), scadenziario (p=20), learning_cdc (p=30),
                          notifica (p=90)
  fattura.pagata        → prima_nota_fattura (p=10), notifica (p=90)
  cedolino.importato    → prima_nota_cedolino (p=10), tfr (p=20), notifica (p=90)
  estratto_conto.importato → (gestito da riconciliazione_intelligente esistente)
  corrispettivi.importati  → (gestito da prima_nota_module/sync esistente)
"""

from app.core.event_bus import bus
from app.handlers.magazzino  import handler_carico_magazzino
from app.handlers.scadenziario import handler_crea_scadenza
from app.handlers.prima_nota import handler_prima_nota_fattura, handler_prima_nota_cedolino
from app.handlers.tfr        import handler_aggiorna_tfr
from app.handlers.learning   import handler_classifica_cdc
from app.handlers.notifiche  import handler_notifica_fattura, handler_notifica_cedolino


def registra_tutti_gli_handler():
    """
    Chiama questa funzione UNA VOLTA all'avvio del server.
    Registra tutti gli handler sul bus degli eventi.
    """

    # ─── FATTURA IMPORTATA ────────────────────────────────────────────────
    bus.register("fattura.importata", handler_carico_magazzino,
                 priority=10, name="magazzino_carico")

    bus.register("fattura.importata", handler_crea_scadenza,
                 priority=20, name="scadenziario_pagamento")

    bus.register("fattura.importata", handler_classifica_cdc,
                 priority=30, name="learning_centro_costo")

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

    total = bus.handlers_count()
    import logging
    logging.getLogger(__name__).info(
        f"[Registry] {total} handler registrati su {len(bus._handlers)} tipi di evento"
    )
