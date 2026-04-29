"""
Ceraldi ERP - Main Application
==============================
FastAPI + MongoDB Atlas | Refactored Modular Architecture
"""
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Database
from app.middleware.error_handler import add_exception_handlers
from app.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

_PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
_FRONTEND_DIST = os.path.realpath(os.path.join(_PROJECT_ROOT, "frontend", "dist"))
_FRONTEND_PUBLIC = os.path.realpath(os.path.join(_PROJECT_ROOT, "frontend", "public"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup, yield, shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    settings.validate_startup()

    try:
        from app.core.handlers_registry import registra_tutti_gli_handler

        registra_tutti_gli_handler()
    except Exception:
        pass

    try:
        from app.services.event_bus import register_all_handlers

        register_all_handlers()
    except Exception as e:
        logger.warning(f"Event bus relazionale non inizializzato: {e}")

    try:
        from app.services.alert_engine import seed_alert_definitions

        db = Database.get_db()
        if db is not None:
            await seed_alert_definitions(db)
    except Exception as e:
        logger.warning(f"Seed alert_definitions non eseguito: {e}")

    try:
        from app.scheduler import start_scheduler

        start_scheduler()
        logger.info("Scheduler avviato")
    except Exception as e:
        logger.warning(f"Scheduler non avviato: {e}")

    try:
        db = Database.get_db()
        if db is not None:
            from app.routers.prima_nota_module.manutenzione import migrazione_pulisci_bancari_da_cassa

            await migrazione_pulisci_bancari_da_cassa()
    except Exception:
        pass

    logger.info("Application startup complete")
    yield

    logger.info("Shutting down...")
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
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    pass

from app.middleware.authentication import AuthenticationMiddleware

app.add_middleware(AuthenticationMiddleware)
add_exception_handlers(app)

from app.router_registry import register_all_routers

register_all_routers(app)


def _frontend_index_path() -> str | None:
    for root in (_FRONTEND_DIST, _FRONTEND_PUBLIC):
        index_path = os.path.join(root, "index.html")
        if os.path.isfile(index_path):
            return index_path
    return None


def _safe_frontend_file(root: str, requested_path: str) -> str | None:
    safe_path = os.path.normpath(requested_path).lstrip("/\\")
    if not safe_path:
        return None
    candidate = os.path.realpath(os.path.join(root, safe_path))
    root_prefix = root if root.endswith(os.sep) else root + os.sep
    if os.path.isfile(candidate) and candidate.startswith(root_prefix):
        return candidate
    return None


@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        index_path = _frontend_index_path()
        if index_path:
            return FileResponse(index_path)
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "status": "online"}


@app.get("/health")
@app.get("/api/health")
async def health_check():
    from datetime import datetime, timezone

    return {
        "status": "healthy",
        "database": "connected" if Database.db is not None else "disconnected",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/ping")
async def ping():
    return {"pong": True}


@app.get("/api/system/lock-status")
async def system_lock_status():
    from app.routers.documenti import get_current_operation, is_email_operation_running

    return {
        "email_locked": is_email_operation_running(),
        "operation": get_current_operation(),
        "can_start_email_operation": not is_email_operation_running(),
    }


docs_path = "./docs"
os.makedirs(docs_path, exist_ok=True)
app.mount("/api/download", StaticFiles(directory=docs_path), name="download")

if os.path.isdir(_FRONTEND_DIST):
    assets_path = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_dist(request: Request, full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        static_file = _safe_frontend_file(_FRONTEND_DIST, full_path)
        if static_file:
            return FileResponse(static_file)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

    logger.info("Frontend dist montato")
elif os.path.isdir(_FRONTEND_PUBLIC):

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_public(request: Request, full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        static_file = _safe_frontend_file(_FRONTEND_PUBLIC, full_path)
        if static_file:
            return FileResponse(static_file)
        return FileResponse(os.path.join(_FRONTEND_PUBLIC, "index.html"))

    logger.info("Frontend public montato")

# reload-trigger
