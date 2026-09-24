from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime
import os
import mimetypes

router = APIRouter(prefix="/api/admin", tags=["Admin Management"])

# Get JWT verification from qrcode_routes
from app.menu.routes.qrcode_routes import verify_token
from app.menu.supabase_client import supabase

# Le immagini caricate dallo staff vengono salvate su Supabase Storage
# (bucket pubblico "menu-images", stesso bucket usato per le immagini migrate
# da Qromo/sito esterno) cosi' da restare disponibili anche dopo un nuovo
# deploy su Render, dove il disco locale del servizio viene azzerato.
STORAGE_BUCKET = "menu-images"
UPLOAD_PREFIX = "uploads"


def _safe_filename(filename: str) -> str:
    """Tiene solo il nome del file, senza eventuali componenti di percorso."""
    return os.path.basename(filename or "immagine")


def _public_url(filename: str) -> str:
    storage_path = f"{UPLOAD_PREFIX}/{filename}"
    return supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    username: str = Depends(verify_token)
):
    """Carica un'immagine su Supabase Storage (persistente tra i deploy)"""
    try:
        filename = _safe_filename(file.filename)
        storage_path = f"{UPLOAD_PREFIX}/{filename}"
        content = await file.read()
        content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        supabase.storage.from_(STORAGE_BUCKET).upload(
            storage_path,
            content,
            {"content-type": content_type, "upsert": "true"}
        )

        image_url = _public_url(filename)

        return {
            "success": True,
            "filename": filename,
            "url": image_url,
            "message": f"Image '{filename}' uploaded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/images")
async def list_images(username: str = Depends(verify_token)):
    """Elenca tutte le immagini caricate dallo staff (Supabase Storage)"""
    try:
        entries = supabase.storage.from_(STORAGE_BUCKET).list(UPLOAD_PREFIX) or []
        images = []
        for entry in entries:
            name = entry.get("name")
            if not name:
                continue
            metadata = entry.get("metadata") or {}
            images.append({
                "filename": name,
                "url": _public_url(name),
                "size": metadata.get("size", 0),
                "uploaded_at": entry.get("created_at") or datetime.utcnow().isoformat()
            })
        images.sort(key=lambda i: i["uploaded_at"], reverse=True)
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/images/{filename}")
async def delete_image(filename: str, username: str = Depends(verify_token)):
    """Elimina un'immagine caricata dallo staff (Supabase Storage)"""
    try:
        filename = _safe_filename(filename)
        storage_path = f"{UPLOAD_PREFIX}/{filename}"
        supabase.storage.from_(STORAGE_BUCKET).remove([storage_path])
        return {"success": True, "message": f"Image '{filename}' deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Tolti GET/PUT /products e POST /associate-image: rispondevano «success»
# senza leggere ne' salvare niente, e nessuna pagina li chiamava. Prodotti e
# immagini si salvano con PUT /api/menu/admin/products/{product_id}.
