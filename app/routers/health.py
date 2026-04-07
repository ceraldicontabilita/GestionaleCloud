"""Health check endpoint."""
from fastapi import APIRouter
from app.database import Database
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    db_ok = False
    try:
        db = Database.get_db()
        await db.command("ping")
        db_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if db_ok else "disconnected",
    }
