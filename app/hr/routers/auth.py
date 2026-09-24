"""
Auth Router — Ceraldi Group ERP
Login/Logout con bcrypt + PyJWT httpOnly cookie.
Singolo utente admin configurato via env.
"""
import hmac
import os
import jwt
import bcrypt
from datetime import timedelta
from fastapi import APIRouter, Response, Request, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from app.hr.config import settings as _hr_settings
from app.services.workforce_tokens import create_workforce_token
from app.utils import login_lockout

load_dotenv()

router = APIRouter(prefix="/api", tags=["auth"])

# Dentro GestionaleCloud i nomi sono prefissati HR_ (l'app ospite ha le sue
# ADMIN_EMAIL / ADMIN_PASSWORD / SECRET_KEY); i nomi originali restano come fallback.
ADMIN_EMAIL         = os.getenv("HR_ADMIN_EMAIL") or os.getenv("ADMIN_EMAIL", "ceraldigroupsrl@gmail.com")
ADMIN_PASSWORD      = os.getenv("HR_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD", "")        # password in chiaro (priorità)
ADMIN_PASSWORD_HASH = os.getenv("HR_ADMIN_PASSWORD_HASH") or os.getenv("ADMIN_PASSWORD_HASH", "")   # bcrypt (fallback)
# Sicurezza (fix 19/09/2026): niente più fallback hardcoded in chiaro
# ("ceraldi-erp-2026") committato nel codice. Il segreto JWT è UNICO per
# tutto app/hr/ (pin_login, dependencies, identity, auth_dipendenti lo
# leggono già da qui): se HR_JWT_SECRET/JWT_SECRET non sono configurate,
# `_shared_auth_secret()` in app/hr/config.py genera già un secret casuale
# effimero (mai una stringa prevedibile) e logga l'assenza della variabile.
SECRET_KEY          = _hr_settings.SECRET_KEY
TOKEN_EXPIRE_HOURS  = 24 * 7   # 7 giorni


def _check_password(plain: str) -> bool:
    """Verifica password: prima in chiaro, poi bcrypt se hash configurato.

    Il confronto in chiaro e' a tempo costante: `==` si ferma al primo
    carattere diverso e lascia misurare quanti ne sono giusti.
    """
    if ADMIN_PASSWORD:
        return hmac.compare_digest(plain.encode(), ADMIN_PASSWORD.encode())
    if ADMIN_PASSWORD_HASH:
        try:
            return bcrypt.checkpw(plain.encode(), ADMIN_PASSWORD_HASH.encode())
        except Exception:
            return False
    return False


class LoginRequest(BaseModel):
    email: str
    password: str


def _make_token(email: str) -> str:
    return create_workforce_token(
        sub=email,
        name="Admin",
        role="admin",
        secret=SECRET_KEY,
        expires_in=timedelta(hours=TOKEN_EXPIRE_HOURS),
        auth_method="password",
        algorithm=_hr_settings.ALGORITHM,
        email=email,
    )


def verify_token(request: Request) -> str:
    """Verifica JWT da cookie o header Authorization. Ritorna email utente."""
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")


# Il cookie resta sotto /hr: con path "/" finiva anche sulle richieste del
# gestionale, che legge un cookie con lo stesso nome firmato con un altro
# segreto. `secure` segue lo schema reale (Render termina l'HTTPS davanti).
_COOKIE_PATH = "/hr"


def _https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto.split(",")[0].strip().lower() == "https"


def _set_session_cookies(request: Request, response: Response, token: str) -> None:
    secure = _https(request)
    max_age = TOKEN_EXPIRE_HOURS * 3600
    response.set_cookie(key="access_token", value=token, httponly=True, secure=secure,
                        samesite="lax", max_age=max_age, path=_COOKIE_PATH)
    response.set_cookie(key="session_active", value="1", httponly=False, secure=secure,
                        samesite="lax", max_age=max_age, path=_COOKIE_PATH)


def _clear_session_cookies(response: Response) -> None:
    for nome in ("access_token", "session_active"):
        response.delete_cookie(nome, path=_COOKIE_PATH)
        response.delete_cookie(nome)  # cookie emessi prima con path "/"


def _login_admin(request: Request, body: "LoginRequest", response: Response) -> str:
    """Login email/password con lo stesso blocco tentativi del PIN."""
    ip = login_lockout.client_ip(request)
    attesa = login_lockout.seconds_locked(ip)
    if attesa > 0:
        raise HTTPException(status_code=429, detail=f"Troppi tentativi, riprova tra {attesa}s")
    email_ok = hmac.compare_digest(body.email.strip().lower().encode(), ADMIN_EMAIL.lower().encode())
    password_ok = _check_password(body.password)
    if not (email_ok and password_ok):
        login_lockout.register_failure(ip)
        raise HTTPException(status_code=401, detail="Credenziali errate")
    login_lockout.clear_failures(ip)
    token = _make_token(body.email)
    _set_session_cookies(request, response, token)
    return token


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    _login_admin(request, body, response)
    return {"ok": True, "email": body.email}


@router.post("/logout")
async def logout(response: Response):
    _clear_session_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    email = verify_token(request)
    return {"email": email, "ok": True}


@router.get("/auth/verify")
async def verify(request: Request):
    """Compatibilità AuthContext frontend: verifica sessione attiva."""
    email = verify_token(request)
    return {
        "ok":    True,
        "user":  {"email": email, "name": "Admin", "role": "admin"},
        "email": email,
    }


@router.post("/auth/login")
async def auth_login(body: LoginRequest, request: Request, response: Response):
    """Alias /api/auth/login → /api/login per compatibilità frontend."""
    token = _login_admin(request, body, response)
    return {
        "ok":          True,
        "email":       body.email,
        "access_token": token,   # il frontend lo ignora (usa cookie)
        "user":        {"email": body.email, "name": "Admin", "role": "admin"},
    }


@router.post("/auth/logout")
async def auth_logout(response: Response):
    """Alias /api/auth/logout."""
    _clear_session_cookies(response)
    return {"ok": True}
