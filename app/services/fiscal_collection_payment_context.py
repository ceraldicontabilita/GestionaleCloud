"""Quote documentali delle ricevute di riscossione, senza duplicare le rate.

Il collegamento di una ricevuta a una cartella non ne attribuisce l'intero
importo. Per ricevute condivise servono quote esplicite che quadrino con il
totale; il riscontro bancario resta una proprieta' separata della ricevuta.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.db_collections import (
    COLL_TAX_ALLOCATIONS,
    COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS,
)


def _positive_cents(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        cents = amount * 100
        if not amount.is_finite() or amount <= 0 or cents != cents.to_integral_value():
            return None
        return int(cents)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None


async def load_collection_payment_context(
    db, *, company_id: str, claims: Iterable[dict[str, Any]],
    payments_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Proietta soltanto importi documentati attribuibili alla singola cartella.

    Le associazioni legacy a un'unica cartella mantengono l'importo intero
    soltanto dopo verifica su tutti i collegamenti del pagamento nell'azienda.
    Una rata condivisa senza riparto documentato resta da verificare anche se
    il portale la dice saldata o la banca conferma l'addebito complessivo.
    """
    claims = list(claims)
    context = {
        str(claim["id"]): {"documented_payments": [], "ambiguous_payment_ids": sorted({
            str(payment_id) for payment_id in claim.get("linked_payment_ids") or []
            if str(payment_id) not in payments_by_id
        })}
        for claim in claims if claim.get("id")
    }
    payment_ids = {
        str(payment_id)
        for claim in claims for payment_id in claim.get("linked_payment_ids") or []
        if str(payment_id) in payments_by_id
    }
    if not payment_ids:
        return context

    # La ricerca dedicata non assume che il lotto di cartelle da riconciliare
    # comprenda tutte quelle che condividono la ricevuta.
    linked_claims = await db[COLL_TAX_COLLECTION_CLAIMS].find(
        {"company_id": company_id, "linked_payment_ids": {"$in": sorted(payment_ids)}},
        {"_id": 0, "id": 1, "collection_number": 1, "linked_payment_ids": 1},
    ).to_list(None)
    allocations = await db[COLL_TAX_ALLOCATIONS].find(
        {"company_id": company_id, "payment_id": {"$in": sorted(payment_ids)},
         "entity_type": "tax_collection_claim"},
        {"_id": 0, "payment_id": 1, "entity_id": 1, "amount": 1},
    ).to_list(None)
    events = await db[COLL_TAX_COLLECTION_EVENTS].find(
        {"company_id": company_id, "payment_id": {"$in": sorted(payment_ids)}},
        {"_id": 0, "payment_id": 1, "claim_id": 1,
         "shared_plan_payment": 1, "amount": 1},
    ).to_list(None)

    claims_by_payment: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    allocations_by_payment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    events_by_payment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in linked_claims:
        if not claim.get("id"):
            continue
        for payment_id in claim.get("linked_payment_ids") or []:
            if str(payment_id) in payment_ids:
                claims_by_payment[str(payment_id)][str(claim["id"])] = claim
    for allocation in allocations:
        allocations_by_payment[str(allocation.get("payment_id"))].append(allocation)
    for event in events:
        events_by_payment[str(event.get("payment_id"))].append(event)

    for payment_id in sorted(payment_ids):
        payment = payments_by_id[payment_id]
        if (not payment.get("documentary_evidence")
                or payment.get("source_kind") == "F24_DOCUMENT_EVIDENCE"):
            continue
        linked = claims_by_payment[payment_id]
        amount = payment.get("operation_amount")
        if amount is None:
            amount = payment.get("amount")
        total_cents = _positive_cents(amount)
        claim_allocations = allocations_by_payment[payment_id]
        attributed: dict[str, int] = {}
        if total_cents is not None and claim_allocations:
            valid = True
            for allocation in claim_allocations:
                claim_id = str(allocation.get("entity_id") or "")
                cents = _positive_cents(allocation.get("amount"))
                if not claim_id or claim_id not in linked or claim_id in attributed or cents is None:
                    valid = False
                    break
                attributed[claim_id] = cents
            numbers = set(payment.get("direct_collection_numbers") or [])
            linked_numbers = {claim.get("collection_number") for claim in linked.values()}
            receipt_events = events_by_payment[payment_id]
            event_claims = {str(event.get("claim_id") or "") for event in receipt_events}
            if (not valid or sum(attributed.values()) != total_cents
                    or set(attributed) != set(linked)
                    or (numbers and numbers != linked_numbers)
                    or not event_claims.issubset(linked)
                    or (len(linked) < 2 and any(event.get("shared_plan_payment") for event in receipt_events))):
                attributed = {}
        elif total_cents is not None and len(linked) == 1:
            claim_id, claim = next(iter(linked.items()))
            numbers = set(payment.get("direct_collection_numbers") or [])
            receipt_events = events_by_payment[payment_id]
            # Un evento di rata condivisa resta tale anche quando un'altra
            # cartella del piano non e' ancora stata importata o selezionata.
            if (not any(event.get("shared_plan_payment") for event in receipt_events)
                    and not any(
                        str(event.get("claim_id") or "") != claim_id
                        or _positive_cents(event.get("amount")) != total_cents
                        for event in receipt_events
                    )
                    and (not numbers or numbers == {claim.get("collection_number")})):
                attributed[claim_id] = total_cents

        for claim_id in linked:
            if claim_id not in context:
                continue
            cents = attributed.get(claim_id)
            if cents is None:
                context[claim_id]["ambiguous_payment_ids"].append(payment_id)
                continue
            context[claim_id]["documented_payments"].append({
                "payment_id": payment.get("id"),
                "source_type": payment.get("source_type"),
                "source_id": payment.get("source_id"),
                "document_id": payment.get("document_id"),
                "amount": format(Decimal(cents) / 100, ".2f"),
                "payment_date": payment.get("payment_date"),
                "bank_verified": bool(payment.get("bank_verified")),
            })
    return context
