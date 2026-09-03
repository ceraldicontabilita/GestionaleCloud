from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime

from app.menu.supabase_client import supabase
from app.menu.models.sale_models import Sala, SalaCreate, SalaUpdate

from app.menu.routes.qrcode_routes import verify_token

router = APIRouter(prefix="/api/sale", tags=["Sale"])


def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt


# Pubblico: usato dal menu digitale/QR per sapere se una sala accetta ordini
@router.get("/", response_model=List[Sala])
async def list_sale():
    res = supabase.table("menu_sale").select("*").order("nome").execute()
    return res.data


@router.get("/{sala_id}", response_model=Sala)
async def get_sala(sala_id: str):
    res = supabase.table("menu_sale").select("*").eq("id", sala_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Sala non trovata")
    return res.data[0]


# Protetti: gestione sale riservata allo staff
@router.post("/", response_model=Sala)
async def create_sala(payload: SalaCreate, username: str = Depends(verify_token)):
    sala = Sala(**payload.dict())
    doc = sala.dict()
    doc['created_at'] = _iso(doc['created_at'])
    doc['updated_at'] = _iso(doc['updated_at'])
    supabase.table("menu_sale").insert(doc).execute()
    return doc


@router.put("/{sala_id}", response_model=Sala)
async def update_sala(sala_id: str, payload: SalaUpdate, username: str = Depends(verify_token)):
    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    update_data["updated_at"] = _iso(datetime.utcnow())
    result = supabase.table("menu_sale").update(update_data).eq("id", sala_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Sala non trovata")
    return result.data[0]


@router.delete("/{sala_id}")
async def delete_sala(sala_id: str, username: str = Depends(verify_token)):
    result = supabase.table("menu_sale").delete().eq("id", sala_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Sala non trovata")
    return {"success": True}
