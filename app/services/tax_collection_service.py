"""Stati multidimensionali e snapshot AdeR, senza equivalenza residuo/pagato."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.services.fiscal_evidence import stable_id


PORTAL_STATES = {"DA_PAGARE", "PAGATA", "SOSPESA", "ANNULLATA", "NON_DETERMINABILE"}


def cents(value: Any) -> int:
    return int(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def classify_collection_status(*, portal_status: str | None, residual: Any, payment_evidence: bool,
                               suspended: bool = False, disputed: bool = False) -> dict[str, Any]:
    residual_cents = cents(residual)
    portal = str(portal_status or "NON_DETERMINABILE").upper()
    if portal not in PORTAL_STATES:
        portal = "NON_DETERMINABILE"
    if suspended:
        business = "CONTESTATA" if disputed else "DA_VERIFICARE"
    elif payment_evidence and residual_cents == 0:
        business = "CHIUSA"
    elif disputed:
        business = "CONTESTATA"
    else:
        business = "APERTA" if residual_cents > 0 else "DA_VERIFICARE"
    return {
        "portal_status": portal,
        "business_status": business,
        "residual_cents": residual_cents,
        "payment_evidence": bool(payment_evidence),
        "micro_residual": 0 < residual_cents <= 500,
        "requires_review": business in {"DA_VERIFICARE", "CONTESTATA"},
    }


def build_snapshot(*, company_id: str, source_document_id: str, captured_at: str,
                   rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = []
    for row in rows:
        number = str(row.get("collection_number") or "").strip()
        if not number:
            raise ValueError("collection_number obbligatorio")
        normalized.append({
            **row,
            "collection_number": number,
            "original_amount_cents": cents(row.get("original_amount")),
            **classify_collection_status(
                portal_status=row.get("portal_status"), residual=row.get("residual"),
                payment_evidence=bool(row.get("payment_evidence")),
                suspended=bool(row.get("suspended")), disputed=bool(row.get("disputed")),
            ),
        })
    return {
        "id": stable_id("adersnap", company_id, source_document_id, captured_at),
        "company_id": company_id,
        "source_document_id": source_document_id,
        "captured_at": captured_at,
        "row_count": len(normalized),
        "rows": normalized,
        "immutable": True,
    }


def payment_match(*, expected_amount: Any, paid_amount: Any, identity_match: bool,
                  payment_document: bool, bank_movement: bool) -> dict[str, Any]:
    exact_amount = cents(expected_amount) == cents(paid_amount)
    definitive = exact_amount and identity_match and payment_document and bank_movement
    return {
        "status": "CONFIRMED" if definitive else "PENDING_MANUAL_REVIEW",
        "confidence": sum((exact_amount, identity_match, payment_document, bank_movement)) / 4,
        "exact_amount": exact_amount,
        "identity_match": identity_match,
        "payment_document": payment_document,
        "bank_movement": bank_movement,
    }
