"""Processo dedicato alle automazioni periodiche di GestionaleCloud.

Il processo web non deve eseguire scansioni Drive/Gmail, OCR o agenti shadow
nello stesso event loop che serve le richieste HTTP.  Questo modulo possiede
quindi un accesso dedicato a Drive/Sheets e uno scheduler separato, ma non espone API.
"""

from __future__ import annotations

import asyncio
import signal

from app.config import settings
from app.database import Database
from app.utils.logger import get_logger, setup_logging


setup_logging()
logger = get_logger(__name__)


async def run_scheduler(stop_event: asyncio.Event | None = None) -> None:
    """Avvia lo scheduler dedicato e chiude ordinatamente le sue risorse."""

    stop_event = stop_event or asyncio.Event()
    await Database.connect_db()
    try:
        settings.validate_startup()
        from app.scheduler import start_scheduler, stop_scheduler

        start_scheduler()
        logger.info("Processo scheduler dedicato avviato")
        await stop_event.wait()
    finally:
        try:
            from app.scheduler import stop_scheduler

            stop_scheduler()
        except Exception:
            logger.exception("Arresto scheduler dedicato non completato")
        await Database.close_db()
        logger.info("Processo scheduler dedicato arrestato")


def main() -> None:
    """Entry point usato dal supervisore di produzione."""

    async def _main() -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _request_stop(*_args) -> None:
            loop.call_soon_threadsafe(stop_event.set)

        for signame in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, signame, None)
            if sig is not None:
                try:
                    signal.signal(sig, _request_stop)
                except (OSError, RuntimeError, ValueError):
                    logger.warning("Handler %s non disponibile", signame)

        await run_scheduler(stop_event)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
