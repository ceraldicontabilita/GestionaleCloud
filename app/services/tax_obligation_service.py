"""Regole del partitario fiscale e del bridge F24, senza nuovi costi."""

from __future__ import annotations

from typing import Any

from app.db_collections import COLL_TAX_ALLOCATIONS, COLL_TAX_OBLIGATIONS, COLL_TAX_PAYMENTS
from app.services.fiscal_evidence import now_iso, stable_id
from app.services.tax_collection_service import cents


def classify_f24_line(tax_code: str, amount: Any, *, is_credit: bool = False) -> dict[str, Any]:
    code = str(tax_code or "").strip().upper()
    cycles = {"6012": "monthly_december", "6013": "annual_advance", "6099": "annual_balance"}
    return {
        "tax_code": code,
        "amount_cents": cents(amount),
        "kind": "credit" if is_credit else "debit",
        "vat_cycle": cycles.get(code),
        "is_accounting_cost": False,
        "reason": "F24 e' mezzo di regolamento; il costo nasce dall'obbligo fiscale",
    }


def obligation_status(*, obligation_cents: int, allocated_cents: int, payment_confirmed: bool) -> str:
    if allocated_cents <= 0:
        return "OPEN"
    if allocated_cents < obligation_cents:
        return "PARTIALLY_ALLOCATED"
    return "PAID" if payment_confirmed else "ALLOCATED_PENDING_PAYMENT_EVIDENCE"


async def upsert_obligation(db, *, company_id: str, tax_code: str, period: str,
                            amount: Any, actor: str, evidence_ids: list[str],
                            obligation_type: str = "tax") -> str:
    if not evidence_ids:
        raise ValueError("Un obbligo fiscale richiede almeno una prova")
    obligation_id = stable_id("taxobl", company_id, obligation_type, tax_code, period)
    now = now_iso()
    await db[COLL_TAX_OBLIGATIONS].update_one(
        {"company_id": company_id, "id": obligation_id},
        {"$setOnInsert": {"created_at": now, "created_by": actor}, "$set": {
            "company_id": company_id, "id": obligation_id, "type": obligation_type,
            "tax_code": str(tax_code).upper(), "period": period,
            "amount_cents": cents(amount), "evidence_ids": evidence_ids,
            "payment_status": "TO_VERIFY", "updated_at": now, "updated_by": actor,
        }}, upsert=True,
    )
    return obligation_id


async def record_payment(db, *, company_id: str, external_ref: str, amount: Any,
                         actor: str, bank_movement_id: str | None = None,
                         payment_document_id: str | None = None,
                         payment_document_type: str | None = None) -> str:
    payment_id = stable_id("taxpay", company_id, external_ref)
    now = now_iso()
    strong_document = payment_document_type in {
        "QUIETANZA_F24", "RICEVUTA_F24", "QUIETANZA_ADE_R", "RICEVUTA_PAGOPA", "RICEVUTA_CBILL",
    }
    status = "CONFIRMED" if bank_movement_id or (payment_document_id and strong_document) else "PENDING_EVIDENCE"
    await db[COLL_TAX_PAYMENTS].update_one(
        {"company_id": company_id, "id": payment_id},
        {"$setOnInsert": {"created_at": now, "created_by": actor}, "$set": {
            "company_id": company_id, "id": payment_id, "external_ref": external_ref,
            "amount_cents": cents(amount), "bank_movement_id": bank_movement_id,
            "payment_document_id": payment_document_id,
            "payment_document_type": payment_document_type,
            "status": status, "updated_at": now,
        }}, upsert=True,
    )
    return payment_id


async def allocate_payment(db, *, company_id: str, payment_id: str,
                           obligation_id: str, amount: Any, actor: str) -> str:
    payment = await db[COLL_TAX_PAYMENTS].find_one(
        {"company_id": company_id, "id": payment_id}, {"_id": 0, "status": 1}
    )
    obligation = await db[COLL_TAX_OBLIGATIONS].find_one(
        {"company_id": company_id, "id": obligation_id}, {"_id": 0, "id": 1}
    )
    if not payment or not obligation:
        raise ValueError("Pagamento o obbligo non trovato nel perimetro aziendale")
    allocation_id = stable_id("taxalloc", company_id, payment_id, obligation_id)
    now = now_iso()
    await db[COLL_TAX_ALLOCATIONS].update_one(
        {"company_id": company_id, "id": allocation_id},
        {"$setOnInsert": {"created_at": now, "created_by": actor}, "$set": {
            "company_id": company_id, "id": allocation_id,
            "payment_id": payment_id, "obligation_id": obligation_id,
            "amount_cents": cents(amount), "payment_confirmed": payment.get("status") == "CONFIRMED",
            "updated_at": now,
        }}, upsert=True,
    )
    return allocation_id
