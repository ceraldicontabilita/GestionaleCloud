"""Riconciliazione canonica delle prove di pagamento fiscali.

Il servizio collega quietanze/PagoPA/CBILL agli oggetti AdeR soltanto quando
esiste un identificativo forte e l'importo coincide al centesimo. Un pagamento
di una rata che copre piu cartelle viene collegato a tutte le pretese, ma non
viene duplicato come importo su ciascuna cartella.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from app.db_collections import (
    COLL_TAX_ALLOCATIONS,
    COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS,
    COLL_TAX_PAYMENTS,
    COLL_TAX_RATE_INSTALLMENTS,
    COLL_TAX_RATE_PLANS,
    COLL_TAX_SETTLEMENT_APPLICATIONS,
)
from app.services.fiscal_evidence import link_evidence, normalize_evidence, stable_id


CENT = Decimal("0.01")


def _money(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _identifier(value: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper())


def _payment_identifiers(payment: dict[str, Any]) -> set[str]:
    return {
        normalized
        for field in (
            "identificativo_bolletta", "iuv", "codice_cbill", "cbill_code", "payment_module_code",
            "document_number", "cartella_number", "collection_number",
            "protocollo_telematico",
        )
        if (normalized := _identifier(payment.get(field)))
    }


def _claim_numbers(plan: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(
        str(item.get("document_number") or "").strip()
        for item in (plan.get("document_references") or [])
        if item.get("document_number")
    ))


def find_ader_payment_target(
    *, payment: dict[str, Any], rate_plans: Iterable[dict[str, Any]],
    settlements: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Trova un solo bersaglio AdeR con codice forte + importo esatto."""
    identifiers = _payment_identifiers(payment)
    amount = _money(payment.get("amount") if payment.get("amount") is not None else payment.get("importo"))
    if not identifiers or amount is None:
        return {"matched": False, "reason": "identificativo_forte_o_importo_mancante", "candidates": []}

    candidates: list[dict[str, Any]] = []
    for plan in rate_plans:
        for module in plan.get("payment_modules") or []:
            module_ids = {
                _identifier(module.get(field))
                for field in ("document_number", "payment_module_code", "iuv", "cbill_code")
            } - {""}
            if not identifiers.intersection(module_ids):
                continue
            installments = [
                item for item in (module.get("installments") or [])
                if _money(item.get("amount")) == amount
            ]
            if len(installments) != 1:
                continue
            installment = installments[0]
            candidates.append({
                "target_type": "rate_installment",
                "plan_id": plan.get("id"),
                "plan_reference": plan.get("plan_reference"),
                "installment_number": installment.get("number"),
                "installment_due_date": installment.get("due_date"),
                "amount": str(amount),
                "claim_numbers": _claim_numbers(plan),
                "matched_identifier": sorted(identifiers.intersection(module_ids))[0],
            })

    for settlement in settlements:
        settlement_ids = {
            _identifier(settlement.get(field))
            for field in ("communication_number", "payment_module_code", "iuv", "cbill_code")
        } - {""}
        settlement_amount = _money(settlement.get("amount_due"))
        if identifiers.intersection(settlement_ids) and settlement_amount == amount:
            number = str(settlement.get("collection_document_number") or "").strip()
            candidates.append({
                "target_type": "settlement",
                "settlement_id": settlement.get("id"),
                "amount": str(amount),
                "claim_numbers": [number] if number else [],
                "matched_identifier": sorted(identifiers.intersection(settlement_ids))[0],
            })

    identities = {
        (candidate["target_type"], candidate.get("plan_id") or candidate.get("settlement_id"),
         candidate.get("installment_number"))
        for candidate in candidates
    }
    if len(identities) != 1:
        return {
            "matched": False,
            "reason": "nessun_bersaglio_univoco" if not candidates else "bersagli_ader_ambigui",
            "candidates": candidates,
        }
    return {"matched": True, "reason": "identificativo_forte_e_importo_esatto", **candidates[0]}


