from fastapi import APIRouter, HTTPException, Depends, Header, Request
from app.menu.models.qrcode_models import QRCodeConfigUpdate, AdminLoginResponse
from datetime import UTC, datetime, timedelta
import os
import jwt
from io import BytesIO
import base64

from app.menu.supabase_client import supabase

CONFIG_ID = "qrcode_config"

router = APIRouter(prefix="/api/qrcode", tags=["QR Code Management"])

# Il Menu non possiede un login amministrativo autonomo. MENU_JWT_SECRET firma
# soltanto il token derivato da una sessione ERP gia' autenticata.
SECRET_KEY = os.environ.get("MENU_JWT_SECRET") or os.environ.get("JWT_SECRET") or ""
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours
ADMIN_USERNAME = os.environ.get("MENU_ADMIN_USERNAME") or os.environ.get("ADMIN_USERNAME", "ceraldi")


def create_access_token(data: dict):
    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Login non configurato (MENU_JWT_SECRET mancante)")
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def verify_token(authorization: str = Header(None)):
    """Token del Menu, nato solo dalla sessione del Gestionale: oltre a firma e
    scadenza si controlla che il logout del Gestionale non l'abbia revocato."""
    from app.services.group_session import sessione_derivata_valida

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
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        # PyJWT non ha JWTError (e' di python-jose): con quel nome un token
        # malformato usciva come AttributeError, cioe' 500 invece di 401.
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    # L'unico ingresso admin del Menu e' la sessione del Gestionale: un token
    # del vecchio login col PIN non vale piu', anche se non e' scaduto.
    if payload.get("auth_method") != "sessione_erp" or not await sessione_derivata_valida(payload):
        raise HTTPException(status_code=401, detail="Sessione del Gestionale chiusa")
    return username


@router.get("/session", response_model=AdminLoginResponse)
async def sessione_dal_gestionale(request: Request):
    """L'amministratore gia' entrato nel Gestionale apre l'amministrazione del
    Menu senza PIN: prova la sessione (cookie ERP, vedi
    `app/services/group_session.py`) e riceve un token del Menu, mai quello
    dell'ERP."""
    from app.services.group_session import sessione_erp

    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Login amministratore non configurato")
    identita = await sessione_erp(request)
    if not identita:
        raise HTTPException(status_code=401, detail="Nessuna sessione del Gestionale")
    token = create_access_token(
        data={"sub": ADMIN_USERNAME, "auth_method": "sessione_erp", "sid": identita["sid"]}
    )
    return AdminLoginResponse(success=True, token=token, message="Accesso dal Gestionale")


def _get_config_row():
    res = supabase.table("menu_qrcode_config").select("*").eq("id", CONFIG_ID).limit(1).execute()
    return res.data[0] if res.data else None


def _public_config(config: dict) -> dict:
    """Return only the non-secret part of the QR configuration."""
    public = dict(config)
    wifi = dict(config.get("wifi") or {})
    wifi.pop("password", None)
    public["wifi"] = wifi
    return public


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
                # Deliberately do not rotate the network here.  The deployment
                # supplies its current password as a secret instead of source code.
                "password": os.environ.get("MENU_WIFI_PASSWORD", ""),
                "security": "WPA",
                "hidden": False,
            },
            "updated_at": datetime.now(UTC).isoformat(),
        }
        supabase.table("menu_qrcode_config").insert(default_config).execute()
        return _public_config(default_config)

    return _public_config(config)


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

    update_data["updated_at"] = datetime.now(UTC).isoformat()
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
    import qrcode
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
async def generate_wifi_qr(_username: str = Depends(verify_token)):
    """Generate QR code for WiFi access"""
    import qrcode
    config = _get_config_row()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    wifi = config.get("wifi") or {}
    if not wifi.get("password"):
        raise HTTPException(status_code=503, detail="Password Wi-Fi non configurata")
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
