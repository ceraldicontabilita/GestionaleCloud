"""Modelli del modulo Menu (stessi campi dell'API della vecchia app Menu, in
camelCase verso il frontend e snake_case nel registro)."""
from typing import List, Optional

from pydantic import BaseModel

ORDER_STATUSES = ["nuovo", "in_corso", "pronto", "completato", "annullato"]
ORDER_SOURCES = ["cliente", "cassa"]
MOVEMENT_TYPES = ["carico", "scarico", "rettifica"]


class CategoryCreate(BaseModel):
    name: str
    nameIT: str
    image: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    image: Optional[str] = None


class SubcategoryCreate(BaseModel):
    name: str
    nameIT: str
    image: Optional[str] = None
    category_id: int


class SubcategoryUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    image: Optional[str] = None


class ProductCreate(BaseModel):
    name: str
    nameIT: str
    price: str
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: List[str] = []
    image: Optional[str] = None
    category_id: int
    subcategory_id: int


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: Optional[List[str]] = None
    image: Optional[str] = None


class OrderItem(BaseModel):
    product_id: Optional[int] = None
    name: str
    price: str
    quantity: int = 1
    note: Optional[str] = None


class OrderCreate(BaseModel):
    items: List[OrderItem]
    table: Optional[str] = None
    customer_name: Optional[str] = None
    note: Optional[str] = None
    source: str = "cliente"
    paid: bool = False
    payment_method: Optional[str] = None
    sala_id: Optional[str] = None
    numero_coperti: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: str


class OrderPaymentUpdate(BaseModel):
    paid: bool
    payment_method: Optional[str] = None


class SalaCreate(BaseModel):
    nome: str
    ordini_abilitati: bool = True
    coperto_attivo: bool = False
    coperto_importo: float = 0
    disabilita_contanti_qr: bool = False


class SalaUpdate(BaseModel):
    nome: Optional[str] = None
    ordini_abilitati: Optional[bool] = None
    coperto_attivo: Optional[bool] = None
    coperto_importo: Optional[float] = None
    disabilita_contanti_qr: Optional[bool] = None


class WiFiConfig(BaseModel):
    ssid: str
    password: str
    security: str = "WPA"
    hidden: bool = False


class QRCodeConfigUpdate(BaseModel):
    menu_url: Optional[str] = None
    wifi: Optional[WiFiConfig] = None


class WarehouseItemCreate(BaseModel):
    name: str
    unit: str = "pz"
    quantity: float = 0
    min_threshold: Optional[float] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    note: Optional[str] = None


class WarehouseItemUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    min_threshold: Optional[float] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    note: Optional[str] = None


class MovementCreate(BaseModel):
    type: str
    quantity: float
    note: Optional[str] = None


def compute_total(items: List[OrderItem]) -> float:
    total = 0.0
    for it in items:
        try:
            price = str(it.price).replace("€", "").strip().replace(",", ".")
            total += float(price) * it.quantity
        except (ValueError, TypeError):
            continue
    return round(total, 2)