async def reconcile_fiscal_payment(
    db, *, company_id: str, payment: dict[str, Any], source_type: str,
    source_id: str, document_id: str | None = None, version_id: str | None = None,
) -> dict[str, Any]:
    """Collega idempotentemente una prova agli oggetti AdeR e alle cartelle."""
    plans = await db[COLL_TAX_RATE_PLANS].find(
        {"company_id": company_id}, {"_id": 0}
    ).to_list(5000)
    settlements = await db[COLL_TAX_SETTLEMENT_APPLICATIONS].find(
        {"company_id": company_id}, {"_id": 0}
    ).to_list(5000)
    target = find_ader_payment_target(
        payment=payment, rate_plans=plans, settlements=settlements,
    )
    if not target["matched"]:
        return target

    now = datetime.now(timezone.utc).isoformat()
    amount = target["amount"]
    payment_id = stable_id("taxpayment", company_id, source_type, source_id)
    payment_record = {
        "id": payment_id,
        "company_id": company_id,
        "source_type": source_type,
        "source_id": source_id,
        "document_id": document_id,
        "version_id": version_id,
        "amount": amount,
        "operation_amount": amount,
        "fee_amount": str(_money(payment.get("fee_amount")) or Decimal("0.00")),
        "bank_debit_total": str(
            _money(payment.get("bank_debit_total")) or amount
        ),
        "payment_date": payment.get("payment_date") or payment.get("data_pagamento"),
        "matched_identifier": target["matched_identifier"],
        "bank_verified": bool(payment.get("bank_verified") or payment.get("movimento_id")),
        "documentary_evidence": True,
        # La commissione diventa costo soltanto dopo il collegamento al vero
        # movimento bancario. Qui resta una componente documentale distinta,
        # senza creare una scrittura o un movimento sintetico.
        "fee_accounting_status": (
            "BANK_EVIDENCE_LINKED"
            if bool(payment.get("bank_verified") or payment.get("movimento_id"))
            else "PENDING_BANK_VERIFICATION"
        ),
        "updated_at": now,
    }
    await db[COLL_TAX_PAYMENTS].update_one(
        {"company_id": company_id, "id": payment_id},
        {"$setOnInsert": {"created_at": now}, "$set": payment_record},
        upsert=True,
    )

    if target["target_type"] == "rate_installment":
        target_id = stable_id(
            "aderinstallment", company_id, target["plan_id"], target["installment_number"],
        )
        await db[COLL_TAX_RATE_INSTALLMENTS].update_one(
            {"company_id": company_id, "id": target_id},
            {"$setOnInsert": {"created_at": now}, "$set": {
                "id": target_id, "company_id": company_id,
                "rate_plan_id": target["plan_id"],
                "installment_number": target["installment_number"],
                "due_date": target.get("installment_due_date"), "amount": amount,
                "payment_id": payment_id, "status": "PAID_DOCUMENTED",
                "bank_verified": payment_record["bank_verified"], "updated_at": now,
            }}, upsert=True,
        )
        entity_type = "tax_rate_installment"
        event_type = "INSTALLMENT_PAYMENT"
    else:
        target_id = target["settlement_id"]
        await db[COLL_TAX_SETTLEMENT_APPLICATIONS].update_one(
            {"company_id": company_id, "id": target_id},
            {"$set": {"payment_evidence": True, "payment_id": payment_id,
                      "status": "PAID_DOCUMENTED", "updated_at": now}},
        )
        entity_type = "tax_settlement_application"
        event_type = "SETTLEMENT_PAYMENT"

    allocation_id = stable_id("taxallocation", company_id, payment_id, entity_type, target_id)
    await db[COLL_TAX_ALLOCATIONS].update_one(
        {"company_id": company_id, "id": allocation_id},
        {"$setOnInsert": {
            "id": allocation_id, "company_id": company_id, "payment_id": payment_id,
            "entity_type": entity_type, "entity_id": target_id, "amount": amount,
            "evidence_types": [source_type], "created_at": now,
        }}, upsert=True,
    )

    evidence = []
    if document_id and version_id:
        evidence = [normalize_evidence(
            document_id=document_id,
            version_id=version_id,
            page_number=1,
            field="payment_identifier",
            raw_value=target["matched_identifier"],
            normalized_value={"identifier": target["matched_identifier"], "amount": amount},
            parser_version="fiscal-payment-reconciliation-v1",
            reason="identificativo_forte_e_importo_esatto",
        )]
        await link_evidence(
            db, company_id=company_id, entity_type=entity_type, entity_id=target_id,
            relation_type="payment_receipt", evidence=evidence,
            actor="fiscal_payment_reconciliation",
        )

    linked_claim_ids: list[str] = []
    for collection_number in target.get("claim_numbers") or []:
        claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one(
            {"company_id": company_id, "collection_number": collection_number},
            {"_id": 0, "id": 1},
        )
        if not claim:
            continue
        claim_id = claim["id"]
        linked_claim_ids.append(claim_id)
        claim_update: dict[str, Any] = {
            "$addToSet": {"linked_payment_ids": payment_id},
            "$set": {"updated_at": now},
        }
        if evidence:
            claim_update["$addToSet"]["payment_evidence_ids"] = evidence[0]["id"]
        await db[COLL_TAX_COLLECTION_CLAIMS].update_one(
            {"company_id": company_id, "id": claim_id},
            claim_update,
        )
        if evidence:
            await link_evidence(
                db, company_id=company_id,
                entity_type="tax_collection_claim", entity_id=claim_id,
                relation_type="payment_receipt", evidence=evidence,
                actor="fiscal_payment_reconciliation",
            )
        event_id = stable_id("taxevent", company_id, claim_id, event_type, payment_id)
        # Se una rata copre piu cartelle il pagamento non viene contato N volte.
        event_amount = amount if len(target.get("claim_numbers") or []) == 1 else "0.00"
        await db[COLL_TAX_COLLECTION_EVENTS].update_one(
            {"company_id": company_id, "id": event_id},
            {"$setOnInsert": {
                "id": event_id, "company_id": company_id, "claim_id": claim_id,
                "event_type": event_type, "amount": event_amount,
                "effective_at": payment_record["payment_date"] or now,
                "source_reference": payment_id, "payment_id": payment_id,
                "shared_plan_payment": len(target.get("claim_numbers") or []) > 1,
                "created_at": now,
            }}, upsert=True,
        )

    return {
        **target, "payment_id": payment_id, "allocation_id": allocation_id,
        "target_id": target_id, "linked_claim_ids": linked_claim_ids,
        "bank_verified": payment_record["bank_verified"],
    }
