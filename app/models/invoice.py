"""
Invoice models for passive invoices (FatturaPA XML).
Pydantic schemas for invoice management.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date as date_type


class Product(BaseModel):
    """Product/item in an invoice."""
    descrizione: str = Field(..., description="Product description")
    quantita: float = Field(..., gt=0, description="Quantity")
    prezzo_unitario: float = Field(..., description="Unit price")
    iva: float = Field(..., ge=0, le=100, description="VAT percentage")
    totale: Optional[float] = Field(None, description="Line total")
    unita_misura: Optional[str] = Field(None, description="Unit of measure")
    codice_articolo: Optional[str] = Field(None, description="Product code")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "descrizione": "Farina tipo 00",
                "quantita": 25.0,
                "prezzo_unitario": 0.85,
                "iva": 10.0,
                "totale": 21.25,
                "unita_misura": "KG"
            }
        }
    )


class Invoice(BaseModel):
    """Invoice document (passive invoice from supplier)."""
    id: Optional[str] = Field(None, alias="_id")
    filename: str
    supplier_name: str
    supplier_vat: str
    supplier_address: Optional[str] = None
    supplier_email: Optional[str] = None
    
    invoice_number: str
    invoice_date: date_type
    due_date: Optional[date_type] = None
    month_year: str = Field(..., description="Format: MM-YYYY")
    
    total_amount: float = Field(..., ge=0)
    total_iva: float = Field(..., ge=0)
    total_imponibile: float = Field(..., ge=0)
    
    products: List[Product] = Field(default_factory=list)
    
    status: str = Field(default="active", description="active, archived, deleted")
    payment_method: Optional[str] = Field(None, description="cassa, banca, misto")
    payment_status: str = Field(default="unpaid", description="unpaid, partial, paid")
    amount_paid: float = Field(default=0.0, ge=0)
    
    check_number: Optional[str] = None
    
    xml_content: Optional[str] = Field(None, description="Original XML content")
    content_hash: Optional[str] = Field(None, description="Hash for duplicate detection")
    
    user_id: str = Field(default="admin")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    
    bank_reconciled: bool = Field(default=False)
    bank_transaction_id: Optional[str] = None
    
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "filename": "IT01234567890_001.xml",
                "supplier_name": "Molino Grassi SPA",
                "supplier_vat": "01234567890",
                "invoice_number": "FAT-2024-001",
                "invoice_date": "2024-01-15",
                "month_year": "01-2024",
                "total_amount": 1230.50,
                "total_iva": 112.50,
                "total_imponibile": 1118.00,
                "payment_method": "banca",
                "status": "active"
            }
        }
    )


class InvoiceCreate(BaseModel):
    """Invoice creation request."""
    filename: str
    supplier_name: str
    supplier_vat: str
    invoice_number: str
    invoice_date: date_type
    total_amount: float
    total_iva: float
    total_imponibile: float
    products: List[Product]
    xml_content: Optional[str] = None
    payment_method: Optional[str] = None


class InvoiceUpdate(BaseModel):
    """Invoice update request."""
    status: Optional[str] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    amount_paid: Optional[float] = None
    check_number: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class InvoiceResponse(BaseModel):
    """Invoice response with computed fields."""
    id: str
    filename: str
    supplier_name: str
    supplier_vat: str
    invoice_number: str
    invoice_date: date_type
    month_year: str
    total_amount: float
    total_iva: float
    total_imponibile: float
    status: str
    payment_method: Optional[str]
    payment_status: str
    amount_paid: float
    remaining_amount: float = Field(..., description="Computed: total_amount - amount_paid")
    uploaded_at: datetime
    products_count: int = Field(..., description="Number of products in invoice")


class PaginatedInvoicesResponse(BaseModel):
    """Paginated invoices response."""
    invoices: List[InvoiceResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class InvoiceStats(BaseModel):
    """Invoice statistics."""
    total_invoices: int
    total_amount: float
    total_paid: float
    total_unpaid: float
    by_status: Dict[str, int]
    by_payment_method: Dict[str, int]
    by_month: Dict[str, float]


class InvoiceMetadata(BaseModel):
    """Invoice metadata for additional information."""
    id: Optional[str] = Field(None, alias="_id")
    invoice_id: str
    user_id: str
    
    category: Optional[str] = None
    chart_of_account_id: Optional[str] = None
    chart_of_account_name: Optional[str] = None
    
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)


# Invoice Metadata Models

class InvoiceMetadataField(BaseModel):
    """Campo metadata personalizzato."""
    field_name: str = Field(..., description="Nome campo")
    field_type: str = Field(..., description="Tipo: text, number, date, boolean")
    field_value: Any = Field(..., description="Valore campo")
    required: bool = Field(default=False, description="Campo obbligatorio")


class InvoiceMetadataCreate(BaseModel):
    """Create invoice metadata."""
    invoice_id: str = Field(..., description="ID fattura")
    metadata_fields: List[InvoiceMetadataField] = Field(..., description="Campi metadata")
    template_name: Optional[str] = Field(None, description="Nome template")


class InvoiceMetadataTemplate(BaseModel):
    """Template metadata."""
    template_name: str = Field(..., min_length=3, description="Nome template")
    description: Optional[str] = Field(None, description="Descrizione")
    fields: List[InvoiceMetadataField] = Field(..., min_items=1, description="Campi template")
    apply_to_supplier: Optional[str] = Field(None, description="Applica automaticamente a fornitore")


class InvoiceMetadataResponse(BaseModel):
    """Metadata response."""
    id: str
    invoice_id: str
    invoice_number: str
    metadata_fields: List[InvoiceMetadataField]
    template_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
