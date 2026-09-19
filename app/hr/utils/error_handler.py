"""Gestione uniforme degli errori nelle rotte — re-export del modulo unico.

La logica vive in `app.utils.error_handler`. Fino al 19/09/2026 qui c'era una copia
**identica byte a byte** al lato ERP: nessuna divergenza da classificare,
solo due file da tenere allineati a mano.

Un modulo che non contiene logica non puo' divergere: e' questo il punto del
re-export. Il fork `app/hr` non nasceva per avere due comportamenti, ma per
avere due percorsi di import, e quelli restano.
"""
from app.utils.error_handler import (  # noqa: F401
    APIResponse,
    handle_errors,
    handle_errors_sync,
)

__all__ = [
    "APIResponse",
    "handle_errors",
    "handle_errors_sync",
]
