from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List, Optional
from datetime import datetime
import os
import mimetypes
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin", tags=["Admin Management"])

# Get JWT verification from qrcode_routes
import sys
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


class Product(BaseModel):
    id: int
    name: str
    nameIT: str
    price: str
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: List[str] = []
    image: Optional[str] = None
    category_id: int
    subcategory_id: int

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    nameIT: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    descriptionIT: Optional[str] = None
    allergens: Optional[List[str]] = None
    image: Optional[str] = None

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

@router.get("/products")
async def get_all_products():
    """Get all products from menu (public endpoint) — vedi /api/menu per la gestione reale."""
    return {
        "message": "I prodotti sono gestiti tramite /api/menu (Supabase)",
    }

@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    product: ProductUpdate,
    username: str = Depends(verify_token)
):
    """Deprecato: usare PUT /api/menu/admin/products/{product_id}"""
    return {
        "success": True,
        "message": "Usare PUT /api/menu/admin/products/{product_id} per aggiornare i prodotti",
    }

@router.post("/associate-image")
async def associate_image(
    product_id: int = Form(...),
    image_filename: str = Form(...),
    username: str = Depends(verify_token)
):
    """Restituisce l'URL pubblico di un'immagine gia' caricata, da salvare sul prodotto."""
    try:
        filename = _safe_filename(image_filename)
        image_url = _public_url(filename)

        return {
            "success": True,
            "product_id": product_id,
            "image_url": image_url,
            "message": "Image associated with product",
            "note": "Usare PUT /api/menu/admin/products/{product_id} per salvare l'immagine sul prodotto"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
