"""Settings router - Application settings management."""
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import base64
import logging

from fastapi import APIRouter, Body, Depends, File, Response, UploadFile

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = PROJECT_ROOT / "frontend" / "public"
LOGO_FILENAMES = ("logo-ceraldi.png", "logo_ceraldi.png")


def _existing_logo_path() -> Optional[Path]:
    """Return the first existing public logo path, if any."""
    for filename in LOGO_FILENAMES:
        candidate = PUBLIC_DIR / filename
        if candidate.exists():
            return candidate
    return None


def _write_logo_files(logo_bytes: bytes) -> None:
    """Keep both supported public logo filenames in sync."""
    try:
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        for filename in LOGO_FILENAMES:
            (PUBLIC_DIR / filename).write_bytes(logo_bytes)
    except Exception as exc:
        logger.warning(f"Impossibile aggiornare file logo pubblico: {exc}")


@router.get(
    "",
    summary="Get settings",
    description="Get application settings"
)
async def get_settings(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get application settings."""
    db = Database.get_db()

    try:
        settings = await db["settings"].find_one(
            {"type": "app_settings"},
            {"_id": 0}
        )
        return settings or {
            "company_name": "Azienda",
            "vat_number": "",
            "fiscal_code": "",
            "address": "",
            "email": "",
            "phone": "",
            "default_vat_rate": 22,
            "currency": "EUR"
        }
    except Exception:
        return {}


@router.get("/logo", summary="Get company logo")
async def get_logo() -> Response:
    """
    Recupera il logo aziendale dal database.
    Restituisce l'immagine direttamente; se manca nel DB usa la copia pubblica.
    """
    db = Database.get_db()

    logo_doc = await db["settings_assets"].find_one(
        {"id": "logo_principale"},
        {"_id": 0}
    )

    if logo_doc and logo_doc.get("data"):
        try:
            logo_bytes = base64.b64decode(logo_doc["data"])
            return Response(
                content=logo_bytes,
                media_type=logo_doc.get("tipo", "image/png"),
                headers={"Cache-Control": "max-age=86400"}
            )
        except Exception as exc:
            logger.warning(f"Logo nel database non leggibile: {exc}")

    public_logo = _existing_logo_path()
    if public_logo:
        try:
            return Response(
                content=public_logo.read_bytes(),
                media_type="image/png",
                headers={"Cache-Control": "max-age=86400"}
            )
        except Exception as exc:
            logger.warning(f"Impossibile leggere logo pubblico: {exc}")

    return Response(status_code=404)


@router.post("/logo", summary="Upload company logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Carica un nuovo logo aziendale nel database.
    Accetta PNG, JPG, SVG e aggiorna anche gli asset pubblici del frontend.
    """
    db = Database.get_db()

    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"]
    if file.content_type not in allowed_types:
        return {"error": f"Tipo file non supportato: {file.content_type}"}

    logo_bytes = await file.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    logo_doc = {
        "id": "logo_principale",
        "nome": file.filename,
        "tipo": file.content_type,
        "dimensione": len(logo_bytes),
        "data": logo_base64,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user.get("user_id")
    }

    await db["settings_assets"].update_one(
        {"id": "logo_principale"},
        {"$set": logo_doc},
        upsert=True
    )

    _write_logo_files(logo_bytes)

    return {
        "success": True,
        "message": "Logo aggiornato",
        "dimensione": len(logo_bytes),
        "nome": file.filename
    }


@router.put(
    "",
    summary="Update settings"
)
async def update_settings(
    settings_data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update application settings."""
    db = Database.get_db()

    settings_data["type"] = "app_settings"
    settings_data["updated_at"] = datetime.now(timezone.utc)
    settings_data["updated_by"] = current_user["user_id"]

    await db["settings"].update_one(
        {"type": "app_settings"},
        {"$set": settings_data},
        upsert=True
    )

    return {"message": "Settings updated"}


@router.get("/user-preferences", summary="Get user preferences")
async def get_user_preferences(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get user-specific preferences from Drive/Sheets."""
    db = Database.get_db()
    prefs = await db["user_preferences"].find_one(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    )
    return prefs or {"user_id": current_user["user_id"], "document_keywords": []}


@router.put("/user-preferences", summary="Update user preferences")
async def update_user_preferences(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Save user preferences to Drive/Sheets."""
    db = Database.get_db()
    data["user_id"] = current_user["user_id"]
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["user_preferences"].update_one(
        {"user_id": current_user["user_id"]},
        {"$set": data},
        upsert=True
    )
    return {"message": "Preferences updated"}
