"""
Sincronizzazione paypal_transactions da API Reporting.
Upsert per transaction_id, enrichment dei campi mancanti.
"""
import re
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from app.services.sheets_document_store import SheetDatabase
from app.services.sheets_document_store import ReturnRecord

from app.services.paypal_api_client import paypal_client
from app.services.payment_allocation_validator import to_cents

logger = logging.getLogger(__name__)

COLL = "paypal_transactions"
CHECKPOINT_COLL = "paypal_sync_checkpoints"

PAGOPA_CUSTOM_PATTERN = re.compile(r'^E\d{13}[A-Za-z0-9]{3,4}$')
PAGOPA_IUV_PATTERN = re.compile(r'\b0\d{17}\b')


def extract_enriched_fields(tx: Dict[str, Any]) -> Dict[str, Any]:
    info = tx.get("transaction_info", {})
    amount = info.get("transaction_amount", {}) or {}
    settlement = (
        info.get("settlement_amount")
        or info.get("converted_transaction_amount")
        or {}
    )
    fee = info.get("fee_amount", {}) or {}
    shipping = info.get("shipping_amount", {}) or {}

    custom = info.get("custom_field", "")
    subject = info.get("transaction_subject", "")
    invoice = info.get("invoice_id", "")

    is_pagopa = bool(
        PAGOPA_CUSTOM_PATTERN.match(custom or "") or
        PAGOPA_IUV_PATTERN.search(f"{subject} {invoice}")
    )

    importo_cents = to_cents(amount.get("value") or 0)
    settlement_cents = to_cents(settlement.get("value")) if settlement else None
    fee_cents = to_cents(fee.get("value")) if fee else 0
    shipping_cents = to_cents(shipping.get("value") or 0)
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
        "transaction_event_code": info.get("transaction_event_code"),
        "transaction_status": info.get("transaction_status"),
        "bank_reference_id": info.get("bank_reference_id"),
        "balance_affecting": info.get("balance_affecting"),
        # Campi usati dai listing:
        "data": data_iso,
        "data_operazione": init_date,
        "importo_cents": importo_cents,
        "gross_amount_cents": importo_cents,
        "gross_amount": importo_cents / 100,
        "gross_currency": amount.get("currency_code"),
        "settlement_amount_cents": settlement_cents,
        "settlement_amount": settlement_cents / 100 if settlement_cents is not None else None,
        "settlement_currency": settlement.get("currency_code") if settlement else None,
        "fee_amount_cents": fee_cents,
        "fee_amount": fee_cents / 100,
        "fee_currency": fee.get("currency_code") if fee else None,
        "lordo": importo_cents / 100,  # alias compatibile
        "importo": importo_cents / 100,
        "tipo": info.get("transaction_event_code"),
        "nome_controparte": nome_controparte.strip(),
        "email_controparte": payer_info.get("email_address"),
        "currency": amount.get("currency_code"),
        "shipping_amount_cents": shipping_cents,
        "shipping_amount": shipping_cents / 100,
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
    db: SheetDatabase,
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
        # PayPal puo' restituire per lo stesso transaction_id una riga che
        # incide sul saldo e una riga solo informativa. Il database operativo
        # conserva esclusivamente quella balance-affecting: evita duplicati e
        # mantiene transaction_id come chiave stabile usata da link e UI.
        balance_affecting = doc.get("balance_affecting")
        if balance_affecting is False or str(balance_affecting or "").upper() in {
            "N", "NO", "FALSE",
        }:
            continue
        reporting_key = "|".join(str(doc.get(key) or "") for key in (
            "transaction_id", "transaction_event_code", "transaction_status",
            "importo_cents", "currency", "initiation_date", "paypal_reference_id",
            "balance_affecting",
        ))
        doc["paypal_reporting_key"] = reporting_key
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


async def sync_paypal_incremental(db: SheetDatabase) -> Dict[str, Any]:
    """Acquisisce solo l'intervallo successivo al checkpoint persistito.

    Un lease breve impedisce che due aperture contemporanee della pagina
    avviino lo stesso intervallo. L'upsert per transaction_id resta la seconda
    barriera idempotente.
    """
    now = datetime.now(timezone.utc)
    checkpoint_id = "paypal_default_account"
    lease_id = str(uuid.uuid4())
    lease_until = now + timedelta(minutes=5)
    # Crea il checkpoint una volta; l'acquisizione del lease successiva e'
    # atomica. Due aperture contemporanee non possono quindi elaborare lo
    # stesso intervallo.
    await db[CHECKPOINT_COLL].update_one(
        {"id": checkpoint_id},
        {"$setOnInsert": {
            "id": checkpoint_id,
            "created_at": now.isoformat(),
            "lock_until": now.isoformat(),
        }},
        upsert=True,
    )
    checkpoint = await db[CHECKPOINT_COLL].find_one_and_update(
        {
            "id": checkpoint_id,
            "$or": [
                {"lock_until": {"$lte": now.isoformat()}},
                {"lock_until": {"$exists": False}},
            ],
        },
        {"$set": {
            "lease_id": lease_id,
            "lock_until": lease_until.isoformat(),
            "status": "running",
            "updated_at": now.isoformat(),
        }},
        projection={"_id": 0},
        # BEFORE contiene il checkpoint precedente (serve per determinare il
        # nuovo intervallo) e rende il test Mongo compatibile con Motor reale.
        return_document=ReturnRecord.BEFORE,
    )
    if not checkpoint:
        current = await db[CHECKPOINT_COLL].find_one(
            {"id": checkpoint_id}, {"_id": 0}
        ) or {}
        return {
            "success": True,
            "status": "already_running",
            "last_success_end": current.get("last_success_end"),
        }
    last_success = checkpoint.get("last_success_end")
    if last_success:
        try:
            start = datetime.fromisoformat(str(last_success)) + timedelta(microseconds=1)
        except ValueError:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now
    if start > end:
        await db[CHECKPOINT_COLL].update_one(
            {"id": checkpoint_id, "lease_id": lease_id},
            {"$set": {"lock_until": now.isoformat(), "status": "up_to_date"}},
        )
        return {"success": True, "status": "up_to_date", "last_success_end": last_success}

    try:
        result = await sync_paypal_period(db, start, end)
        await db[CHECKPOINT_COLL].update_one(
            {"id": checkpoint_id, "lease_id": lease_id},
            {"$set": {
                "status": "success",
                "last_success_start": start.isoformat(),
                "last_success_end": end.isoformat(),
                "last_result": result,
                "lock_until": now.isoformat(),
                "last_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {"success": True, "status": "updated", **result}
    except Exception as exc:
        await db[CHECKPOINT_COLL].update_one(
            {"id": checkpoint_id, "lease_id": lease_id},
            {"$set": {
                "status": "error",
                "last_error": type(exc).__name__,
                "lock_until": now.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        raise
