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
import hmac
import logging
import os

from app.config import settings
from app.utils.session_cookie import SESSION_COOKIE_SECURE

logger = logging.getLogger(__name__)

RENDER_INGEST_PATHS = {
    "/api/documenti/upload-auto/render/preview",
    "/api/documenti/upload-auto/render",
}

LOTTI_INTEGRATION_PREFIX = "/api/integrations/lotti/"

# Modulo HR (portale dipendenti): login pubblico del portale e perimetro
# delle sessioni dipendente. Definiti nel modulo, letti qui.
from app.hr.router_registry import HR_PREFIX, HR_PUBLIC_PATHS  # noqa: E402
from app.menu.router_registry import MENU_PUBLIC_PREFIX, MENU_STAFF_PREFIX  # noqa: E402
HR_ALLOWED_OUTSIDE = {"/api/auth/logout"}
# Una sessione del portale dipendenti vale nel modulo HR e nelle schermate
# operative del menu (cassa, cucina, ordini, magazzino bar): mai altrove.
PREFISSI_SESSIONE_PORTALE = (HR_PREFIX + "/", MENU_STAFF_PREFIX + "/", MENU_PUBLIC_PREFIX + "/")

# Paths that don't require authentication
PUBLIC_PATHS = {
    # Health checks
    "/",
    "/health",
    "/api/health",
    "/api/ping",
    
    # Authentication endpoints
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/verify",  # verifica il token da sé (401 con messaggio specifico se assente/scaduto)
    "/api/auth/pin-login",  # login PIN reale (pin_login.router montato su /api/auth): senza
                             # questo path esplicito NESSUNO può più fare login (review Codex, PR #65)
    "/api/auth/mfa/verify-login",  # challenge firmata + OTP, non ancora una sessione
    # RIMOSSO: "/api/auth/register" — ora richiede autenticazione (admin crea utenti)

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
    # NOTA (audit sicurezza 19/07/2026): "/api/auth/" come prefisso è stato
    # rimosso da qui — rendeva pubblico per costruzione QUALSIASI endpoint
    # futuro montato sotto /api/auth/, non solo i 3 reali (login/logout/
    # verify), che ora sono elencati esplicitamente in PUBLIC_PATHS con lo
    # stesso identico comportamento di prima (nessun cambio per il frontend).
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

        # Credenziale macchina-a-macchina, valida esclusivamente per il ponte
        # documentale Render. Se manca la configurazione il canale resta chiuso.
        if path in RENDER_INGEST_PATHS:
            expected = (settings.RENDER_INGEST_SHARED_SECRET or "").strip()
            supplied = request.headers.get("X-Render-Ingest-Token", "").strip()
            if not expected:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Render document ingest non configurato"},
                )
            if not supplied or not hmac.compare_digest(supplied, expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Credenziale Render non valida"},
                )
            request.state.user_id = "render-document-ingest"
            request.state.user_email = "render-document-ingest@internal"
            request.state.user_role = "admin"
            request.state.auth_method = "render_shared_secret"
            return await call_next(request)

        # Il ponte Lotti e' un canale macchina-a-macchina: non ha una
        # sessione utente JWT, ma non e' pubblico. Il middleware valida qui
        # la stessa chiave privata che il router ricontrolla prima di leggere
        # le fatture, cosi' nessun endpoint del prefisso puo' bypassare
        # accidentalmente l'autenticazione globale.
        if path.startswith(LOTTI_INTEGRATION_PREFIX):
            expected = (os.environ.get("LOTTI_INTEGRATION_KEY") or "").strip()
            supplied = request.headers.get("X-Lotti-Key", "").strip()
            if not expected:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Integrazione Lotti non configurata"},
                )
            if not supplied or not hmac.compare_digest(supplied, expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Chiave integrazione Lotti non valida"},
                )
            request.state.user_id = "lotti-integration"
            request.state.user_email = "lotti-integration@internal"
            request.state.user_role = "admin"
            request.state.auth_method = "lotti_shared_secret"
            return await call_next(request)
        
        # Allow public paths
        if path in PUBLIC_PATHS or path in HR_PUBLIC_PATHS:
            return await call_next(request)
        # Menu digitale dei clienti (QR al tavolo): lettura del menu, invio
        # ordine, stato del proprio ordine, immagini. Nessuna sessione.
        if path == MENU_PUBLIC_PREFIX or path.startswith(MENU_PUBLIC_PREFIX + "/"):
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
                from app.utils.ruoli import normalizza_ruolo, RUOLI_VALIDI
                ruolo = normalizza_ruolo(payload.get("role"))
                if not user_id:
                    return JSONResponse(status_code=401, content={"detail": "Invalid WebSocket token"})
                if ruolo not in RUOLI_VALIDI:
                    return JSONResponse(status_code=403, content={"detail": "Ruolo utente non valido"})
                request.state.user_id = user_id
                request.state.user_email = payload.get("email")
                request.state.user_role = ruolo
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

            # Token revocato esplicitamente (logout) prima della scadenza
            # naturale. Controllato SOLO dopo che firma/scadenza sono già
            # validate (review Codex su PR #65): un token spazzatura non deve
            # costare una lettura Drive/Sheets prima di essere respinto localmente.
            from app.database import Database
            from app.utils.token_blacklist import TokenBlacklistUnavailable, is_revocato
            try:
                revocato = await is_revocato(Database.get_db(), token)
            except TokenBlacklistUnavailable:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Verifica sessione temporaneamente non disponibile"},
                )
            if revocato:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Sessione terminata (logout)"},
                    headers={"WWW-Authenticate": "Bearer"}
                )

            # --- CONTROLLO RUOLO (rete di sicurezza globale) ---
            # Sola lettura: nessuna scrittura. Operatore: fuori dagli endpoint
            # admin. Il ruolo storico "user" diventa operatore; un ruolo
            # assente/sconosciuto viene rifiutato senza privilegi impliciti.
            from app.utils.ruoli import (
                normalizza_ruolo, METODI_SCRITTURA, PREFISSI_SOLO_ADMIN,
                RUOLI_VALIDI, RUOLI_HR, SOLA_LETTURA, ADMIN,
            )
            ruolo = normalizza_ruolo(payload.get("role"))
            if ruolo not in RUOLI_VALIDI:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Ruolo utente non valido"},
                )
            # Un dipendente (o il responsabile turni) ha una sessione del
            # portale HR: vale solo per il modulo HR, mai per i dati contabili.
            if ruolo in RUOLI_HR and not path.startswith(PREFISSI_SESSIONE_PORTALE) and path not in HR_ALLOWED_OUTSIDE:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Sessione del portale dipendenti: accesso al gestionale non consentito"},
                )

            # Store only normalized user info in request state.
            request.state.user_id = user_id
            request.state.user_email = payload.get("email")
            request.state.user_role = ruolo
            # /logout resta sempre permesso (serve anche in sola lettura).
            if not path.startswith("/api/auth/"):
                if ruolo == SOLA_LETTURA and method in METODI_SCRITTURA:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Account in sola lettura: operazione non consentita"},
                    )
                if ruolo != ADMIN and any(path.startswith(p) for p in PREFISSI_SOLO_ADMIN):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Operazione riservata all'amministratore"},
                    )

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
                            "role": ruolo,
                            "tipo": ruolo,
                            "iat": datetime.now(timezone.utc),
                            "exp": datetime.now(timezone.utc) + vita,
                            "auth_method": payload.get("auth_method"),
                            "mfa_verified": bool(payload.get("mfa_verified")),
                            "mfa_verified_at": payload.get("mfa_verified_at"),
                            "amr": payload.get("amr") or [],
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
                        secure=SESSION_COOKIE_SECURE,
                        samesite="lax",
                        max_age=int(vita.total_seconds()),
                        path="/",
                    )
        except Exception:
            logger.exception("Rinnovo scorrevole token non riuscito (non bloccante)")

        return response
