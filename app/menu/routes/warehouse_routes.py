from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime

from app.menu.supabase_client import supabase
from app.lotti.db import database as lotti_db
from app.lotti.routers.magazzino_bar import applica_movimento_stock
from app.menu.models.warehouse_models import (
    WarehouseItem, WarehouseItemCreate, WarehouseItemUpdate,
    Movement, MovementCreate, MOVEMENT_TYPES, new_id
)

from app.menu.routes.qrcode_routes import verify_token
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/warehouse", tags=["Warehouse"])

# Lotti possiede prodotti e movimenti. Il Menu usa il document store canonico
# tramite RPC, senza accedere alla vecchia tabella pubblica di staging.


def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _row_to_item(row: dict) -> dict:
    """Mappa un documento lotti_documents (collection=magazzino_bar_prodotti) su WarehouseItem."""
    data = row.get("data") or {}
    quantity = data.get("stock", 0)
    try:
        quantity = float(quantity) if quantity is not None else 0
    except (TypeError, ValueError):
        quantity = 0
    min_threshold = data.get("min_threshold")
    if min_threshold is not None:
        try:
            min_threshold = float(min_threshold)
        except (TypeError, ValueError):
            min_threshold = None
    return {
        "id": row["doc_id"],
        "name": data.get("nome") or data.get("name") or "(senza nome)",
        "unit": data.get("unita") or data.get("unit") or "pz",
        "quantity": quantity,
        "min_threshold": min_threshold,
        "category": data.get("categoria") or data.get("category"),
        "supplier": data.get("fornitore") or data.get("supplier"),
        "note": data.get("note"),
        "updated_at": row.get("updated_at") or row.get("created_at") or _iso(datetime.utcnow()),
    }


def _document_to_row(doc: dict) -> dict:
    return {"doc_id": str(doc.get("id") or doc.get("_id")), "data": doc,
            "updated_at": doc.get("updated_at"), "created_at": doc.get("created_at")}


async def _get_item_row(item_id: str) -> Optional[dict]:
    doc = await lotti_db.magazzino_bar_prodotti.find_one({"id": item_id})
    if not doc:
        doc = await lotti_db.magazzino_bar_prodotti.find_one({"_id": item_id})
    return _document_to_row(doc) if doc else None


@router.get("/items", response_model=List[WarehouseItem])
async def list_items(low_stock_only: bool = False, username: str = Depends(verify_token)):
    docs = await lotti_db.magazzino_bar_prodotti.find({}).to_list(20000)
    items = [_row_to_item(_document_to_row(doc)) for doc in docs]
    items.sort(key=lambda i: (i["name"] or "").lower())
    if low_stock_only:
        items = [i for i in items if i.get("min_threshold") is not None and i["quantity"] <= i["min_threshold"]]
    return items


@router.post("/items", response_model=WarehouseItem)
async def create_item(payload: WarehouseItemCreate, username: str = Depends(verify_token)):
    item_id = new_id()
    now = _iso(datetime.utcnow())
    data = {
        "nome": payload.name,
        "unita": payload.unit,
        "stock": payload.quantity,
        "categoria": payload.category,
        "fornitore": payload.supplier,
        "note": payload.note,
    }
    if payload.min_threshold is not None:
        data["min_threshold"] = payload.min_threshold

    data.update(id=item_id, stock=0, created_at=now, updated_at=now)
    await lotti_db.magazzino_bar_prodotti.insert_one(data)
    if payload.quantity:
        await applica_movimento_stock(data, payload.quantity, "carico", username,
                                      "Giacenza iniziale da Menu", {"origine": "menu"})
    return _row_to_item(await _get_item_row(item_id))


@router.put("/items/{item_id}", response_model=WarehouseItem)
async def update_item(item_id: str, payload: WarehouseItemUpdate, username: str = Depends(verify_token)):
    row = await _get_item_row(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Articolo non trovato")

    fields = {"name": "nome", "unit": "unita", "category": "categoria",
              "supplier": "fornitore", "note": "note", "min_threshold": "min_threshold"}
    updates = {fields[k]: v for k, v in payload.dict().items() if v is not None}
    updates["updated_at"] = _iso(datetime.utcnow())
    await lotti_db.magazzino_bar_prodotti.update_one(
        {"_id": row["data"].get("_id", item_id)}, {"$set": updates})
    return _row_to_item(await _get_item_row(item_id))


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, username: str = Depends(verify_token)):
    row = await _get_item_row(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    await lotti_db.magazzino_bar_prodotti.delete_one({"_id": row["data"].get("_id", item_id)})
    return {"success": True}


@router.post("/items/{item_id}/movement", response_model=WarehouseItem)
async def register_movement(item_id: str, payload: MovementCreate, username: str = Depends(verify_token)):
    if payload.type not in MOVEMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo movimento non valido")
    if payload.quantity < 0:
        raise HTTPException(status_code=400, detail="La quantità del movimento deve essere positiva")

    row = await _get_item_row(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    item = _row_to_item(row)

    delta = (payload.quantity if payload.type == "carico" else
             -payload.quantity if payload.type == "scarico" else
             payload.quantity - item["quantity"])
    prod = dict(row["data"])
    prod.setdefault("id", item_id)
    prod.setdefault("nome", item["name"])
    await applica_movimento_stock(prod, delta, payload.type, username,
                                  payload.note or "", {"origine": "menu"})
    return _row_to_item(await _get_item_row(item_id))


@router.get("/movements", response_model=List[Movement])
async def list_movements(item_id: Optional[str] = None, limit: int = 100, username: str = Depends(verify_token)):
    query = supabase.table("menu_warehouse_movements").select("*")
    if item_id:
        query = query.eq("item_id", item_id)
    res = (await run_in_threadpool(query.order("created_at", desc=True).limit(limit).execute))
    # Conserva lo storico Menu precedente; i nuovi movimenti hanno un solo
    # writer e si leggono dal registro canonico Lotti.
    docs = await lotti_db.magazzino_bar_movimenti.find(
        {"prodotto_id": item_id} if item_id else {}).sort("data", -1).to_list(max(1, min(limit, 1000)))
    canonical = [{"id": str(d.get("id") or d.get("_id")),
                  "item_id": d["prodotto_id"], "item_name": d.get("prodotto_nome", ""),
                  "type": d["tipo"], "quantity": d.get("quantita", 0),
                  "resulting_quantity": d.get("stock_dopo", 0),
                  "note": d.get("nota"), "created_at": d["data"]} for d in docs]
    combined = {str(d["id"]): d for d in [*res.data, *canonical]}
    return sorted(combined.values(), key=lambda d: str(d["created_at"]), reverse=True)[:max(1, min(limit, 1000))]
