from fastapi import APIRouter, HTTPException, Depends, Header, Request, status
from app.menu.models.qrcode_models import MenuUrlUpdate, AdminPinLogin, AdminLoginResponse
from datetime import datetime, timedelta
import os
import jwt
from io import BytesIO
import base64
from urllib.parse import urlsplit

from app.menu.supabase_client import supabase
from app.utils import login_lockout
from app.services import pin_authentication

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
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        # PyJWT non ha JWTError (e' di python-jose): con quel nome un token
        # malformato usciva come AttributeError, cioe' 500 invece di 401.
        raise HTTPException(status_code=401, detail="Invalid token") from exc


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

    if not pin_authentication.admin_pin_is_configured():
        raise HTTPException(status_code=503, detail="PIN amministratore non configurato")

    if not pin_authentication.admin_pin_matches(pin):
        login_lockout.register_failure(ip)
        return AdminLoginResponse(success=False, message="PIN non valido")

    login_lockout.clear_failures(ip)
    access_token = create_access_token(data={"sub": ADMIN_USERNAME, "auth_method": "pin"})
    return AdminLoginResponse(
        success=True,
        token=access_token,
        message="Accesso effettuato",
    )


@router.get("/session", response_model=AdminLoginResponse)
async def sessione_dal_gestionale(request: Request):
    """L'amministratore gia' entrato nel Gestionale apre l'amministrazione del
    Menu senza PIN: prova la sessione (cookie ERP, vedi
    `app/services/group_session.py`) e riceve un token del Menu, mai quello
    dell'ERP."""
    from app.services.group_session import sessione_erp

    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Login amministratore non configurato")
    if not await sessione_erp(request):
        raise HTTPException(status_code=401, detail="Nessuna sessione del Gestionale")
    token = create_access_token(data={"sub": ADMIN_USERNAME, "auth_method": "sessione_erp"})
    return AdminLoginResponse(success=True, token=token, message="Accesso dal Gestionale")


def _get_config_row():
    res = supabase.table("menu_qrcode_config").select("*").eq("id", CONFIG_ID).limit(1).execute()
    return res.data[0] if res.data else None


def normalizza_menu_url(valore: str) -> str:
    """L'indirizzo pubblico del menu clienti, in forma canonica.

    Deve essere https, con un dominio, e puntare al Menu (`/menu/`): il Mount
    di Starlette esige la barra finale, e `/menu` nudo o un altro percorso
    porterebbero il cliente nel gestionale o su una pagina che non esiste.
    Stampato su un QR, un indirizzo sbagliato non si corregge piu'.
    """
    testo = str(valore or "").strip()
    parti = urlsplit(testo)
    if parti.scheme != "https" or not parti.hostname:
        raise HTTPException(status_code=400, detail="L'indirizzo del menu deve iniziare con https:// e avere un dominio")
    if parti.path not in ("/menu", "/menu/") or parti.query or parti.fragment:
        raise HTTPException(status_code=400, detail="L'indirizzo del menu deve finire con /menu/")
    return f"https://{parti.netloc}/menu/"


# Il QR del menu clienti ha una sola fonte: `menu_qrcode_config.menu_url`,
# l'indirizzo pubblico scelto dall'amministratore (quello stampato sui tavoli).
# Il QR si disegna nel browser da questo valore; non si ricava piu' dal
# dominio da cui si apre l'amministrazione e non si genera una seconda
# immagine lato server.
@router.get("/menu-url")
async def leggi_menu_url():
    """Indirizzo pubblico del menu clienti (`null` se non ancora scelto)."""
    config = _get_config_row() or {}
    url = config.get("menu_url") or None
    return {"url": url, "updated_at": config.get("updated_at"), "updated_by": config.get("updated_by")}


@router.put("/menu-url")
async def aggiorna_menu_url(payload: MenuUrlUpdate, username: str = Depends(verify_token)):
    """Cambia l'indirizzo pubblico del menu clienti (solo amministratore)."""
    url = normalizza_menu_url(payload.url)
    adesso = datetime.utcnow().isoformat()
    if _get_config_row():
        supabase.table("menu_qrcode_config").update(
            {"menu_url": url, "updated_at": adesso, "updated_by": username}
        ).eq("id", CONFIG_ID).execute()
    else:
        supabase.table("menu_qrcode_config").insert(
            {"id": CONFIG_ID, "menu_url": url, "updated_at": adesso, "updated_by": username}
        ).execute()
    return {"url": url, "updated_at": adesso, "updated_by": username}


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
