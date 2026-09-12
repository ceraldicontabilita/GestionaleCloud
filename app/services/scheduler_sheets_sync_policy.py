"""Policy per il backup Google Sheets quando Supabase e' il backend primario.

In produzione Supabase e' il registro operativo. Il vecchio job automatico
``google_sheets_ledger_sync`` riscriveva integralmente decine di fogli ogni
30 minuti e poteva esaurire la quota Google Sheets (HTTP 429) anche senza
variazioni dei dati.

Questa policy non rimuove il registro portabile e non modifica ``sync_all``:
la sincronizzazione manuale dall'area amministrativa resta disponibile. Viene
neutralizzato soltanto il job periodico quando ``DATA_BACKEND=supabase``.
"""
from __future__ import annotations

from functools import wraps
from typing import Any


def automatic_sheets_sync_enabled(data_backend: str) -> bool:
    """Il full-sync periodico serve solo quando Sheets e' il backend primario."""
    return str(data_backend or "").strip().lower() == "sheets"


def install_scheduler_sheets_sync_policy() -> None:
    """Sostituisce solo il job periodico Sheets con un no-op su Supabase."""
    from app import scheduler as scheduler_module
    from app.config import settings

    scheduler = scheduler_module.scheduler
    if getattr(scheduler, "_sheets_sync_policy_installed", False):
        return

    original_add_job = scheduler.add_job

    def add_job_with_sheets_policy(
        func,
        trigger=None,
        args=None,
        kwargs=None,
        id=None,
        **options: Any,
    ):
        if id == "google_sheets_ledger_sync" and not automatic_sheets_sync_enabled(
            settings.DATA_BACKEND
        ):
            original_func = func

            @wraps(original_func)
            async def _skip_automatic_sheets_sync(*job_args, **job_kwargs):
                scheduler_module.logger.info(
                    "[SCHEDULER-SHEETS] full-sync automatico disabilitato: "
                    "Supabase e' il backend primario; export Sheets disponibile manualmente"
                )
                return {
                    "status": "disabled",
                    "reason": "supabase_primary_backend",
                }

            func = _skip_automatic_sheets_sync

        return original_add_job(
            func,
            trigger,
            args=args,
            kwargs=kwargs,
            id=id,
            **options,
        )

    scheduler.add_job = add_job_with_sheets_policy
    scheduler._sheets_sync_policy_installed = True
