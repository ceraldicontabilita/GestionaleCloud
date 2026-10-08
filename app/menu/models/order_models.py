from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# Stato di un ordine, in ordine di avanzamento naturale
ORDER_STATUSES = ["nuovo", "in_corso", "pronto", "completato", "annullato"]

# Da dove arriva l'ordine: cliente da tavolo (menu digitale) o operatore al banco
ORDER_SOURCES = ["cliente", "cassa"]


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
    payment_method: Optional[str] = None  # contanti / pos / satispay ecc.
    sala_id: Optional[str] = None
    numero_coperti: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: str


class OrderPaymentUpdate(BaseModel):
    paid: bool
    payment_method: Optional[str] = None


class Order(BaseModel):
    id: str = Field(default_factory=new_id)
    items: List[OrderItem]
    table: Optional[str] = None
    customer_name: Optional[str] = None
    note: Optional[str] = None
    source: str = "cliente"
    status: str = "nuovo"
    paid: bool = False
    payment_method: Optional[str] = None
    total: float = 0.0
    sala_id: Optional[str] = None
    sala_nome: Optional[str] = None
    numero_coperti: Optional[int] = None
    totale_coperto: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def compute_total(items: List[OrderItem]) -> float:
    total = 0.0
    for it in items:
        try:
            # i prezzi nel menu sono stringhe tipo "3,50" o "3.50"
            price_str = str(it.price).replace("€", "").strip().replace(",", ".")
            total += float(price_str) * it.quantity
        except (ValueError, TypeError):
            continue
    return round(total, 2)
