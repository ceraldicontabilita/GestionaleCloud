from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class SalaBase(BaseModel):
    nome: str
    ordini_abilitati: bool = True
    coperto_attivo: bool = False
    coperto_importo: float = 0
    disabilita_contanti_qr: bool = False


class SalaCreate(SalaBase):
    pass


class SalaUpdate(BaseModel):
    nome: Optional[str] = None
    ordini_abilitati: Optional[bool] = None
    coperto_attivo: Optional[bool] = None
    coperto_importo: Optional[float] = None
    disabilita_contanti_qr: Optional[bool] = None


class Sala(SalaBase):
    id: str = Field(default_factory=new_id)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
