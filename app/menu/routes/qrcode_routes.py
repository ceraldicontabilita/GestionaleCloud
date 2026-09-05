from fastapi import APIRouter, HTTPException, Depends, Header, Request, status
from app.menu.models.qrcode_models import QRCodeConfig, QRCodeConfigUpdate, AdminPinLogin, AdminLoginResponse, WiFiConfig
from datetime import datetime, timedelta
import hashlib
import hmac
import os
import jwt
import qrcode
from io import BytesIO
import base64

from app.menu.supabase_client import supabase
from app.utils import login_lockout

CONFIG_ID = "qrcode_config"

router = APIRouter(prefix="/api/qrcode", tags=["QR Code Management"])

# Il Menu usa lo stesso PIN amministratore del gestionale principale.
# Il valore non viene mai salvato in chiaro nel repository: Render espone
# esclusivamente PIN_HASH_ADMIN (SHA-256 del PIN). MENU_JWT_SECRET/JWT_SECRET
# continua a firmare il token locale del Menu, così le rotte admin esistenti
# restano compatibili senza introdurre un secondo PIN.
SECRET_KEY = os.environ.get("MENU_JWT_SECRET") or os.environ.get("JWT_SECRET") or ""
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours
ADMIN_USERNAME = os.environ.get("MENU_ADMIN_USERNAME") or os.environ.get("ADMIN_USERNAME", "ceraldi")


def _verify_admin_pin(pin: str):
    pin_hash_admin = os.environ.get("PIN_HASH_ADMIN", "").strip().lower()
    if not pin_hash_admin:
        return None
    supplied_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
    return hmac.compare_digest(supplied_hash, pin_hash_admin)


def create_access_token(data: dict):
    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Login non configurato (MENU_JWT_SECRET mancante)")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Login non configurato (MENU_JWT_SECRET mancante)")

    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(login_data: AdminPinLogin, request: Request):
    """Accesso amministratore Menu tramite lo stesso PIN del gestionale."""
    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Login amministratore non configurato")

    ip = login_lockout.client_ip(request)
    lock_sec = login_lockout.seconds_locked(ip)
    if lock_sec > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Troppi tentativi, riprova tra {lock_sec}s",
        )

    pin = str(login_data.pin or "").strip()
    if not pin or not pin.isdigit() or len(pin) < 4 or len(pin) > 12:
        login_lockout.register_failure(ip)
        raise HTTPException(status_code=400, detail="PIN non valido")

    pin_ok = _verify_admin_pin(pin)
    if pin_ok is None:
        raise HTTPException(status_code=503, detail="PIN amministratore non configurato")

    if not pin_ok:
        login_lockout.register_failure(ip)
        return AdminLoginResponse(success=False, message="PIN non valido")

    login_lockout.clear_failures(ip)
    access_token = create_access_token(data={"sub": ADMIN_USERNAME, "auth_method": "pin"})
    return AdminLoginResponse(
        success=True,
        token=access_token,
        message="Accesso effettuato",
    )


def _get_config_row():
    res = supabase.table("menu_qrcode_config").select("*").eq("id", CONFIG_ID).limit(1).execute()
    return res.data[0] if res.data else None


@router.get("/config")
async def get_qrcode_config():
    """Get current QR code configuration (public endpoint)"""
    config = _get_config_row()

    if not config:
        default_config = {
            "id": CONFIG_ID,
            "menu_url": f"{os.environ.get('BACKEND_URL', 'http://localhost:3000')}",
            "wifi": {
                "ssid": "Ceraldi_Caffe_WiFi",
                "password": "ceraldi2024",
                "security": "WPA",
                "hidden": False,
            },
            "updated_at": datetime.utcnow().isoformat(),
        }
        supabase.table("menu_qrcode_config").insert(default_config).execute()
        return default_config

    return config


@router.put("/config")
async def update_qrcode_config(
    config_update: QRCodeConfigUpdate,
    username: str = Depends(verify_token),
):
    """Update QR code configuration (protected endpoint)"""
    current_config = _get_config_row()

    if not current_config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    update_data = {}
    if config_update.menu_url is not None:
        update_data["menu_url"] = config_update.menu_url
    if config_update.wifi is not None:
        update_data["wifi"] = config_update.wifi.dict()

    update_data["updated_at"] = datetime.utcnow().isoformat()
    update_data["updated_by"] = username

    supabase.table("menu_qrcode_config").update(update_data).eq("id", CONFIG_ID).execute()
    updated_config = _get_config_row()

    return {
        "success": True,
        "message": "Configuration updated successfully",
        "config": updated_config,
    }


@router.get("/generate/menu")
async def generate_menu_qr():
    """Generate QR code for menu URL"""
    config = _get_config_row()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(config["menu_url"])
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return {
        "qr_code": f"data:image/png;base64,{img_str}",
        "url": config["menu_url"],
    }


@router.get("/generate/wifi")
async def generate_wifi_qr():
    """Generate QR code for WiFi access"""
    config = _get_config_row()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    wifi = config["wifi"]
    wifi_string = f"WIFI:T:{wifi['security']};S:{wifi['ssid']};P:{wifi['password']};H:{'true' if wifi.get('hidden', False) else 'false'};;"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(wifi_string)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return {
        "qr_code": f"data:image/png;base64,{img_str}",
        "wifi": {
            "ssid": wifi["ssid"],
            "security": wifi["security"],
        },
    }


@router.get("/verify")
async def verify_admin_token(username: str = Depends(verify_token)):
    """Verify if token is still valid"""
    return {"valid": True, "username": username}
