"""
Global Authentication Middleware.
Protects ALL API endpoints except whitelisted public paths.

This middleware ensures no endpoint is accidentally left unprotected.
Individual routers can still use Depends(get_current_user) for user context,
but this middleware acts as a safety net.
"""
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
    
    # OpenAPI docs (only in development)
    "/docs",
    "/redoc",
    "/openapi.json",
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = [
    "/api/auth/",        # All auth endpoints
    "/api/public/",      # Explicit public API
    "/api/f24-public/",  # F24 public endpoints
    "/api/enhanced-parser/info",  # Parser info endpoint
    "/api/openclaw/",    # OpenClaw AI assistant
    "/docs",             # Swagger UI assets
    "/redoc",            # ReDoc assets
]


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Global authentication middleware.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Check if auth is disabled
        if getattr(settings, 'AUTH_DISABLED', False) or settings.ENVIRONMENT == "development":
            return await call_next(request)
            
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
        auth_header = request.headers.get("Authorization", "")
        
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = auth_header[7:]  # Remove "Bearer "
        
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
        
        return await call_next(request)
