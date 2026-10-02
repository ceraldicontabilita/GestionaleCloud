"""
Services package.
Business logic layer for all operations.

ARCHITETTURA:
- business_rules.py: Regole di business centralizzate e validazioni
- corrispettivi_service.py: CSV AdE dei corrispettivi (dato provvisorio)
- *_service.py: Altri servizi specifici
"""
from .auth_service import AuthService
from .accounting_entries_service import AccountingEntriesService
from .cash_service import CashService
from .chart_service import ChartOfAccountsService
from .email_service import EmailService
from .business_rules import BusinessRules, ValidationResult, DataFlowManager

from .data_propagation import DataPropagationService, get_propagation_service


# Il package services viene inizializzato durante lo startup prima di
# ``app.scheduler.start_scheduler``. Installiamo qui la policy di coda: il
# lock resta globale e seriale, ma un job concorrente attende invece di essere
# perso fino alla ricorrenza successiva.
from .scheduler_queue_policy import install_scheduler_queue_policy

install_scheduler_queue_policy()


__all__ = [
    # Core Services
    "AuthService",
    "AccountingEntriesService",
    "CashService",
    "ChartOfAccountsService",
    "EmailService",
    # Propagation
    "DataPropagationService",
    "get_propagation_service",
    # Business Rules
    "BusinessRules",
    "ValidationResult",
    "DataFlowManager"
]
