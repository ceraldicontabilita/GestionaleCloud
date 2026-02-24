"""
Supplier models.
Pydantic schemas for supplier management.
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


class SupplierBase(BaseModel):
    """Base supplier fields."""
    vat_number: str = Field(..., description="Partita IVA")
    name: str = Field(..., min_length=1)
    fiscal_code: Optional[str] = Field(None, description="Codice Fiscale")
    
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = Field(default="IT")
    
    email: Optional[EmailStr] = None
    pec: Optional[EmailStr] = Field(None, description="PEC email")
    phone: Optional[str] = None
    mobile: Optional[str] = None
    website: Optional[str] = None
    
    payment_method: Optional[str] = Field(None, description="cassa, banca, misto, assegno")
    payment_terms_days: Optional[int] = Field(None, ge=0, description="Payment terms in days")
    
    bank_iban: Optional[str] = None
    bank_name: Optional[str] = None
    
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    is_active: bool = Field(default=True)


class Supplier(SupplierBase):
    """Supplier document in database."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    # Statistics (computed/cached)
    total_invoices: int = Field(default=0)
    total_amount: float = Field(default=0.0)
    last_invoice_date: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "vat_number": "01234567890",
                "name": "Molino Grassi SPA",
                "address": "Via Roma 123",
                "city": "Parma",
                "province": "PR",
                "postal_code": "43100",
                "email": "info@molinograssi.it",
                "phone": "+39 0521 123456",
                "payment_method": "banca",
                "payment_terms_days": 60,
                "is_active": True
            }
        }
    )


class SupplierCreate(SupplierBase):
    """Supplier creation request."""
    pass


class SupplierUpdate(BaseModel):
    """Supplier update request."""
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    email: Optional[EmailStr] = None
    pec: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    website: Optional[str] = None
    payment_method: Optional[str] = None
    payment_terms_days: Optional[int] = None
    bank_iban: Optional[str] = None
    bank_name: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class SupplierResponse(BaseModel):
    """Supplier response."""
    id: str
    vat_number: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    city: Optional[str]
    payment_method: Optional[str]
    payment_terms_days: Optional[int]
    total_invoices: int
    total_amount: float
    last_invoice_date: Optional[datetime]
    is_active: bool


class SupplierStats(BaseModel):
    """Supplier statistics."""
    total_suppliers: int
    active_suppliers: int
    total_invoices: int
    total_amount: float
    by_payment_method: dict[str, int]
    top_suppliers: List[SupplierResponse]


class SupplierPaymentMethod(BaseModel):
    """Supplier payment method configuration."""
    id: Optional[str] = Field(None, alias="_id")
    supplier_vat: str
    user_id: str = Field(default="admin")
    
    payment_method: str = Field(..., description="cassa, banca, misto, assegno")
    default_bank_account: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)


class SupplierPaymentHistory(BaseModel):
    """Supplier payment history record."""
    id: Optional[str] = Field(None, alias="_id")
    supplier_vat: str
    supplier_name: str
    user_id: str = Field(default="admin")
    
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    
    payment_date: datetime
    amount: float = Field(..., gt=0)
    payment_method: str
    
    bank_transaction_id: Optional[str] = None
    check_number: Optional[str] = None
    
    notes: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "supplier_vat": "01234567890",
                "supplier_name": "Molino Grassi SPA",
                "payment_date": "2024-03-15T10:30:00",
                "amount": 1230.50,
                "payment_method": "bonifico",
                "notes": "Pagamento fattura FAT-2024-001"
            }
        }
    )
