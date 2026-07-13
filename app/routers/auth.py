"""
Auth Router — Ceraldi Group ERP
Login/Logout con bcrypt + PyJWT httpOnly cookie.
Singolo utente admin configurato via env.
"""
import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Response, Request, HTTPException, status
from pydantic import BaseModel
from dotenv import load_dotenv

from app.config import settings
from app.utils import login_lockout

load_dotenv()

router = APIRouter(prefix="/api", tags=["auth"])

ADMIN_EMAIL         = os.getenv("ADMIN_EMAIL", "ceraldigroupsrl@gmail.com")
ADMIN_PASSWORD      = os.getenv("ADMIN_PASSWORD", "")        # password in chiaro (priorità)
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")   # bcrypt (fallback)
# IMPORTANTE: STESSA chiave del middleware di autenticazione (settings.SECRET_KEY,
# che include il segreto condiviso in sistema_stato.auth_secret). Prima il login
# firmava con os.getenv("SECRET_KEY") o una chiave CASUALE per processo: se
# diversa da quella del middleware, OGNI chiamata API rispondeva 401
# ("Authentication required" su tutte le pagine).
SECRET_KEY          = settings.SECRET_KEY
TOKEN_EXPIRE_HOURS  = 24 * 7   # 7 giorni


def _check_password(plain: str) -> bool:
    """Verifica password: prima in chiaro, poi bcrypt se hash configurato."""
    if ADMIN_PASSWORD:
        return plain == ADMIN_PASSWORD
    if ADMIN_PASSWORD_HASH:
        try:
            return bcrypt.checkpw(plain.encode(), ADMIN_PASSWORD_HASH.encode())
        except Exception:
            return False
    return False


class LoginRequest(BaseModel):
    email: str
    password: str


def _make_token(email: str, role: str = "admin", name: str = "Admin") -> str:
    # Il ruolo viaggia NEL token: il middleware e le dependency lo leggono da
    # qui. L'admin via env resta 'admin' (nessun cambiamento di comportamento).
    payload = {
        "sub": email,
        "email": email,
        "name": name,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _decode_token(request: Request) -> dict:
    """Decodifica il JWT da cookie o header Authorization. Ritorna il payload."""
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")


def verify_token(request: Request) -> str:
    """Verifica JWT da cookie o header Authorization. Ritorna email utente."""
    return _decode_token(request)["sub"]


# NB: gli alias legacy /api/login, /api/logout, /api/me sono stati rimossi
# (audit lug 2026): il frontend usa esclusivamente /api/auth/login,
# /api/auth/logout, /api/auth/verify definiti qui sotto.


@router.get("/auth/verify")
async def verify(request: Request):
    """Compatibilità AuthContext frontend: verifica sessione attiva."""
    from app.utils.ruoli import normalizza_ruolo
    payload = _decode_token(request)
    email = payload["sub"]
    ruolo = normalizza_ruolo(payload.get("role"))
    return {
        "ok":    True,
        "user":  {"email": email, "name": payload.get("name", "Admin"), "role": ruolo},
        "email": email,
    }


@router.post("/auth/login")
async def auth_login(body: LoginRequest, request: Request, response: Response):
    """Alias /api/auth/login → /api/login per compatibilità frontend."""
    ip = login_lockout.client_ip(request)
    lock = login_lockout.seconds_locked(ip)
    if lock > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Troppi tentativi falliti. Riprova tra {lock} secondi.",
        )
    if body.email.lower() != ADMIN_EMAIL.lower() or not _check_password(body.password):
        login_lockout.register_failure(ip)
        raise HTTPException(status_code=401, detail="Credenziali errate")
    login_lockout.clear_failures(ip)
    token = _make_token(body.email)
    response.set_cookie(key="access_token", value=token, httponly=True,
                        secure=False, samesite="lax", max_age=TOKEN_EXPIRE_HOURS * 3600, path="/")
    response.set_cookie(key="session_active", value="1", httponly=False,
                        secure=False, samesite="lax", max_age=TOKEN_EXPIRE_HOURS * 3600, path="/")
    return {
        "ok":          True,
        "email":       body.email,
        "access_token": token,   # il frontend lo ignora (usa cookie)
        "user":        {"email": body.email, "name": "Admin", "role": "admin"},
    }


@router.post("/auth/logout")
async def auth_logout(response: Response):
    """Alias /api/auth/logout."""
    response.delete_cookie("access_token")
    response.delete_cookie("session_active")
    return {"ok": True}
