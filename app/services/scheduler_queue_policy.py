"""Policy di serializzazione per le automazioni del Gestionale.

Lo scheduler deve mantenere un solo job pesante alla volta sul processo Render
da 512 MiB, ma un job che arriva mentre il lock e' occupato non deve essere
scartato. Questa policy sostituisce soltanto l'esecutore locale: il secondo job
resta sospeso sullo stesso ``asyncio.Lock`` e parte appena il precedente lo
libera.
"""
from __future__ import annotations

import inspect
from typing import Any


def install_scheduler_queue_policy() -> None:
    """Installa una volta la policy FIFO del lock locale dello scheduler."""
    from app import scheduler as scheduler_module

    if getattr(scheduler_module, "_queue_policy_installed", False):
        return

    async def _queued(job_id: str, funzione, *args: Any, **kwargs: Any):
        lock = scheduler_module._sheets_scheduler_lock
        if lock.locked():
            scheduler_module.logger.info(
                "[SCHEDULER] job %s in coda: attende il completamento "
                "dell'automazione corrente",
                job_id,
            )
        async with lock:
            risultato = funzione(*args, **kwargs)
            return await risultato if inspect.isawaitable(risultato) else risultato

    scheduler_module._esegui_con_lock_locale = _queued
    scheduler_module._queue_policy_installed = True
