"""
Schemi Pydantic condivisi tra i vari moduli.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone
import uuid


# ==================== BASE MODELS ====================

class BaseModelWithId(BaseModel):
    """Modello base con ID e timestamp"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None


class ResponseMessage(BaseModel):
    """Risposta standard per operazioni"""
    success: bool = True
    message: str
    data: Optional[dict] = None


class PaginatedResponse(BaseModel):
    """Risposta paginata standard"""
    items: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== ENUMS / CONSTANTS ====================

# Unità di misura
UNITA_MISURA = {
    "pz": "Pezzi",
    "kg": "Kilogrammi",
    "g": "Grammi",
    "l": "Litri",
    "ml": "Millilitri",
    "conf": "Confezioni"
}

# Tipi di frigorifero
TIPI_FRIGORIFERO = {
    "frigo": {"nome": "Frigorifero", "temp_min": 0, "temp_max": 4},
    "congelatore": {"nome": "Congelatore", "temp_min": -22, "temp_max": -18},
    "abbattitore": {"nome": "Abbattitore", "temp_min": -40, "temp_max": -18},
    "cella": {"nome": "Cella frigorifera", "temp_min": 0, "temp_max": 4}
}

# Stati non conformità
STATI_NON_CONFORMITA = ["aperto", "in_gestione", "chiuso"]

# Frequenze sanificazione
FREQUENZE_SANIFICAZIONE = ["giornaliera", "settimanale", "mensile", "straordinaria"]
