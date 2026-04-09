"""Ceraldi ERP v2 - Main Application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import logging

from app.config import settings
from app.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # Avvia scheduler se abilitato
    if settings.SCHEDULER_ENABLED:
        try:
            from app.routers.scheduler import start_scheduler
            start_scheduler()
            logger.info("Scheduler avviato")
        except Exception as e:
            logger.warning(f"Scheduler non avviato: {e}")

    yield

    # Ferma scheduler
    try:
        from app.routers.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass

    await Database.close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTERS — Contabilità / Gestionale
# ═══════════════════════════════════════════════════════════════════════════════
from app.routers import (
    fornitori, learning, tributi, alert_fiscali, quietanze,
    dipendenti, health, fatture, cedolini,
    estratto_conto, f24, corrispettivi, distinte, verbali,
    import_hub, mittenti, presenze, f24_privati, omaggi_acquaviva, ordini,
    prima_nota,
)

app.include_router(health.router,            prefix="/api",                 tags=["health"])
app.include_router(import_hub.router,        prefix="/api/import",          tags=["import"])
app.include_router(mittenti.router,          prefix="/api/mittenti",        tags=["mittenti"])
app.include_router(dipendenti.router,        prefix="/api/dipendenti",      tags=["dipendenti"])
app.include_router(fatture.router,           prefix="/api/fatture",         tags=["fatture"])
app.include_router(cedolini.router,          prefix="/api/cedolini",        tags=["cedolini"])
app.include_router(estratto_conto.router,    prefix="/api/estratto-conto",  tags=["estratto-conto"])
app.include_router(f24.router,               prefix="/api/f24",             tags=["f24"])
app.include_router(f24_privati.router,                                       tags=["f24-privati"])
app.include_router(corrispettivi.router,     prefix="/api/corrispettivi",   tags=["corrispettivi"])
app.include_router(distinte.router,          prefix="/api/distinte",        tags=["distinte"])
app.include_router(verbali.router,           prefix="/api/verbali",         tags=["verbali"])
app.include_router(presenze.router,          prefix="/api/presenze",        tags=["presenze"])
app.include_router(quietanze.router,         prefix="/api/quietanze",       tags=["quietanze"])
app.include_router(alert_fiscali.router,     prefix="/api/alert-fiscali",   tags=["alert-fiscali"])
app.include_router(tributi.router,           prefix="/api/tributi",         tags=["tributi"])
app.include_router(learning.router,          prefix="/api/learning",        tags=["learning"])
app.include_router(fornitori.router,         prefix="/api/fornitori",       tags=["fornitori"])
app.include_router(omaggi_acquaviva.router,                                  tags=["omaggi-acquaviva"])
app.include_router(ordini.router,                                            tags=["ordini"])
app.include_router(prima_nota.router,        prefix="/api/prima-nota",      tags=["prima-nota"])

# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTERS — Tracciabilità (ex ceraldiapp.it, ora locali)
# ═══════════════════════════════════════════════════════════════════════════════
from app.routers import (
    tr_temperature, tr_sanificazione, tr_disinfestazione,
    tr_dashboard, tr_sconti, tr_ordini_fornitori,
)

app.include_router(tr_temperature.router,       prefix="/api/tr",     tags=["tracciabilita"])
app.include_router(tr_sanificazione.router,      prefix="/api/tr",     tags=["tracciabilita"])
app.include_router(tr_disinfestazione.router,    prefix="/api/tr",     tags=["tracciabilita"])
app.include_router(tr_dashboard.router,          prefix="/api/tr",     tags=["tracciabilita"])
app.include_router(tr_sconti.router,             prefix="/api/tr",     tags=["tracciabilita"])
app.include_router(tr_ordini_fornitori.router,   prefix="/api/tr",     tags=["tracciabilita"])

# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTER — Scheduler
# ═══════════════════════════════════════════════════════════════════════════════
from app.routers import scheduler
app.include_router(scheduler.router,             prefix="/api/scheduler", tags=["scheduler"])

# ═══════════════════════════════════════════════════════════════════════════════
#  STATIC FILES (React build)
# ═══════════════════════════════════════════════════════════════════════════════
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(frontend_dist, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.BACKEND_PORT, reload=True)
