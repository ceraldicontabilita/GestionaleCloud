from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import logging
from pathlib import Path

from app.config import settings
from app.menu.routes.qrcode_routes import router as qrcode_router
from app.menu.routes.admin_routes import router as admin_router
from app.menu.routes.allergeni_routes import router as allergeni_router
from app.menu.routes.backup_routes import router as backup_router
from app.menu.routes.menu_routes import router as menu_router
from app.menu.routes.seed_routes import router as seed_router
from app.menu.routes.order_routes import router as order_router
from app.menu.routes.warehouse_routes import router as warehouse_router
from app.menu.routes.sale_routes import router as sale_router
from app.menu.qromo_sync import router as qromo_sync_router
from app.menu.qromo_auto_sync import avvia_sync_qromo_background

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI(title="Menu Ceraldi", version="1.0.0")

# CORS: stesso contratto dell'ERP. Wildcard + credentials e' vietato.
# In produzione Menu e' same-origin sotto gestionalecloud.onrender.com/menu.
app.add_middleware(
    CORSMiddleware,
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_origins=settings.get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Le immagini prodotti sono servite direttamente da Supabase Storage
# (bucket "menu-images", pubblico) — vedi routes/admin_routes.py.

# Routers
app.include_router(qrcode_router)
app.include_router(admin_router)
app.include_router(allergeni_router)
app.include_router(backup_router)
app.include_router(menu_router)
app.include_router(seed_router)
app.include_router(order_router)
app.include_router(warehouse_router)
app.include_router(sale_router)
app.include_router(qromo_sync_router)

# Durante la migrazione Qromo resta la fonte di verita' del menu clienti.
# Il riallineamento parte in background: non rallenta e non blocca l'avvio
# del gestionale, ma aggiorna categorie, prodotti, prezzi, allergeni e foto.
avvia_sync_qromo_background()

# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "menu-ceraldi"}

# ================== Frontend (build React servito dallo stesso servizio) ==================
FRONTEND_BUILD_DIR = Path(__file__).resolve().parents[2] / "frontend_menu" / "build"

if FRONTEND_BUILD_DIR.exists():
    static_assets_dir = FRONTEND_BUILD_DIR / "static"
    if static_assets_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_assets_dir)), name="frontend-static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """Catch-all: serve i file del build React, con fallback a index.html per il routing lato client."""
        if full_path.startswith("api/") or full_path.startswith("uploads/"):
            raise HTTPException(status_code=404)
        candidate = FRONTEND_BUILD_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        index_file = FRONTEND_BUILD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
