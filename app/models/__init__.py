"""
Models package.
Pydantic schemas for all entities.
"""
from .user import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserInDB,
    UserResponse,
    UserUpdate,
    PasswordChange
)

from .invoice import (
    Product,
    Invoice,
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    PaginatedInvoicesResponse,
    InvoiceStats,
    InvoiceMetadata
)

from .supplier import (
    Supplier,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    SupplierStats,
    SupplierPaymentMethod,
    SupplierPaymentHistory
)

from .warehouse import (
    WarehouseProduct,
    WarehouseMovement,
    ProductCatalog,
    PriceHistoryEntry,
    ProductMapping,
    InventorySnapshot,
    StockAlert
)

from .employee import (
    Employee,
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    Payslip,
    PayslipCreate,
    PayslipResponse,
    LibrettoSanitario,
    LibrettoSanitarioCreate,
    LibrettoSanitarioUpdate,
    LibrettoSanitarioResponse,
    EmployeeStats
)

from .cash import (
    CashMovement,
    CashMovementCreate,
    CashMovementUpdate,
    CashMovementResponse,
    Corrispettivo,
    CorrissettivoCreate,
    CorrissettivoUpdate,
    CorrissettivoResponse,
    CashStats
)

__all__ = [
    # User models
    "UserRegister",
    "UserLogin",
    "TokenResponse",
    "UserInDB",
    "UserResponse",
    "UserUpdate",
    "PasswordChange",
    
    # Invoice models
    "Product",
    "Invoice",
    "InvoiceCreate",
    "InvoiceUpdate",
    "InvoiceResponse",
    "PaginatedInvoicesResponse",
    "InvoiceStats",
    "InvoiceMetadata",
    
    # Supplier models
    "Supplier",
    "SupplierCreate",
    "SupplierUpdate",
    "SupplierResponse",
    "SupplierStats",
    "SupplierPaymentMethod",
    "SupplierPaymentHistory",
    
    # Warehouse models
    "WarehouseProduct",
    "WarehouseMovement",
    "ProductCatalog",
    "PriceHistoryEntry",
    "ProductMapping",
    "InventorySnapshot",
    "StockAlert",
    
    # Employee models
    "Employee",
    "EmployeeCreate",
    "EmployeeUpdate",
    "EmployeeResponse",
    "Payslip",
    "PayslipCreate",
    "PayslipResponse",
    "LibrettoSanitario",
    "LibrettoSanitarioCreate",
    "LibrettoSanitarioUpdate",
    "LibrettoSanitarioResponse",
    "EmployeeStats",
    
    # Cash models
    "CashMovement",
    "CashMovementCreate",
    "CashMovementUpdate",
    "CashMovementResponse",
    "Corrispettivo",
    "CorrissettivoCreate",
    "CorrissettivoUpdate",
    "CorrissettivoResponse",
    "CashStats",
]

from .bank import (
    BankStatement,
    BankStatementCreate,
    BankStatementUpdate,
    BankReconcile,
    Assegno,
    AssegnoCreate,
    AssegnoUpdate,
    AssegnoResponse
)

from .accounting_extended import (
    ChartOfAccount,
    ChartOfAccountCreate,
    ChartOfAccountUpdate
)
