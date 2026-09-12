"""Stato aggregato veritiero per l'ingest documentale Drive.

Il vecchio ``sync_tutti`` poteva restituire ``status=ok`` anche quando uno o
piu' canali annidati erano in errore. Questa policy non cambia gli scanner e
non tocca i documenti: corregge soltanto il riepilogo restituito a scheduler,
monitoraggio e diagnostica.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Dict, Mapping, Tuple


def aggregate_channel_status(
    channels: Mapping[str, Mapping[str, Any]],
) -> Tuple[str, list[str]]:
    """Calcola lo stato del ciclo dai risultati reali dei canali eseguiti."""
    error_channels = [
        name
        for name, result in channels.items()
        if str(result.get("status") or "").lower() == "error"
    ]
    if not error_channels:
        return "ok", []
    if len(error_channels) == len(channels):
        return "error", error_channels
    return "degraded", error_channels


def install_drive_documenti_status_policy() -> None:
    """Avvolge ``sync_tutti`` senza modificare gli scanner dei singoli canali."""
    from . import drive_documenti_ingest as module

    current = module.sync_tutti
    if getattr(current, "_aggregate_status_policy", False):
        return

    @wraps(current)
    async def sync_tutti_with_status(db) -> Dict[str, Any]:
        result = await current(db)
        channels = dict(result.get("canali") or {})
        status, error_channels = aggregate_channel_status(channels)
        return {
            **result,
            "status": status,
            "error_channels": error_channels,
        }

    sync_tutti_with_status._aggregate_status_policy = True
    module.sync_tutti = sync_tutti_with_status
