"""
Global Authentication Middleware.
Protects ALL API endpoints except whitelisted public paths.

This middleware ensures no endpoint is accidentally left unprotected.
Individual routers can still use Depends(get_current_user) for user context,
but this middleware acts as a safety net.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = {
    # Health checks
    "/",
    "/health",
    "/api/health",
    "/api/ping",
    
    # Authentication endpoints
    "/api/auth/login",
    "/api/auth/setup",  # Setup iniziale admin (solo se nessun admin esiste)
    # RIMOSSO: "/api/auth/register" — ora richiede autenticazione (admin crea utenti)

    # Integrazioni esterne: chiamanti che non possono avere un nostro JWT.
    # Prima nessuna era whitelistata → 401 sempre, integrazioni di fatto
    # rotte in produzione (bug #24 audit memoria/endpoints/README.md).
    # Ciascuna si autentica con un proprio meccanismo (vedi i rispettivi
    # router): WhatsApp col verify_token di Meta, il ponte ERP con
    # ERP_BRIDGE_SECRET.
    "/api/whatsapp/webhook",
    "/api/erp/ponte/fattura-ricevuta",

    # Pagine legali: già pubbliche in versione non-/api (bypass generico
    # "non è /api/"), whitelistate anche qui per coerenza sulla variante
    # /api/ usata da eventuali link esterni (revisione app Meta ecc.).
    "/api/privacy",
    "/api/terms",
    "/api/data-deletion",

    # OpenAPI docs (only in development)
    "/docs",
    "/redoc",
    "/openapi.json",

    # SEO/crawler files (must be accessible without auth)
    "/robots.txt",
    "/sitemap.xml",
    "/favicon.ico",
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = [
    "/api/auth/",        # All auth endpoints
    "/api/public/",      # Explicit public API
    "/docs",             # Swagger UI assets
    "/redoc",            # ReDoc assets
]

# NOTA: "/api/f24-public/" era whitelistato qui ma il prefisso "-public" è
# fuorviante: il router dietro (app/routers/f24/f24_public.py) espone lettura
# E SCRITTURA di dati fiscali reali (importi, upload PDF, modifica, delete)
# senza alcuna verifica — chiunque su internet poteva leggere/alterare gli
# F24 aziendali (bug #24 audit memoria/endpoints/README.md e 08-sistema-admin.md).
# L'unico chiamante reale è Dashboard.jsx che usa già il client axios
# autenticato (stesso Bearer/cookie di ogni altra chiamata /api/*): rimosso
# dalla whitelist, ora richiede JWT come tutto il resto.


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Global authentication middleware.
    
    Checks for valid JWT token on all API requests except whitelisted paths.
    This is a SAFETY NET - individual routers should still use Depends(get_current_user)
    for getting user context, but this prevents accidentally unprotected endpoints.
    """
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        
        # Allow OPTIONS (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)
        
        # Allow public paths
        if path in PUBLIC_PATHS:
            return await call_next(request)
        
        # Allow public prefixes
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)
        
        # Allow non-API paths (static files, etc.)
        if not path.startswith("/api/"):
            return await call_next(request)
        
        # Allow WebSocket upgrades (validate token from query params)
        if request.headers.get("upgrade", "").lower() == "websocket":
            token = request.query_params.get("token")
            if not token:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "WebSocket authentication required: pass ?token=JWT"},
                )
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                user_id = payload.get("sub")
                if user_id:
                    request.state.user_id = user_id
                    request.state.user_email = payload.get("email")
                    request.state.user_role = payload.get("role", "user")
            except JWTError:
                return JSONResponse(status_code=401, content={"detail": "Invalid WebSocket token"})
            return await call_next(request)
        
        # --- Require authentication for all other /api/ paths ---
        # Token dal header Bearer (chiamate API del frontend) OPPURE dal
        # cookie di sessione (link aperti direttamente nel browser, es.
        # "Vedi fattura" in nuova scheda: il browser non manda il Bearer).
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.cookies.get("access_token")

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            user_id = payload.get("sub")
            if not user_id:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token: missing user ID"},
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Store user info in request state for downstream access
            request.state.user_id = user_id
            request.state.user_email = payload.get("email")
            request.state.user_role = payload.get("role", "user")

        except JWTError as e:
            logger.warning(f"Auth middleware: invalid token on {path}: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        response = await call_next(request)

        # --- SESSIONE SCORREVOLE (regola utente: PIN dopo 1 ora di
        # inattività). Se il token ha superato metà vita, ne emettiamo uno
        # fresco nello header X-Token-Rinnovato: il frontend lo salva e la
        # scadenza riparte. Usando l'app la sessione non cade mai; ferma
        # per più di ACCESS_TOKEN_EXPIRE_MINUTES → 401 → PIN.
        try:
            exp = payload.get("exp")
            if exp:
                vita = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
                residuo = datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)
                if timedelta(0) < residuo < vita / 2:
                    nuovo = jwt.encode(
                        {
                            "sub": user_id,
                            "email": payload.get("email"),
                            "name": payload.get("name"),
                            "role": payload.get("role", "user"),
                            "exp": datetime.now(timezone.utc) + vita,
                        },
                        settings.SECRET_KEY,
                        algorithm=settings.ALGORITHM,
                    )
                    response.headers["X-Token-Rinnovato"] = nuovo
                    # Rinnova anche il COOKIE di sessione (stessi flag del
                    # login): il cookie serve agli iframe "Vedi fattura" che
                    # non mandano il Bearer. Senza questo rinnovo, dopo
                    # un'ora di uso il Bearer restava fresco ma il cookie
                    # scadeva → "Authentication required" aprendo la fattura
                    # dalla Prima Nota (segnalato dall'utente il 10/07).
                    response.set_cookie(
                        key="access_token",
                        value=nuovo,
                        httponly=True,
                        secure=False,
                        samesite="lax",
                        max_age=int(vita.total_seconds()),
                        path="/",
                    )
        except Exception:
            logger.exception("Rinnovo scorrevole token non riuscito (non bloccante)")

        return response
