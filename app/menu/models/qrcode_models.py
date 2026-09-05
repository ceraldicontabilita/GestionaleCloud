from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class WiFiConfig(BaseModel):
    ssid: str
    password: str
    security: str = "WPA"  # WPA, WEP, or nopass
    hidden: bool = False

class QRCodeConfig(BaseModel):
    id: str = "qrcode_config"
    menu_url: str
    wifi: WiFiConfig
    updated_at: datetime = None
    updated_by: str = "admin"

class QRCodeConfigUpdate(BaseModel):
    menu_url: Optional[str] = None
    wifi: Optional[WiFiConfig] = None

class AdminPinLogin(BaseModel):
    pin: str

class AdminLoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str
