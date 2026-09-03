"""Avvio e arresto del modulo HR dentro il lifespan del gestionale.

Registra gli handler dell'event bus HR, esegue il seed dei periodi TFR e
avvia i due job periodici del modulo (scadenzario contratti/prova e
sincronizzazione paghe). I job girano solo dove il gestionale tiene attivo
lo scheduler (``PROCESS_ROLE`` combined/scheduler): un processo "web" puro
non li avvia, come per il resto delle automazioni.
"""
import logging

logger = logging.getLogger(__name__)


async def avvia_modulo_hr(*, scheduler_attivo: bool) -> None:
    try:
        from app.hr.services.event_bus import register_all_handlers
        register_all_handlers()
    except Exception:
        logger.exception("HR: registrazione handler eventi fallita")

    try:
        from app.hr.services.tfr_seed import seed_tfr_periodi
        await seed_tfr_periodi()
    except Exception as exc:
        logger.warning("HR: seed periodi TFR non eseguito: %s", exc)

    if not scheduler_attivo:
        logger.info("HR: scheduler disattivo in questo processo, job periodici non avviati")
        return
    try:
        from app.hr.services.scadenze_scheduler import start_scheduler
        start_scheduler()
    except Exception as exc:
        logger.warning("HR: scadenzario non avviato: %s", exc)
    try:
        from app.hr.services.paghe_scheduler import start_scheduler as start_paghe
        start_paghe()
    except Exception as exc:
        logger.warning("HR: sincronizzazione paghe periodica non avviata: %s", exc)


def arresta_modulo_hr() -> None:
    for modulo in ("scadenze_scheduler", "paghe_scheduler"):
        try:
            module = __import__(f"app.hr.services.{modulo}", fromlist=["stop_scheduler"])
            module.stop_scheduler()
        except Exception:
            logger.debug("HR: stop %s non necessario", modulo, exc_info=True)
