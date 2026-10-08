"""
Warehouse and product management models.
Pydantic schemas for inventory and stock management.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date as date_type


class WarehouseProduct(BaseModel):
    """Product in warehouse with stock information."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    product_name: str
    product_description: Optional[str] = None
    product_code: Optional[str] = None
    
    unit_of_measure: str = Field(default="PZ", description="KG, L, PZ, CF, etc.")
    
    # Stock quantities
    quantity_purchased: float = Field(default=0.0, ge=0)
    quantity_used: float = Field(default=0.0, ge=0)
    quantity_available: float = Field(default=0.0, ge=0)
    
    # Reorder management
    minimum_stock: Optional[float] = Field(None, ge=0, description="Minimum stock level")
    optimal_stock: Optional[float] = Field(None, ge=0, description="Optimal stock level")
    
    # Accounting
    chart_of_account_id: Optional[str] = None
    chart_of_account_name: Optional[str] = None
    
    # Supplier information
    supplier_vat: str
    supplier_name: str
    primary_supplier: bool = Field(default=True)
    
    # Pricing
    unit_price_avg: float = Field(default=0.0, ge=0, description="Average purchase price")
    unit_price_min: float = Field(default=0.0, ge=0, description="Minimum purchase price")
    unit_price_max: float = Field(default=0.0, ge=0, description="Maximum purchase price")
    last_purchase_price: Optional[float] = Field(None, ge=0)
    
    # Dates
    last_purchase_date: Optional[date_type] = None
    last_movement_date: Optional[date_type] = None
    
    # Product details
    category: Optional[str] = None
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    
    # Storage location
    storage_location: Optional[str] = Field(None, description="Shelf, room, zone")
    
    # Lot tracking
    lot_tracking_enabled: bool = Field(default=False)
    current_lot: Optional[str] = None
    
    # Additional info
    barcode: Optional[str] = None
    ean: Optional[str] = None
    sku: Optional[str] = None
    
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    is_active: bool = Field(default=True)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "product_name": "Farina tipo 00",
                "product_code": "FAR-00-25KG",
                "unit_of_measure": "KG",
                "quantity_purchased": 500.0,
                "quantity_used": 250.0,
                "quantity_available": 250.0,
                "minimum_stock": 50.0,
                "supplier_vat": "01234567890",
                "supplier_name": "Molino Grassi",
                "unit_price_avg": 0.85,
                "category": "Ingredienti",
                "subcategory": "Farine"
            }
        }
    )


class WarehouseMovement(BaseModel):
    """Stock movement record."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    product_id: str = Field(..., description="Reference to warehouse product")
    product_name: str
    
    movement_type: str = Field(..., description="carico, scarico, rettifica, inventario, scadenza")
    quantity: float = Field(..., description="Positive for carico, negative for scarico")
    
    unit_of_measure: str
    unit_price: Optional[float] = Field(None, ge=0)
    total_value: Optional[float] = Field(None, ge=0)
    
    # Stock before/after
    quantity_before: float = Field(..., ge=0)
    quantity_after: float = Field(..., ge=0)
    
    # Source document
    document_type: Optional[str] = Field(None, description="fattura, ddт, ordine, manuale")
    document_id: Optional[str] = None
    document_number: Optional[str] = None
    invoice_id: Optional[str] = None
    
    # Supplier/customer
    supplier_vat: Optional[str] = None
    supplier_name: Optional[str] = None
    
    # Lot tracking
    lot_number: Optional[str] = None
    expiry_date: Optional[date_type] = None
    
    # Movement details
    movement_date: datetime = Field(default_factory=datetime.utcnow)
    reason: Optional[str] = Field(None, description="Reason for movement")
    notes: Optional[str] = None
    
    # Audit
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "product_name": "Farina tipo 00",
                "movement_type": "carico",
                "quantity": 25.0,
                "unit_of_measure": "KG",
                "unit_price": 0.85,
                "quantity_before": 200.0,
                "quantity_after": 225.0,
                "document_type": "fattura",
                "supplier_name": "Molino Grassi"
            }
        }
    )


class ProductCatalog(BaseModel):
    """Product catalog entry."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    product_name: str
    product_code: Optional[str] = None
    description: Optional[str] = None
    
    category: Optional[str] = None
    subcategory: Optional[str] = None
    
    unit_of_measure: str = Field(default="PZ")
    
    # Pricing
    cost_price: Optional[float] = Field(None, ge=0)
    selling_price: Optional[float] = Field(None, ge=0)
    vat_rate: float = Field(default=22.0, ge=0, le=100)
    
    # Supplier
    preferred_supplier_vat: Optional[str] = None
    preferred_supplier_name: Optional[str] = None
    
    # Product details
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    
    barcode: Optional[str] = None
    ean: Optional[str] = None
    sku: Optional[str] = None
    
    # Flags
    is_active: bool = Field(default=True)
    is_sellable: bool = Field(default=True)
    is_purchasable: bool = Field(default=True)
    
    tags: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)


class PriceHistoryEntry(BaseModel):
    """Price history entry for a product."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    product_name: str
    supplier_vat: str
    supplier_name: str
    
    price: float = Field(..., gt=0)
    unit_of_measure: str
    quantity: Optional[float] = None
    
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date_type] = None
    
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "product_name": "Farina tipo 00",
                "supplier_vat": "01234567890",
                "supplier_name": "Molino Grassi",
                "price": 0.85,
                "unit_of_measure": "KG",
                "quantity": 25.0,
                "invoice_date": "2024-01-15"
            }
        }
    )


class ProductMapping(BaseModel):
    """Product name mapping for standardization."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    original_name: str = Field(..., description="Original product name from invoice")
    standard_name: str = Field(..., description="Standardized product name")
    
    supplier_vat: Optional[str] = None
    category: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)


class InventorySnapshot(BaseModel):
    """Inventory snapshot at a point in time."""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(default="admin")
    
    snapshot_date: datetime = Field(default_factory=datetime.utcnow)
    snapshot_type: str = Field(default="periodic", description="periodic, year_end, spot_check")
    
    products: List[Dict[str, Any]] = Field(default_factory=list)
    
    total_items: int = Field(default=0)
    total_value: float = Field(default=0.0, ge=0)
    
    notes: Optional[str] = None
    
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(populate_by_name=True)


class StockAlert(BaseModel):
    """Stock alert for low inventory."""
    product_id: str
    product_name: str
    current_quantity: float
    minimum_stock: float
    suggested_order_quantity: float
    supplier_name: str
    alert_level: str = Field(..., description="low, critical, out_of_stock")
