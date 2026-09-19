"""Audit log HR — re-export del modulo unico.

La logica vive in `app/services/audit_logger.py`. Fino al 19/09/2026 qui c'era
una copia identica nel comportamento: le sole differenze erano il percorso di
import nell'esempio della docstring, la terminologia di due righe di commento
(«MongoDB» invece di «Sheets», resto di una migrazione gia' fatta) e l'assenza
di `log_sicurezza`, la scorciatoia per gli eventi di login e le operazioni
distruttive. Nessuna divergenza da classificare: una copia era semplicemente
piu' povera.

Con il re-export `log_sicurezza` diventa disponibile anche al ramo HR, dove
`routers/pin_login.py` registra gli accessi con PIN: oggi passa da `log_evento`
a mano, domani puo' usarla.
"""
from app.services.audit_logger import (  # noqa: F401
    COLL_AUDIT_LOG,
    get_audit_per_modulo,
    get_storia_entita,
    log_evento,
    log_sicurezza,
)

__all__ = [
    "COLL_AUDIT_LOG",
    "get_audit_per_modulo",
    "get_storia_entita",
    "log_evento",
    "log_sicurezza",
]
