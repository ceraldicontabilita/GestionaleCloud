from pydantic import BaseModel
from typing import Optional


class MenuUrlUpdate(BaseModel):
    """Nuovo indirizzo pubblico del menu clienti (quello del QR)."""
    url: str


class AdminPinLogin(BaseModel):
    pin: str


class AdminLoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str
