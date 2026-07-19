"""
Auth Router — Ceraldi Group ERP
Login/Logout con bcrypt + PyJWT httpOnly cookie.
Singolo utente admin configurato via env.
"""
import os
import hmac
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

# Cookie Secure: in produzione (Render/https) i cookie di sessione viaggiano
# solo su TLS; in locale (http) resta False altrimenti il browser li scarta.
_COOKIE_SECURE = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID")
                      or os.getenv("ENVIRONMENT", "").lower() == "production")

ADMIN_EMAIL         = os.getenv("ADMIN_EMAIL", "ceraldigroupsrl@gmail.com")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")   # bcrypt (priorità)
ADMIN_PASSWORD      = os.getenv("ADMIN_PASSWORD", "")        # chiaro (fallback solo se l'hash non è configurato)
# IMPORTANTE: STESSA chiave del middleware di autenticazione (settings.SECRET_KEY,
# che include il segreto condiviso in sistema_stato.auth_secret). Prima il login
# firmava con os.getenv("SECRET_KEY") o una chiave CASUALE per processo: se
# diversa da quella del middleware, OGNI chiamata API rispondeva 401
# ("Authentication required" su tutte le pagine).
SECRET_KEY          = settings.SECRET_KEY
# Scelta utente 13/07/2026: 1 ora di inattività (poi ri-login). Il token vive
# ACCESS_TOKEN_EXPIRE_MINUTES e il middleware lo rinnova da solo mentre l'utente
# lavora (sessione scorrevole), quindi non cade mai durante l'uso attivo.
TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


def _check_password(plain: str) -> bool:
    """Verifica password: bcrypt (se configurato) ha sempre la priorità sul
    confronto in chiaro. ADMIN_PASSWORD resta solo un fallback per ambienti
    senza ADMIN_PASSWORD_HASH configurato (audit sicurezza 19/07/2026: prima
    il chiaro aveva priorità anche con l'hash presente)."""
    if ADMIN_PASSWORD_HASH:
        try:
            return bcrypt.checkpw(plain.encode(), ADMIN_PASSWORD_HASH.encode())
        except Exception:
            return False
    if ADMIN_PASSWORD:
        # Confronto a tempo costante: evita timing attack sul confronto '=='.
        return hmac.compare_digest(plain, ADMIN_PASSWORD)
    return False


class LoginRequest(BaseModel):
    email: str
    password: str


async def _audit_login(ip: str, email: str, ok: bool) -> None:
    """Registra il tentativo di login (best-effort, non blocca mai)."""
    try:
        from app.database import Database
        from app.services.audit_logger import log_sicurezza
        await log_sicurezza(
            Database.get_db(),
            azione="login_ok" if ok else "login_fallito",
            dettaglio=f"Login email {'riuscito' if ok else 'fallito'}",
            utente=email, ip=ip,
        )
    except Exception:
        pass


def _make_token(email: str, role: str = "admin", name: str = "Admin") -> str:
    # Il ruolo viaggia NEL token: il middleware e le dependency lo leggono da
    # qui. L'admin via env resta 'admin' (nessun cambiamento di comportamento).
    payload = {
        "sub": email,
        "email": email,
        "name": name,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


async def _decode_token(request: Request) -> dict:
    """Decodifica il JWT da cookie o header Authorization. Ritorna il payload."""
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")

    # Blacklist controllata SOLO dopo che firma/scadenza sono già valide
    # (review Codex su PR #65, stesso fix già fatto nel middleware globale
    # ma dimenticato qui: /api/auth/verify bypassa il middleware essendo
    # pubblico, quindi ha una propria copia dello stesso controllo).
    from app.database import Database
    from app.utils.token_blacklist import is_revocato
    if await is_revocato(Database.get_db(), token):
        raise HTTPException(status_code=401, detail="Sessione terminata (logout)")

    return payload


async def verify_token(request: Request) -> str:
    """Verifica JWT da cookie o header Authorization. Ritorna email utente."""
    payload = await _decode_token(request)
    return payload["sub"]


# NB: gli alias legacy /api/login, /api/logout, /api/me sono stati rimossi
# (audit lug 2026): il frontend usa esclusivamente /api/auth/login,
# /api/auth/logout, /api/auth/verify definiti qui sotto.


@router.get("/auth/verify")
async def verify(request: Request):
    """Compatibilità AuthContext frontend: verifica sessione attiva."""
    from app.utils.ruoli import normalizza_ruolo
    payload = await _decode_token(request)
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
        await _audit_login(ip, body.email, ok=False)
        raise HTTPException(status_code=401, detail="Credenziali errate")
    login_lockout.clear_failures(ip)
    await _audit_login(ip, body.email, ok=True)
    token = _make_token(body.email)
    response.set_cookie(key="access_token", value=token, httponly=True,
                        secure=_COOKIE_SECURE, samesite="lax", max_age=TOKEN_EXPIRE_MINUTES * 60, path="/")
    response.set_cookie(key="session_active", value="1", httponly=False,
                        secure=_COOKIE_SECURE, samesite="lax", max_age=TOKEN_EXPIRE_MINUTES * 60, path="/")
    return {
        "ok":          True,
        "email":       body.email,
        "access_token": token,   # il frontend lo ignora (usa cookie)
        "user":        {"email": body.email, "name": "Admin", "role": "admin"},
    }


@router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    """Alias /api/auth/logout. Revoca il token lato server (audit 19/07/2026:
    prima il logout cancellava solo i cookie, un token rubato restava valido
    fino a scadenza naturale)."""
    # Il frontend manda SEMPRE il bearer da localStorage (interceptor axios)
    # E il browser manda il cookie in automatico: normalmente coincidono, ma
    # la sessione scorrevole può rinnovarli in momenti diversi. Revoca
    # ENTRAMBI se presenti e diversi — prima si sceglieva solo il cookie e
    # un bearer copiato/divergente restava valido fino a scadenza (review
    # Codex su PR #65).
    token_cookie = request.cookies.get("access_token")
    token_bearer = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_bearer = auth_header[7:]

    for token in {t for t in (token_cookie, token_bearer) if t}:
        from app.database import Database
        from app.utils.token_blacklist import revoca_token
        try:
            # verify_exp=False: un token scaduto ma firmato correttamente va
            # comunque revocato (con la sua scadenza reale per il TTL).
            # Un token con firma non valida/malformato NON va in blacklist:
            # /api/auth/logout è pubblico, altrimenti chiunque potrebbe
            # riempire token_blacklist con hash spazzatura senza scadenza
            # (review Codex su PR #65).
            exp = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False}).get("exp")
        except jwt.InvalidTokenError:
            continue
        await revoca_token(Database.get_db(), token, exp=exp)
    response.delete_cookie("access_token")
    response.delete_cookie("session_active")
    return {"ok": True}
