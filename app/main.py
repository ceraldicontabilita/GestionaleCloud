"""
Ceraldi ERP - Main Application
==============================
FastAPI + MongoDB Atlas | Refactored Modular Architecture
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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

    # Bus eventi unico (app/services/event_bus.py): include anche gli handler
    # migrati dal vecchio bus core (app/core/event_bus.py, rimosso).
    try:
        from app.services.event_bus import register_all_handlers

        register_all_handlers()
    except Exception as e:
        logger.warning(f"Event bus non inizializzato: {e}")

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

    # Operazione una tantum autorizzata: elimina i dati operativi antecedenti
    # al 2026 solo in produzione Render, dopo backup separato per collection.
    # Cedolini, prima nota salari e bonifici collegati sono esclusi e verificati.
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        try:
            from app.routers.prima_nota_module.manutenzione import (
                esegui_pulizia_pregressi_una_tantum,
                ripristina_provvisori_metodo_errato,
            )

            pulizia = await esegui_pulizia_pregressi_una_tantum()
            if not pulizia.get("skipped"):
                logger.info(
                    "Pulizia pre-2026 completata: %s documenti archiviati ed eliminati",
                    pulizia.get("totale_eliminati", 0),
                )

            # Ripara una sola volta le registrazioni automatiche sul lato
            # errato. Pagamenti manuali e riconciliati non vengono toccati.
            repair_marker = "repair_supplier_payment_side_20260720_v1"
            repair_run = await db["migration_runs"].find_one({"id": repair_marker})
            if not repair_run or repair_run.get("status") != "completed":
                riparazione = await ripristina_provvisori_metodo_errato(
                    dry_run=False, anno=2026,
                    banca_non_riconciliate=False, _admin={}
                )
                await db["migration_runs"].update_one(
                    {"id": repair_marker},
                    {"$set": {
                        "id": repair_marker,
                        "status": "completed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "result": riparazione,
                    }},
                    upsert=True,
                )
                if riparazione.get("corretti"):
                    logger.info(
                        "Fatture automatiche con metodo errato ripristinate: %s",
                        riparazione["corretti"],
                    )
        except Exception as e:
            logger.error("Pulizia pregressi/riparazione metodo non completata: %s", e)

    # Backfill: fatture importate da Drive/bulk prima del fix campi — senza
    # `anno`/`data_documento` non comparivano nei filtri per anno.
    try:
        db = Database.get_db()
        if db is not None:
            r = await db["invoices"].update_many(
                {"anno": {"$exists": False},
                 "invoice_date": {"$regex": r"^\d{4}-"}},
                [{"$set": {
                    "anno": {"$toInt": {"$substrCP": ["$invoice_date", 0, 4]}},
                    "data_documento": {"$ifNull": ["$data_documento", "$invoice_date"]},
                    "numero_fattura": {"$ifNull": ["$numero_fattura", "$invoice_number"]},
                    "cedente_denominazione": {"$ifNull": ["$cedente_denominazione", "$supplier_name"]},
                    "cedente_piva": {"$ifNull": ["$cedente_piva", "$supplier_vat"]},
                }}],
            )
            if r.modified_count:
                logger.info(f"Backfill fatture senza anno: {r.modified_count} aggiornate")
    except Exception as e:
        logger.warning(f"Backfill anno fatture non eseguito: {e}")

    # Migrazione: assegni auto-associati con beneficiario sintetico
    # "Pag. fatt. X - Y" invece di un vero nome beneficiario. Li riporta a
    # "da associare" senza perdere il collegamento alla fattura già trovato.
    try:
        db = Database.get_db()
        if db is not None:
            r = await db["assegni"].update_many(
                {"beneficiario": {"$regex": r"^Pag\. fatt\. "}},
                {"$set": {"beneficiario": "", "stato": "vuoto"}},
            )
            if r.modified_count:
                logger.info(f"Corretti {r.modified_count} assegni con beneficiario fittizio")
    except Exception as e:
        logger.warning(f"Pulizia beneficiari fittizi assegni non eseguita: {e}")

    # Migrazione: gli ammortamenti cespiti venivano registrati anche come
    # "uscita" reale in prima_nota_cassa (costo non monetario che abbassava
    # il saldo cassa). Soft-delete dei movimenti generati da quel bug:
    # riconoscibili senza ambiguità dal source dedicato.
    try:
        db = Database.get_db()
        if db is not None:
            r = await db["prima_nota_cassa"].update_many(
                {"source": "ammortamento_cespiti", "status": {"$ne": "deleted"}},
                {"$set": {"status": "deleted",
                          "nota_migrazione": "ammortamento non monetario, rimosso dalla cassa"}},
            )
            if r.modified_count:
                logger.info(f"Neutralizzati {r.modified_count} movimenti cassa da ammortamenti (non monetari)")
    except Exception as e:
        logger.warning(f"Pulizia ammortamenti in cassa non eseguita: {e}")

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
    # Sessione scorrevole: il browser deve poter leggere il token rinnovato
    expose_headers=["X-Token-Rinnovato"],
)

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    # Audit sicurezza 19/07/2026: il Limiter era istanziato ma senza questo
    # middleware default_limits non veniva mai applicato — nessun endpoint
    # (tranne login/PIN, che hanno il loro lockout dedicato) aveva un limite
    # di richieste reale.
    app.add_middleware(SlowAPIMiddleware)
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


# Bug segnalato dall'utente 17/07/2026 ("non vedo niente di live"): l'index
# veniva servito SENZA Cache-Control, quindi il browser (specie la PWA su
# telefono) applicava la cache euristica e continuava a caricare i chunk JS
# vecchi anche dopo il deploy. no-cache = il browser riconvalida l'index a
# ogni apertura (costa un 304 da pochi byte) e prende subito il bundle nuovo.
_INDEX_HEADERS = {"Cache-Control": "no-cache"}


def _index_response(index_path: str) -> FileResponse:
    return FileResponse(index_path, headers=_INDEX_HEADERS)


def _static_response(file_path: str) -> FileResponse:
    # I file dentro /assets hanno l'hash del contenuto nel nome: se cambiano,
    # cambia l'URL — la cache lunga e "immutable" è sicura e velocizza l'app.
    if f"{os.sep}assets{os.sep}" in file_path:
        return FileResponse(
            file_path, headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
    # Altri file statici (icone, manifest, service-worker): riconvalida.
    return FileResponse(file_path, headers=_INDEX_HEADERS)


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
            return _index_response(index_path)
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

class _HashedAssets(StaticFiles):
    """Asset con hash nel nome (index-BJ8lb5ff.js): cache lunga sicura."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


if os.path.isdir(_FRONTEND_DIST):
    assets_path = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(assets_path):
        app.mount("/assets", _HashedAssets(directory=assets_path), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_spa_dist(request: Request, full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        static_file = _safe_frontend_file(_FRONTEND_DIST, full_path)
        if static_file:
            return _static_response(static_file)
        return _index_response(os.path.join(_FRONTEND_DIST, "index.html"))

    logger.info("Frontend dist montato")
elif os.path.isdir(_FRONTEND_PUBLIC):

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_spa_public(request: Request, full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        static_file = _safe_frontend_file(_FRONTEND_PUBLIC, full_path)
        if static_file:
            return _static_response(static_file)
        return _index_response(os.path.join(_FRONTEND_PUBLIC, "index.html"))

    logger.info("Frontend public montato")

# reload-trigger
