"""
Ceraldi ERP — Main Application
================================
FastAPI + MongoDB Atlas | Refactored Modular Architecture
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.database import Database
from app.utils.logger import setup_logging, get_logger
from app.middleware.error_handler import add_exception_handlers

setup_logging()
logger = get_logger(__name__)


# =============================================================================
# LIFESPAN (Startup + Shutdown)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup → yield → shutdown."""
    # ── Startup ──
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
    
    settings.validate_startup()
    
    # Event Bus
    try:
        from app.core.handlers_registry import registra_tutti_gli_handler
        registra_tutti_gli_handler()
    except Exception:
        pass

    # Event Bus relazionale (Chat 8/9)
    try:
        from app.services.event_bus import register_all_handlers
        register_all_handlers()
    except Exception as e:
        logger.warning(f"Event bus relazionale non inizializzato: {e}")

    # Seed alert definitions (Chat 8)
    try:
        from app.services.alert_engine import seed_alert_definitions
        db = Database.get_db()
        if db is not None:
            await seed_alert_definitions(db)
    except Exception as e:
        logger.warning(f"Seed alert_definitions non eseguito: {e}")

    # Scheduler (PEC ogni ora, Gmail ogni ora, F24 giornaliero)
    try:
        from app.scheduler import start_scheduler
        start_scheduler()
        logger.info("⏰ Scheduler avviato")
    except Exception as e:
        logger.warning(f"Scheduler non avviato: {e}")
    
    # Migrazione one-shot: pulisci movimenti bancari da cassa
    try:
        db = Database.get_db()
        if db is not None:
            from app.routers.prima_nota_module.manutenzione import migrazione_pulisci_bancari_da_cassa
            await migrazione_pulisci_bancari_da_cassa()
    except Exception:
        pass
    
    logger.info("✅ Application startup complete")
    yield
    
    # ── Shutdown ──
    logger.info("🔄 Shutting down...")
    try:
        from app.services.email_monitor_service import stop_monitor
        stop_monitor()
    except Exception:
        pass
    try:
        from app.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    await Database.close_db()
    logger.info("✅ Shutdown complete")


# =============================================================================
# APP CREATION
# =============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
    redirect_slashes=False
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Rate Limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    pass

# Auth Middleware — montato GLOBALMENTE su tutti gli endpoint /api/
# (esclude whitelist di path pubblici definita in authentication.py)
from app.middleware.authentication import AuthenticationMiddleware
app.add_middleware(AuthenticationMiddleware)

# SEO: header X-Robots-Tag su TUTTE le risposte
# Gestionale privato → non deve comparire in nessun motore di ricerca.
from starlette.middleware.base import BaseHTTPMiddleware

class NoIndexMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet, noimageindex"
        return response

app.add_middleware(NoIndexMiddleware)

# Exception Handlers
add_exception_handlers(app)


# =============================================================================
# ROUTER REGISTRATION
# =============================================================================

from app.router_registry import register_all_routers
register_all_routers(app)

# Route alias senza trailing slash - workaround FastAPI 0.110.1 + proxy Emergent
# Redirect server-side: /api/mutui → /api/mutui/ e /api/scadenze → /api/scadenze/tutte
from fastapi.responses import RedirectResponse

@app.get("/api/mutui", include_in_schema=False, tags=["Mutui"])
async def mutui_root_alias(request: Request):
    """Alias senza trailing slash per /api/mutui/"""
    url = str(request.url).rstrip("/") + "/"
    return RedirectResponse(url=url, status_code=307)

@app.get("/api/scadenze", include_in_schema=False, tags=["Scadenze"])
async def scadenze_root_alias(request: Request):
    """Alias senza trailing slash per /api/scadenze/tutte"""
    # Preserva query params
    qs = request.url.query
    target = "/api/scadenze/tutte" + (f"?{qs}" if qs else "")
    return RedirectResponse(url=target, status_code=307)


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        _idx = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "index.html")
        if os.path.isfile(_idx):
            return FileResponse(_idx)
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "status": "online"}

@app.get("/health")
@app.get("/api/health")
async def health_check():
    from datetime import datetime, timezone
    return {
        "status": "healthy",
        "database": "connected" if Database.db is not None else "disconnected",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/ping")
async def ping():
    return {"pong": True}

@app.get("/api/system/lock-status")
async def system_lock_status():
    from app.routers.documenti import is_email_operation_running, get_current_operation
    return {
        "email_locked": is_email_operation_running(),
        "operation": get_current_operation(),
        "can_start_email_operation": not is_email_operation_running()
    }


# =============================================================================
# STATIC FILES & SPA SERVING
# =============================================================================

# Downloads
docs_path = "./docs"
os.makedirs(docs_path, exist_ok=True)
app.mount("/api/download", StaticFiles(directory=docs_path), name="download")

# SPA Frontend (React Router)
_FRONTEND_DIST = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        safe_path = os.path.normpath(full_path).lstrip("/\\")
        static_file = os.path.join(_FRONTEND_DIST, safe_path)
        if full_path and os.path.isfile(static_file) and static_file.startswith(_FRONTEND_DIST):
            return FileResponse(static_file)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

    logger.info("✅ Frontend React montato (SPA routing attivo)")


