"""
Cash models.
Cash register management, movements, and daily closures (corrispettivi).
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, date as date_type


class CashMovement(BaseModel):
    """Cash register movement (entry or exit)."""
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Date and time
    date: date_type = Field(..., description="Movement date")
    time: str = Field(..., description="Time in HH:MM format")
    
    # Type and amount
    type: str = Field(
        ...,
        description="Movement type: entrata (in) or uscita (out)"
    )
    amount: float = Field(..., ge=0, description="Amount in euros")
    
    # Description
    description: str = Field(..., description="Movement description")
    category: Optional[str] = Field(
        None,
        description="Category: vendita, spese, prelievo, versamento, etc."
    )
    
    # Payment method
    payment_method: Optional[str] = Field(
        None,
        description="Payment method: contanti, carta, assegno"
    )
    
    # Reference
    reference_number: Optional[str] = Field(
        None,
        description="Receipt/invoice number if applicable"
    )
    
    # Notes
    notes: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class CashMovementCreate(BaseModel):
    """Cash movement creation request."""
    
    date: date_type
    time: str = Field(..., description="HH:MM format")
    type: str = Field(..., pattern="^(entrata|uscita)$")
    amount: float = Field(..., ge=0)
    description: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class CashMovementUpdate(BaseModel):
    """Cash movement update request."""
    
    amount: Optional[float] = Field(None, ge=0)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class CashMovementResponse(BaseModel):
    """Cash movement response model."""
    
    id: str
    user_id: str
    date: date_type
    time: str
    type: str
    amount: float
    description: str
    category: Optional[str]
    payment_method: Optional[str]
    reference_number: Optional[str]
    notes: Optional[str]
    created_at: datetime


class Corrispettivo(BaseModel):
    """
    Corrispettivo (daily cash register closure).
    Required for Italian tax compliance.
    """
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Date
    date: date_type = Field(..., description="Closure date")
    
    # Totals by payment method
    total_cash: float = Field(
        default=0,
        ge=0,
        description="Total cash payments (contanti)"
    )
    total_card: float = Field(
        default=0,
        ge=0,
        description="Total card payments (carte)"
    )
    total_other: float = Field(
        default=0,
        ge=0,
        description="Other payment methods"
    )
    
    # Summary
    total_receipts: int = Field(
        default=0,
        ge=0,
        description="Number of receipts issued"
    )
    total_amount: float = Field(
        default=0,
        ge=0,
        description="Total amount (sum of all payment methods)"
    )
    
    # Cash drawer
    opening_balance: Optional[float] = Field(
        None,
        ge=0,
        description="Opening cash balance"
    )
    closing_balance: Optional[float] = Field(
        None,
        ge=0,
        description="Closing cash balance (counted)"
    )
    expected_balance: Optional[float] = Field(
        None,
        description="Expected balance (opening + cash in - cash out)"
    )
    difference: Optional[float] = Field(
        None,
        description="Difference between closing and expected"
    )
    
    # Notes
    notes: Optional[str] = Field(None, description="Closure notes")
    
    # Status
    is_reconciled: bool = Field(
        default=False,
        description="Whether closure is reconciled"
    )
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)


class CorrissettivoCreate(BaseModel):
    """Corrispettivo creation request."""
    
    date: date_type
    total_cash: float = Field(default=0, ge=0)
    total_card: float = Field(default=0, ge=0)
    total_other: float = Field(default=0, ge=0)
    total_receipts: int = Field(default=0, ge=0)
    
    opening_balance: Optional[float] = Field(None, ge=0)
    closing_balance: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class CorrissettivoUpdate(BaseModel):
    """Corrispettivo update request."""
    
    total_cash: Optional[float] = Field(None, ge=0)
    total_card: Optional[float] = Field(None, ge=0)
    total_other: Optional[float] = Field(None, ge=0)
    total_receipts: Optional[int] = Field(None, ge=0)
    
    opening_balance: Optional[float] = Field(None, ge=0)
    closing_balance: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    is_reconciled: Optional[bool] = None


class CorrissettivoResponse(BaseModel):
    """Corrispettivo response model."""
    
    id: str
    date: date_type
    total_cash: float
    total_card: float
    total_other: float
    total_amount: float
    total_receipts: int
    opening_balance: Optional[float]
    closing_balance: Optional[float]
    expected_balance: Optional[float]
    difference: Optional[float]
    is_reconciled: bool
    created_at: datetime


class CashStats(BaseModel):
    """Cash register statistics."""
    
    total_in: float
    total_out: float
    current_balance: float
    movements_count: int
    by_category: dict
    by_payment_method: dict
    date_range: dict
