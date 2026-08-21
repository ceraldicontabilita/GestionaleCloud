"""Server isolato per il collaudo browser delle operazioni distruttive.

Usa i router reali e un registro Sheets in memoria. Non legge file ``.env`` e
non puo' raggiungere l'archivio di produzione. I dati spariscono alla chiusura.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

# Configurazione deliberatamente fittizia, impostata prima di importare app.*.
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "e2e-isolato-solo-test-non-produzione"
os.environ["ADMIN_EMAIL"] = "e2e@example.invalid"
os.environ["ADMIN_PASSWORD"] = "e2e-password-solo-test"
os.environ["GESTIONE_RISERVATA_CODE"] = "00000000"
os.environ.pop("ADMIN_PASSWORD_HASH", None)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from app.services.sheets_document_store import MemorySheetsClient  # noqa: E402

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
    client = MemorySheetsClient()
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
    await Database.db["invoices"].insert_many([
        {
            "id": "e2e-fattura-a",
            "invoice_number": "E2E-001",
            "invoice_date": "2026-08-08",
            "document_type": "TD01",
            "supplier_name": "Fornitore E2E Alfa",
            "supplier_vat": "00000000001",
            "taxable_amount": 100.00,
            "vat_amount": 22.00,
            "total_amount": 122.00,
            "status": "imported",
        },
        {
            "id": "e2e-fattura-b",
            "invoice_number": "E2E-002",
            "invoice_date": "2026-08-07",
            "document_type": "TD01",
            "supplier_name": "Fornitore E2E Beta",
            "supplier_vat": "00000000002",
            "taxable_amount": 200.00,
            "vat_amount": 44.00,
            "total_amount": 244.00,
            "status": "imported",
        },
        {
            "id": "e2e-nota-credito",
            "invoice_number": "NC-E2E-001",
            "invoice_date": "2026-08-06",
            "document_type": "TD04",
            "supplier_name": "Fornitore E2E Gamma",
            "supplier_vat": "00000000003",
            "taxable_amount": 50.00,
            "vat_amount": 11.00,
            "total_amount": 61.00,
            "status": "imported",
        },
    ])
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


@app.get("/api/system/lock-status")
async def system_lock_status():
    """Replica il contratto read-only esposto dall'applicazione reale.

    Il collaudo delle pagine deve usare gli stessi endpoint del deploy, anche
    quando il server isolato non importa ``app.main`` per evitare bootstrap e
    connessioni esterne. Lo stato deriva dal lock reale del router Documenti.
    """
    from app.routers.documenti import get_current_operation, is_email_operation_running

    locked = is_email_operation_running()
    return {
        "email_locked": locked,
        "operation": get_current_operation(),
        "can_start_email_operation": not locked,
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
