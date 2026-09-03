from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime

from app.menu.supabase_client import supabase
from app.menu.models.order_models import (
    Order, OrderCreate, OrderStatusUpdate, OrderPaymentUpdate,
    ORDER_STATUSES, compute_total
)

from app.menu.routes.qrcode_routes import verify_token

router = APIRouter(prefix="/api/orders", tags=["Orders"])


def order_out(row: dict) -> dict:
    """Mappa la riga DB (colonna table_name) sul modello Order (campo table)."""
    row = dict(row)
    row['table'] = row.pop('table_name', None)
    return row


def order_in(doc: dict) -> dict:
    """Mappa il modello Order (campo table) sulla riga DB (colonna table_name)."""
    doc = dict(doc)
    doc['table_name'] = doc.pop('table', None)
    if isinstance(doc.get('created_at'), datetime):
        doc['created_at'] = doc['created_at'].isoformat()
    if isinstance(doc.get('updated_at'), datetime):
        doc['updated_at'] = doc['updated_at'].isoformat()
    return doc


# ================== PUBLIC ==================

@router.post("/", response_model=Order)
async def create_order(payload: OrderCreate):
    """Crea un nuovo ordine (dal menu digitale del cliente o dal banco/cassa)."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="L'ordine deve contenere almeno un prodotto")

    sala_nome = None
    totale_coperto = 0.0
    if payload.sala_id:
        sala_res = supabase.table("menu_sale").select("*").eq("id", payload.sala_id).limit(1).execute()
        if not sala_res.data:
            raise HTTPException(status_code=404, detail="Sala non trovata")
        sala = sala_res.data[0]
        if not sala.get("ordini_abilitati", True):
            raise HTTPException(status_code=400, detail=f"Gli ordini non sono al momento abilitati per la sala \"{sala['nome']}\"")
        sala_nome = sala["nome"]
        if (
            payload.source == "cliente"
            and sala.get("disabilita_contanti_qr")
            and payload.payment_method == "contanti"
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Il pagamento in contanti non è disponibile per gli ordini QR nella sala \"{sala['nome']}\". Scegli un altro metodo di pagamento."
            )
        if sala.get("coperto_attivo") and sala.get("coperto_importo"):
            coperti = payload.numero_coperti or 1
            totale_coperto = round(float(sala["coperto_importo"]) * coperti, 2)

    order = Order(
        items=payload.items,
        table=payload.table,
        customer_name=payload.customer_name,
        note=payload.note,
        source=payload.source,
        paid=payload.paid,
        payment_method=payload.payment_method,
        sala_id=payload.sala_id,
        sala_nome=sala_nome,
        numero_coperti=payload.numero_coperti,
        totale_coperto=totale_coperto,
    )
    order.total = round(compute_total(payload.items) + totale_coperto, 2)

    doc = order.dict()
    doc['items'] = [i if isinstance(i, dict) else i.dict() for i in order.items]
    row = order_in(doc)
    supabase.table("menu_orders").insert(row).execute()
    return order_out(row)


@router.get("/{order_id}", response_model=Order)
async def get_order(order_id: str):
    """Stato di un singolo ordine (usato dal cliente per seguire il proprio ordine)."""
    res = supabase.table("menu_orders").select("*").eq("id", order_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return order_out(res.data[0])


# ================== PROTETTI (staff) ==================

@router.get("/", response_model=List[Order])
async def list_orders(status: Optional[str] = None, active_only: bool = False, username: str = Depends(verify_token)):
    """Elenco ordini, opzionalmente filtrato per stato o solo attivi (non completati/annullati)."""
    query = supabase.table("menu_orders").select("*")
    if status:
        if status not in ORDER_STATUSES:
            raise HTTPException(status_code=400, detail="Stato non valido")
        query = query.eq("status", status)
    elif active_only:
        query = query.not_.in_("status", ["completato", "annullato"])

    res = query.order("created_at").limit(500).execute()
    return [order_out(r) for r in res.data]


@router.patch("/{order_id}/status", response_model=Order)
async def update_order_status(order_id: str, payload: OrderStatusUpdate, username: str = Depends(verify_token)):
    if payload.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Stato non valido")

    result = supabase.table("menu_orders").update({
        "status": payload.status,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", order_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return order_out(result.data[0])


@router.patch("/{order_id}/payment", response_model=Order)
async def update_order_payment(order_id: str, payload: OrderPaymentUpdate, username: str = Depends(verify_token)):
    result = supabase.table("menu_orders").update({
        "paid": payload.paid,
        "payment_method": payload.payment_method,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", order_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return order_out(result.data[0])


@router.delete("/{order_id}")
async def delete_order(order_id: str, username: str = Depends(verify_token)):
    result = supabase.table("menu_orders").delete().eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return {"success": True}
