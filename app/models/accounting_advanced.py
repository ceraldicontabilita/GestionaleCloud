"""
Accounting Entries Models - Prima Nota, IVA, F24, Bilanci
Models per gestione contabile avanzata
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date as date_type
from enum import Enum


class EntryType(str, Enum):
    """Tipo di registrazione contabile."""
    OPENING = "opening"  # Apertura
    ORDINARY = "ordinary"  # Ordinaria
    ADJUSTMENT = "adjustment"  # Rettifica
    CLOSING = "closing"  # Chiusura


class AccountingEntryLine(BaseModel):
    """Riga di registrazione in prima nota."""
    account_id: str = Field(..., description="ID del conto")
    account_code: str = Field(..., description="Codice conto")
    account_name: str = Field(..., description="Nome conto")
    debit: float = Field(default=0.0, description="Dare")
    credit: float = Field(default=0.0, description="Credito")
    description: Optional[str] = Field(None, description="Descrizione riga")


class AccountingEntryCreate(BaseModel):
    """Create accounting entry."""
    date: date_type = Field(..., description="Data registrazione")
    entry_type: EntryType = Field(default=EntryType.ORDINARY)
    description: str = Field(..., min_length=3, description="Descrizione registrazione")
    document_number: Optional[str] = Field(None, description="Numero documento")
    document_date: Optional[date_type] = Field(None, description="Data documento")
    lines: List[AccountingEntryLine] = Field(..., min_items=2, description="Righe registrazione")
    notes: Optional[str] = Field(None, description="Note")
    
    model_config = ConfigDict(use_enum_values=True)


class AccountingEntryUpdate(BaseModel):
    """Update accounting entry."""
    date: Optional[date_type] = None
    entry_type: Optional[EntryType] = None
    description: Optional[str] = Field(None, min_length=3)
    document_number: Optional[str] = None
    document_date: Optional[date_type] = None
    lines: Optional[List[AccountingEntryLine]] = Field(None, min_items=2)
    notes: Optional[str] = None
    
    model_config = ConfigDict(use_enum_values=True)


class AccountingEntryResponse(BaseModel):
    """Accounting entry response."""
    id: str
    date: date_type
    entry_type: str
    description: str
    document_number: Optional[str]
    document_date: Optional[date_type]
    lines: List[AccountingEntryLine]
    total_debit: float
    total_credit: float
    balanced: bool
    notes: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# IVA Models

class VATType(str, Enum):
    """Tipo IVA."""
    DEDUCTIBLE = "deductible"  # Detraibile
    PAYABLE = "payable"  # A debito
    NON_DEDUCTIBLE = "non_deductible"  # Indetraibile


class VATRate(BaseModel):
    """Aliquota IVA."""
    rate: float = Field(..., description="Aliquota %")
    taxable: float = Field(..., description="Imponibile")
    vat_amount: float = Field(..., description="Importo IVA")


class VATLiquidation(BaseModel):
    """Liquidazione IVA."""
    quarter: int = Field(..., ge=1, le=4, description="Trimestre")
    year: int = Field(..., description="Anno")
    vat_deductible: float = Field(default=0.0, description="IVA detraibile")
    vat_payable: float = Field(default=0.0, description="IVA a debito")
    vat_balance: float = Field(..., description="Saldo IVA")
    previous_credit: float = Field(default=0.0, description="Credito precedente")
    to_pay: float = Field(..., description="IVA da versare")
    payment_date: Optional[date_type] = Field(None, description="Data pagamento")
    paid: bool = Field(default=False, description="Pagato")
    notes: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class VATRegistryEntry(BaseModel):
    """Registrazione registro IVA."""
    date: date_type
    document_number: str
    supplier_name: str
    taxable: float
    vat_rate: float
    vat_amount: float
    total: float
    vat_type: VATType
    deductible: bool
    invoice_id: Optional[str] = None


# F24 Models

class F24TributeCode(str, Enum):
    """Codici tributo F24."""
    IVA_6001 = "6001"  # IVA mensile
    IVA_6002 = "6002"  # IVA trimestrale
    INPS = "inps"
    IRPEF = "irpef"
    IRAP = "irap"
    IMU = "imu"


class F24Tribute(BaseModel):
    """Tributo F24."""
    code: F24TributeCode
    description: str
    amount: float = Field(..., gt=0)
    debit_account: Optional[str] = None
    
    model_config = ConfigDict(use_enum_values=True)


class F24Create(BaseModel):
    """Create F24."""
    reference_month: int = Field(..., ge=1, le=12, description="Mese riferimento")
    reference_year: int = Field(..., description="Anno riferimento")
    payment_date: date_type = Field(..., description="Data pagamento")
    tributes: List[F24Tribute] = Field(..., min_items=1)
    total_amount: float = Field(..., gt=0)
    paid: bool = Field(default=False)
    payment_reference: Optional[str] = None
    notes: Optional[str] = None


class F24Update(BaseModel):
    """Update F24."""
    payment_date: Optional[date_type] = None
    paid: Optional[bool] = None
    payment_reference: Optional[str] = None
    notes: Optional[str] = None


class F24Response(BaseModel):
    """F24 response."""
    id: str
    reference_month: int
    reference_year: int
    payment_date: date_type
    tributes: List[F24Tribute]
    total_amount: float
    paid: bool
    payment_reference: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Balance Sheet Models

class BalanceSheetSection(str, Enum):
    """Sezioni bilancio."""
    ASSETS = "assets"  # Attivo
    LIABILITIES = "liabilities"  # Passivo
    EQUITY = "equity"  # Patrimonio netto
    REVENUE = "revenue"  # Ricavi
    EXPENSES = "expenses"  # Costi


class BalanceSheetItem(BaseModel):
    """Voce di bilancio."""
    account_code: str
    account_name: str
    section: BalanceSheetSection
    amount: float
    percentage: Optional[float] = None
    parent_account: Optional[str] = None
    
    model_config = ConfigDict(use_enum_values=True)


class BalanceSheet(BaseModel):
    """Bilancio."""
    year: int
    date: date_type
    assets_total: float
    liabilities_total: float
    equity_total: float
    revenue_total: float
    expenses_total: float
    net_profit: float
    items: List[BalanceSheetItem]
    generated_at: datetime


class TrialBalance(BaseModel):
    """Bilancio di verifica."""
    date: date_type
    accounts: List[Dict[str, Any]]
    total_debit: float
    total_credit: float
    balanced: bool
    generated_at: datetime


class ProfitLoss(BaseModel):
    """Conto economico."""
    year: int
    revenue: Dict[str, float]
    expenses: Dict[str, float]
    gross_profit: float
    operating_profit: float
    net_profit: float
    revenue_total: float
    expenses_total: float


class CashFlow(BaseModel):
    """Rendiconto finanziario."""
    year: int
    operating_activities: float
    investing_activities: float
    financing_activities: float
    net_cash_flow: float
    opening_cash: float
    closing_cash: float


# Account Linking Models

class InvoiceAccountLink(BaseModel):
    """Link fattura-conto."""
    invoice_id: str
    account_id: str
    amount: float
    notes: Optional[str] = None


class InvoiceAccountLinkResponse(BaseModel):
    """Invoice account link response."""
    id: str
    invoice_id: str
    invoice_number: str
    account_id: str
    account_code: str
    account_name: str
    amount: float
    notes: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
