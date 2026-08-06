"""Server isolato per il collaudo browser delle operazioni distruttive.

Usa i router reali dell'applicazione e MongoDB in memoria. Non legge file
``.env``, non conosce URI Atlas e non puo' raggiungere il database di
produzione. I dati vengono creati all'avvio e spariscono alla chiusura.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

# Configurazione deliberatamente fittizia, impostata prima di importare app.*.
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "e2e-isolato-solo-test-non-produzione"
os.environ["MONGO_URL"] = "mongodb://non-usato.invalid/e2e"
os.environ["MONGODB_ATLAS_URI"] = "mongodb://non-usato.invalid/e2e"
os.environ["DB_NAME"] = "Gestionale_E2E_Distruttivo"
os.environ["ADMIN_EMAIL"] = "e2e@example.invalid"
os.environ["ADMIN_PASSWORD"] = "e2e-password-solo-test"
os.environ["GESTIONE_RISERVATA_CODE"] = "00000000"
os.environ.pop("ADMIN_PASSWORD_HASH", None)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.middleware.authentication import AuthenticationMiddleware  # noqa: E402
from app.middleware.error_handler import add_exception_handlers  # noqa: E402
from app.router_registry import register_all_routers  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
# Consente di collaudare un build fresco fuori dal repository. In questo modo
# l'E2E non sporca ``frontend/dist`` e non rischia di confondere artefatti
# generati con modifiche sorgente da pubblicare.
DIST = Path(
    os.environ.get("E2E_FRONTEND_DIST", str(ROOT / "frontend" / "dist"))
).resolve()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    client = AsyncMongoMockClient()
    Database.client = client
    Database.db = client["Gestionale_E2E_Distruttivo"]
    await Database.db["notifiche_scadenze"].insert_one(
        {
            "id": "e2e-scadenza-da-eliminare",
            "data_scadenza": "2026-12-15",
            "descrizione": "COLLAUDO E2E - cancellami",
            "tipo": "CUSTOM",
            "importo": 123.45,
            "priorita": "media",
            "completata": False,
        }
    )
    await Database.db["learning_rules"].insert_one(
        {"id": "e2e-regola-protetta", "pattern": "solo test"}
    )
    yield
    client.close()
    Database.client = None
    Database.db = None


app = FastAPI(title="GestionaleCloud E2E isolato", lifespan=lifespan)
app.add_middleware(AuthenticationMiddleware)
add_exception_handlers(app)
register_all_routers(app)


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "database": "connected" if Database.db is not None else "disconnected",
        "environment": "e2e-isolato",
        "version": settings.APP_VERSION,
    }


if not DIST.is_dir():
    raise RuntimeError("frontend/dist assente: eseguire prima il build frontend")

assets = DIST / "assets"
if assets.is_dir():
    app.mount("/assets", StaticFiles(directory=assets), name="e2e-assets")


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
async def serve_frontend(request: Request, full_path: str):
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse({"detail": "Not found"}, status_code=404)
    candidate = (DIST / full_path).resolve()
    if candidate.is_file() and DIST.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
