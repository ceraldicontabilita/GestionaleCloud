"""
Repository package.
Provides data access layer for all entities.
"""
from .base_repository import BaseRepository
from .user_repository import UserRepository
from .invoice_repository import InvoiceRepository
from .supplier_repository import SupplierRepository
from .warehouse_repository import WarehouseRepository, WarehouseMovementRepository
from .temperature_repository import TemperatureRepository, EquipmentRepository
from .employee_repository import (
    EmployeeRepository,
    PayslipRepository,
    LibrettoSanitarioRepository
)
from .cash_repository import (
    CashMovementRepository,
    CorrissettivoRepository
)

__all__ = [
    "BaseRepository",
    "UserRepository",
    "InvoiceRepository",
    "SupplierRepository",
    "WarehouseRepository",
    "WarehouseMovementRepository",
    "TemperatureRepository",
    "EquipmentRepository",
    "EmployeeRepository",
    "PayslipRepository",
    "LibrettoSanitarioRepository",
    "CashMovementRepository",
    "CorrissettivoRepository",
]
from .bank_repository import (
    BankStatementRepository,
    AssegnoRepository
)
from .chart_repository import ChartOfAccountsRepository
