"""
Sincronizzazione paypal_transactions da API Reporting.
Upsert per transaction_id, enrichment dei campi mancanti.
"""
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.paypal_api_client import paypal_client

logger = logging.getLogger(__name__)

COLL = "paypal_transactions"

PAGOPA_CUSTOM_PATTERN = re.compile(r'^E\d{13}[A-Za-z0-9]{3,4}$')
PAGOPA_IUV_PATTERN = re.compile(r'\b0\d{17}\b')


def extract_enriched_fields(tx: Dict[str, Any]) -> Dict[str, Any]:
    info = tx.get("transaction_info", {})
    amount = info.get("transaction_amount", {}) or {}
    shipping = info.get("shipping_amount", {}) or {}

    custom = info.get("custom_field", "")
    subject = info.get("transaction_subject", "")
    invoice = info.get("invoice_id", "")

    is_pagopa = bool(
        PAGOPA_CUSTOM_PATTERN.match(custom or "") or
        PAGOPA_IUV_PATTERN.search(f"{subject} {invoice}")
    )

    importo_f = float(amount.get("value") or 0)
    init_date = info.get("transaction_initiation_date") or ""
    # Data ISO (YYYY-MM-DD) per compatibilità con gli altri endpoint PayPal
    data_iso = init_date[:10] if init_date else None

    # Estrai nome_controparte dal payer_info / shipping_info
    payer_info = tx.get("payer_info", {}) or {}
    shipping_info = tx.get("shipping_info", {}) or {}
    payer_name = payer_info.get("payer_name", {}) or {}
    nome_controparte = (
        payer_name.get("alternate_full_name")
        or payer_name.get("full_name")
        or f"{payer_name.get('given_name', '')} {payer_name.get('surname', '')}".strip()
        or shipping_info.get("name")
        or info.get("transaction_subject")
        or ""
    )

    return {
        "transaction_id": info.get("transaction_id"),
        "paypal_account_id": info.get("paypal_account_id"),
        "paypal_reference_id": info.get("paypal_reference_id"),
        "reference_id_type": info.get("paypal_reference_id_type"),
        "event_code": info.get("transaction_event_code"),
        # Campi usati dai listing:
        "data": data_iso,
        "data_operazione": init_date,
        "lordo": importo_f,  # alias compatibile
        "importo": importo_f,
        "tipo": info.get("transaction_event_code"),
        "nome_controparte": nome_controparte.strip(),
        "currency": amount.get("currency_code"),
        "shipping_amount": float(shipping.get("value") or 0),
        "invoice_id_fornitore": invoice or None,
        "custom_field": custom or None,
        "transaction_subject": subject or None,
        "transaction_note": info.get("transaction_note"),
        "initiation_date": init_date,
        "is_pagopa": is_pagopa,
        "instrument_type": info.get("instrument_type"),
        "instrument_sub_type": info.get("instrument_sub_type"),
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "source": "paypal_api",
    }


async def sync_paypal_period(
    db: AsyncIOMotorDatabase,
    start: datetime,
    end: datetime,
) -> Dict[str, int]:
    tx_list = await paypal_client.sync_period(start, end)

    upserted = 0
    enriched = 0
    for tx in tx_list:
        doc = extract_enriched_fields(tx)
        if not doc.get("transaction_id"):
            continue
        res = await db[COLL].update_one(
            {"transaction_id": doc["transaction_id"]},
            {"$set": doc},
            upsert=True,
        )
        upserted += 1
        if res.upserted_id or res.modified_count:
            enriched += 1

    logger.info("Sync PayPal %s -> %s: %d transazioni, %d arricchite",
                start.date(), end.date(), upserted, enriched)
    return {"total": upserted, "enriched": enriched,
            "period_start": start.isoformat(), "period_end": end.isoformat()}
