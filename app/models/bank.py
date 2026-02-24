"""
Bank models.
Bank statements, reconciliation, and checks (assegni) management.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, date as date_type


class BankStatement(BaseModel):
    """Bank statement transaction."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Transaction details
    date: date_type = Field(..., description="Transaction date")
    value_date: Optional[date_type] = Field(None, description="Value date (data valuta)")
    
    description: str = Field(..., description="Transaction description")
    amount: float = Field(..., description="Amount (positive=credit, negative=debit)")
    balance: Optional[float] = Field(None, description="Balance after transaction")
    
    # Transaction ID
    transaction_id: Optional[str] = Field(
        None,
        description="Bank transaction ID"
    )
    
    # Reconciliation
    reconciled: bool = Field(default=False, description="Whether reconciled")
    invoice_id: Optional[str] = Field(None, description="Linked invoice ID")
    reconciled_at: Optional[datetime] = None
    
    # Category
    category: Optional[str] = Field(None, description="Transaction category")
    
    # Notes
    notes: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class BankStatementCreate(BaseModel):
    """Bank statement creation request."""
    
    date: date_type
    value_date: Optional[date_type] = None
    description: str = Field(..., min_length=1)
    amount: float
    balance: Optional[float] = None
    transaction_id: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None


class BankStatementUpdate(BaseModel):
    """Bank statement update request."""
    
    description: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = None
    notes: Optional[str] = None


class BankReconcile(BaseModel):
    """Bank reconciliation request."""
    
    statement_id: str
    invoice_id: str


class Assegno(BaseModel):
    """Assegno (check) record."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Check details
    number: str = Field(..., description="Check number")
    date: date_type = Field(..., description="Check date")
    amount: float = Field(..., ge=0, description="Check amount")
    
    # Parties
    payee: str = Field(..., description="Payee (beneficiario)")
    bank: Optional[str] = Field(None, description="Issuing bank")
    
    # Status
    status: str = Field(
        default="emesso",
        description="Status: emesso, incassato, annullato"
    )
    
    # Dates
    issue_date: Optional[date_type] = Field(None, description="Issue date")
    cash_date: Optional[date_type] = Field(None, description="Date cashed")
    
    # Reference
    invoice_id: Optional[str] = Field(None, description="Related invoice")
    
    # Notes
    notes: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class AssegnoCreate(BaseModel):
    """Assegno creation request."""
    
    number: str = Field(..., min_length=1)
    date: date_type
    amount: float = Field(..., ge=0)
    payee: str = Field(..., min_length=1)
    bank: Optional[str] = None
    issue_date: Optional[date_type] = None
    invoice_id: Optional[str] = None
    notes: Optional[str] = None


class AssegnoUpdate(BaseModel):
    """Assegno update request."""
    
    status: Optional[str] = Field(
        None,
        pattern="^(emesso|incassato|annullato)$"
    )
    cash_date: Optional[date_type] = None
    notes: Optional[str] = None


class AssegnoResponse(BaseModel):
    """Assegno response model."""
    
    id: str
    number: str
    date: date_type
    amount: float
    payee: str
    bank: Optional[str]
    status: str
    issue_date: Optional[date_type]
    cash_date: Optional[date_type]
    invoice_id: Optional[str]
    created_at: datetime
