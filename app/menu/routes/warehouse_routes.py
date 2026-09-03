from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime

from app.menu.supabase_client import supabase
from app.menu.models.warehouse_models import (
    WarehouseItem, WarehouseItemCreate, WarehouseItemUpdate,
    Movement, MovementCreate, MOVEMENT_TYPES, new_id
)

from app.menu.routes.qrcode_routes import verify_token

router = APIRouter(prefix="/api/warehouse", tags=["Warehouse"])

# Il magazzino del Menu e' collegato direttamente al magazzino bar del
# sistema Lotti/HACCP (stesso progetto Supabase, tabella generica
# lotti_documents). E' un unico magazzino condiviso: le modifiche fatte
# da qui (carico/scarico, modifica, cancellazione) sono visibili anche
# in Lotti, e viceversa.
LOTTI_TABLE = "lotti_documents"
LOTTI_COLLECTION = "magazzino_bar_prodotti"


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


def _get_item_row(item_id: str) -> Optional[dict]:
    res = (
        supabase.table(LOTTI_TABLE)
        .select("*")
        .eq("collection", LOTTI_COLLECTION)
        .eq("doc_id", item_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


@router.get("/items", response_model=List[WarehouseItem])
async def list_items(low_stock_only: bool = False, username: str = Depends(verify_token)):
    res = (
        supabase.table(LOTTI_TABLE)
        .select("*")
        .eq("collection", LOTTI_COLLECTION)
        .execute()
    )
    items = [_row_to_item(r) for r in res.data]
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

    supabase.table(LOTTI_TABLE).insert({
        "collection": LOTTI_COLLECTION,
        "doc_id": item_id,
        "data": data,
        "created_at": now,
        "updated_at": now,
    }).execute()

    row = _get_item_row(item_id)
    return _row_to_item(row)


@router.put("/items/{item_id}", response_model=WarehouseItem)
async def update_item(item_id: str, payload: WarehouseItemUpdate, username: str = Depends(verify_token)):
    row = _get_item_row(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Articolo non trovato")

    data = dict(row.get("data") or {})
    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    if "name" in update_data:
        data["nome"] = update_data["name"]
    if "unit" in update_data:
        data["unita"] = update_data["unit"]
    if "category" in update_data:
        data["categoria"] = update_data["category"]
    if "supplier" in update_data:
        data["fornitore"] = update_data["supplier"]
    if "note" in update_data:
        data["note"] = update_data["note"]
    if "min_threshold" in update_data:
        data["min_threshold"] = update_data["min_threshold"]

    result = (
        supabase.table(LOTTI_TABLE)
        .update({"data": data, "updated_at": _iso(datetime.utcnow())})
        .eq("collection", LOTTI_COLLECTION)
        .eq("doc_id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    return _row_to_item(result.data[0])


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, username: str = Depends(verify_token)):
    result = (
        supabase.table(LOTTI_TABLE)
        .delete()
        .eq("collection", LOTTI_COLLECTION)
        .eq("doc_id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    return {"success": True}


@router.post("/items/{item_id}/movement", response_model=WarehouseItem)
async def register_movement(item_id: str, payload: MovementCreate, username: str = Depends(verify_token)):
    if payload.type not in MOVEMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo movimento non valido")
    if payload.quantity < 0:
        raise HTTPException(status_code=400, detail="La quantità del movimento deve essere positiva")

    row = _get_item_row(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    item = _row_to_item(row)

    if payload.type == "carico":
        new_qty = item["quantity"] + payload.quantity
    elif payload.type == "scarico":
        new_qty = item["quantity"] - payload.quantity
    else:  # rettifica: la quantity passata è il nuovo valore assoluto
        new_qty = payload.quantity

    new_qty = round(new_qty, 3)

    data = dict(row.get("data") or {})
    data["stock"] = new_qty

    supabase.table(LOTTI_TABLE).update({
        "data": data,
        "updated_at": _iso(datetime.utcnow()),
    }).eq("collection", LOTTI_COLLECTION).eq("doc_id", item_id).execute()

    # Storico movimenti: resta nel database del Menu (non modifica i
    # movimenti_lotto di Lotti, che ha una logica propria legata ai lotti HACCP)
    movement = Movement(
        item_id=item_id,
        item_name=item["name"],
        type=payload.type,
        quantity=payload.quantity,
        resulting_quantity=new_qty,
        note=payload.note,
    )
    movement_doc = movement.dict()
    movement_doc['created_at'] = _iso(movement_doc['created_at'])
    supabase.table("menu_warehouse_movements").insert(movement_doc).execute()

    updated_row = _get_item_row(item_id)
    return _row_to_item(updated_row)


@router.get("/movements", response_model=List[Movement])
async def list_movements(item_id: Optional[str] = None, limit: int = 100, username: str = Depends(verify_token)):
    query = supabase.table("menu_warehouse_movements").select("*")
    if item_id:
        query = query.eq("item_id", item_id)
    res = query.order("created_at", desc=True).limit(limit).execute()
    return res.data
