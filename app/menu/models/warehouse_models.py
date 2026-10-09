from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:12]


MOVEMENT_TYPES = ["carico", "scarico", "rettifica"]


class WarehouseItemBase(BaseModel):
    name: str
    unit: str = "pz"  # pz, kg, l, confezione...
    quantity: float = 0
    min_threshold: Optional[float] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    note: Optional[str] = None


class WarehouseItemCreate(WarehouseItemBase):
    pass


class WarehouseItemUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    min_threshold: Optional[float] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    note: Optional[str] = None


class WarehouseItem(WarehouseItemBase):
    id: str = Field(default_factory=new_id)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MovementCreate(BaseModel):
    type: str  # carico / scarico / rettifica
    quantity: float
    note: Optional[str] = None


class Movement(BaseModel):
    id: str = Field(default_factory=new_id)
    item_id: str
    item_name: str
    type: str
    quantity: float
    resulting_quantity: float
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
