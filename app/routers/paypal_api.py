from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse
from datetime import datetime, timezone
from typing import Dict, Any
import os

from app.database import Database
from app.services.paypal_api_sync import sync_paypal_period

router = APIRouter(prefix="/paypal-api", tags=["paypal-api"])


@router.post("/sync")
async def sync_period(body: Dict[str, Any] = Body(...)):
    try:
        start = datetime.fromisoformat(body["start_date"]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(body["end_date"]).replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"Formato data non valido: {e}")

    db = Database.get_db()
    result = await sync_paypal_period(db, start, end)
    return result


@router.post("/sync/month")
async def sync_current_month():
    from calendar import monthrange
    now = datetime.now(timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(day=last_day, hour=23, minute=59, second=59)

    db = Database.get_db()
    return await sync_paypal_period(db, start, end)


@router.get("/status")
async def status():
    db = Database.get_db()
    total = await db["paypal_transactions"].count_documents({})
    enriched = await db["paypal_transactions"].count_documents({"source": "paypal_api"})
    pagopa = await db["paypal_transactions"].count_documents({"is_pagopa": True})

    last = await db["paypal_transactions"].find_one(
        {"source": "paypal_api"},
        sort=[("enriched_at", -1)],
        projection={"_id": 0, "enriched_at": 1},
    )
    return {
        "total_transazioni": total,
        "arricchite_da_api": enriched,
        "identificate_pagopa": pagopa,
        "ultimo_sync": last.get("enriched_at") if last else None,
    }


@router.post("/riconcilia")
async def riconcilia_da_collection(body: Dict[str, Any] = Body(default={})):
    """
    FASE 2: riconciliazione unificata che processa in sequenza:
    1. Multe PagoPA → verbali_noleggio
    2. Fatture commerciali → invoices (match by paypal_account_id)
    3. Allineamento paypal_transactions ↔ estratto_conto_movimenti
    """
    from app.services.paypal_riconciliazione import (
        riconcilia_pagamenti_paypal,
        riconcilia_multe_pagopa,
        collega_a_estratto_conto,
    )

    db = Database.get_db()
    q: Dict[str, Any] = {"importo": {"$lt": 0}}
    if body.get("start_date"):
        q["initiation_date"] = {"$gte": body["start_date"]}
    if body.get("end_date"):
        q.setdefault("initiation_date", {})["$lte"] = body["end_date"] + "T23:59:59Z"

    txs = await db["paypal_transactions"].find(q, {"_id": 0}).to_list(5000)
    multe = [t for t in txs if t.get("is_pagopa")]
    fatture = [t for t in txs if not t.get("is_pagopa")]

    r_multe = await riconcilia_multe_pagopa(db, multe)
    r_fatt = await riconcilia_pagamenti_paypal(db, [
        {
            "data": (t.get("initiation_date") or "")[:10],
            "beneficiario": t.get("paypal_account_id", "") or t.get("transaction_subject", ""),
            "paypal_account_id": t.get("paypal_account_id"),
            "importo": t.get("importo", 0),
            "codice_transazione": t.get("transaction_id"),
        }
        for t in fatture
    ])
    r_banca = await collega_a_estratto_conto(db)
    return {"multe_pagopa": r_multe, "fatture": r_fatt, "banca": r_banca}


@router.get("/ricevuta-pdf/{transaction_id}")
async def scarica_ricevuta_pdf(transaction_id: str):
    from app.services.paypal_pdf_fetcher import (
        fetch_ricevuta_pagopa,
        genera_pdf_transazione_paypal,
    )
    db = Database.get_db()
    tx = await db["paypal_transactions"].find_one({"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(404, "Transazione non trovata")
    pdf_path = tx.get("pdf_ricevuta_path") or tx.get("pdf_generato_path")
    if not pdf_path or not os.path.exists(pdf_path):
        if tx.get("is_pagopa"):
            r = await fetch_ricevuta_pagopa(
                db, transaction_id,
                abs(tx.get("importo", 0)),
                tx.get("initiation_date", ""),
            )
            pdf_path = r["pdf_path"] if r else None
        if not pdf_path:
            pdf_path = await genera_pdf_transazione_paypal(db, transaction_id)
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(404, "PDF non disponibile")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"ricevuta_paypal_{transaction_id}.pdf",
    )
