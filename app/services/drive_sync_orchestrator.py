"""Avvio coordinato degli import Drive esposti dalla pagina Documenti.

Ogni importatore conserva il proprio lock e la propria logica di deduplica.
Questo modulo offre soltanto un comando unico, senza cambiare parser o dati.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from app.services import (
    drive_cedolini_ingest,
    drive_corrispettivi_ingest,
    drive_documenti_ingest,
    drive_estratti_conto_ingest,
    drive_invoice_ingest,
    drive_quietanze_ingest,
)


_tasks: Dict[str, asyncio.Task] = {}
logger = logging.getLogger(__name__)


def _consume_task_result(name: str, task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Sincronizzazione Drive %s terminata con errore", name)


def _start_task(name: str, factory: Callable[[], Awaitable[Dict[str, Any]]]) -> str:
    current = _tasks.get(name)
    if current is not None and not current.done():
        return "running"
    _tasks[name] = asyncio.create_task(factory())
    _tasks[name].add_done_callback(lambda task: _consume_task_result(name, task))
    return "started"


def _start_existing_service(service: Any, db: Any) -> str:
    if not service.is_configured():
        return "not_configured"
    return "started" if service.start_background_sync(db) else "running"


def _generic_channels_available() -> bool:
    return any(
        drive_documenti_ingest.is_enabled(channel)
        and drive_documenti_ingest.is_configured(channel)
        for channel in drive_documenti_ingest.CANALI
    )


def start_all(db: Any) -> Dict[str, str]:
    """Avvia tutti e soli i canali Drive configurati, senza attenderne l'esito."""
    statuses = {
        "fatture": _start_existing_service(drive_invoice_ingest, db),
        "cedolini": _start_existing_service(drive_cedolini_ingest, db),
        "corrispettivi": _start_existing_service(drive_corrispettivi_ingest, db),
        "quietanze": _start_existing_service(drive_quietanze_ingest, db),
    }

    statuses["estratti_conto"] = (
        _start_task("estratti_conto", lambda: drive_estratti_conto_ingest.sync(db))
        if drive_estratti_conto_ingest.is_configured()
        else "not_configured"
    )
    statuses["documenti"] = (
        _start_task("documenti", lambda: drive_documenti_ingest.sync_tutti(db))
        if _generic_channels_available()
        else "not_configured"
    )
    return statuses
