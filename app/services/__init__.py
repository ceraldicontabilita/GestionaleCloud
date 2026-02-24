"""
Services package.
Business logic layer for all operations.

ARCHITETTURA:
- business_rules.py: Regole di business centralizzate e validazioni
- invoice_service_v2.py: Gestione fatture con controlli sicurezza
- corrispettivi_service.py: Gestione corrispettivi con propagazione Prima Nota
- *_service.py: Altri servizi specifici
"""
from .auth_service import AuthService
# from .invoice_service import InvoiceService  # DEPRECATO — usare InvoiceServiceV2
from .invoice_service_v2 import InvoiceServiceV2, get_invoice_service_v2
# from .supplier_service import SupplierService  # DEPRECATO — usare SupplierServiceV2
from .warehouse_service import WarehouseService
from .accounting_service import AccountingService
from .accounting_entries_service import AccountingEntriesService
from .employee_service import EmployeeService
from .cash_service import CashService
from .bank_service import BankService
from .chart_service import ChartOfAccountsService
from .email_service import EmailService
from .business_rules import BusinessRules, ValidationResult, DataFlowManager
from .corrispettivi_service import CorrispettiviService, get_corrispettivi_service

from .data_propagation import DataPropagationService, get_propagation_service

__all__ = [
    # Core Services
    "AuthService",
    # "InvoiceService",  # DEPRECATO
    "InvoiceServiceV2",
    "get_invoice_service_v2",
    # "SupplierService",  # DEPRECATO
    "WarehouseService",
    "AccountingService",
    "AccountingEntriesService",
    "EmployeeService",
    "CashService",
    "BankService",
    "ChartOfAccountsService",
    "EmailService",
    # V2 Services with Security
    "CorrispettiviService",
    "get_corrispettivi_service",
    # Propagation
    "DataPropagationService",
    "get_propagation_service",
    # Business Rules
    "BusinessRules",
    "ValidationResult",
    "DataFlowManager"
]
