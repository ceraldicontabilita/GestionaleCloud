"""Magazzino Menu: proiezione del magazzino bar canonico Lotti.

Nessun accesso diretto alla vecchia public.lotti_documents e nessun secondo
motore di stock: persistenza RPC e movimenti sono quelli dell'app Lotti.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.lotti.db import database as db
from app.lotti.routers.magazzino_bar import (
    NuovoProdotto, applica_movimento_stock, crea_prodotto,
)
from app.menu.models.warehouse_models import (
    WarehouseItem, WarehouseItemCreate, WarehouseItemUpdate,
    Movement, MovementCreate, MOVEMENT_TYPES,
)
from app.menu.routes.qrcode_routes import verify_token

router = APIRouter(prefix="/api/warehouse", tags=["Warehouse"])


def _item(doc: dict) -> dict:
    return {
        "id": str(doc["id"]),
        "name": doc.get("nome") or doc.get("name") or "(senza nome)",
        "unit": doc.get("unita") or doc.get("unit") or "pz",
        "quantity": float(doc.get("stock") or 0),
        "min_threshold": doc.get("soglia_minima", doc.get("min_threshold")),
        "category": doc.get("categoria"),
        "supplier": doc.get("fornitore"),
        "note": doc.get("note"),
        "updated_at": doc.get("updated_at") or doc.get("created_at") or datetime.now(timezone.utc),
    }


async def _get_item(item_id: str) -> dict:
    doc = await db.magazzino_bar_prodotti.find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    return doc


@router.get("/items", response_model=List[WarehouseItem])
async def list_items(low_stock_only: bool = False, username: str = Depends(verify_token)):
    items = [_item(doc) async for doc in db.magazzino_bar_prodotti.find({}, {"_id": 0})]
    items.sort(key=lambda item: item["name"].lower())
    if low_stock_only:
        items = [item for item in items if item["min_threshold"] is not None
                 and item["quantity"] <= item["min_threshold"]]
    return items


@router.post("/items", response_model=WarehouseItem)
async def create_item(payload: WarehouseItemCreate, username: str = Depends(verify_token)):
    doc = await crea_prodotto(NuovoProdotto(
        nome=payload.name, categoria=payload.category or "",
        fornitore=payload.supplier or "", unita=payload.unit,
    ), _admin={"username": username})
    await db.magazzino_bar_prodotti.update_one({"id": doc["id"]}, {"$set": {
        "soglia_minima": payload.min_threshold, "note": payload.note,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    if payload.quantity:
        await applica_movimento_stock(
            doc, payload.quantity, "carico", username, payload.note or "",
            extra={"canale": "menu"},
        )
    return _item(await _get_item(doc["id"]))


@router.put("/items/{item_id}", response_model=WarehouseItem)
async def update_item(item_id: str, payload: WarehouseItemUpdate, username: str = Depends(verify_token)):
    await _get_item(item_id)
    mapping = {"name": "nome", "unit": "unita", "category": "categoria",
               "supplier": "fornitore", "note": "note", "min_threshold": "soglia_minima"}
    fields = {mapping[key]: value for key, value in payload.model_dump(exclude_unset=True).items()}
    if fields.get("nome") is None and "nome" in fields:
        raise HTTPException(422, "Il nome non può essere vuoto")
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.magazzino_bar_prodotti.update_one({"id": item_id}, {"$set": fields})
    return _item(await _get_item(item_id))


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, username: str = Depends(verify_token)):
    await _get_item(item_id)
    await db.magazzino_bar_prodotti.delete_one({"id": item_id})
    return {"success": True}


@router.post("/items/{item_id}/movement", response_model=WarehouseItem)
async def register_movement(item_id: str, payload: MovementCreate, username: str = Depends(verify_token)):
    if payload.type not in MOVEMENT_TYPES:
        raise HTTPException(400, "Tipo movimento non valido")
    doc = await _get_item(item_id)
    current = float(doc.get("stock") or 0)
    delta = (payload.quantity if payload.type == "carico" else
             -payload.quantity if payload.type == "scarico" else payload.quantity - current)
    await applica_movimento_stock(
        doc, delta, payload.type, username, payload.note or "",
        extra={"canale": "menu", "quantita_richiesta": payload.quantity},
    )
    return _item(await _get_item(item_id))


@router.get("/movements", response_model=List[Movement])
async def list_movements(item_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
                        username: str = Depends(verify_token)):
    query = {"prodotto_id": item_id} if item_id else {}
    docs = await db.magazzino_bar_movimenti.find(query, {"_id": 0}).sort("data", -1).to_list(limit)
    return [{
        "id": doc["id"], "item_id": doc["prodotto_id"],
        "item_name": doc.get("prodotto_nome") or "(senza nome)",
        "type": doc["tipo"], "quantity": doc.get("quantita_richiesta", doc["quantita"]),
        "resulting_quantity": doc["stock_dopo"], "note": doc.get("nota"),
        "created_at": doc["data"],
    } for doc in docs]
