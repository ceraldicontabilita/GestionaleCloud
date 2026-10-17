"""Conservative identity and version checks for documentary AdeR plans.

The archive's tenant is not proof of the debtor printed in a letter. Multiple
letters for a protocol are documentary variants until their terms agree.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_TAX_ID = r"([A-Z0-9]{16}|[0-9]{11})(?![A-Z0-9])"
_CF_LABEL = r"(?:C\s*\.?\s*F\s*\.?|CODICE\s+FISCALE)(?:\s*/\s*PARTITA\s+IVA)?\s*:?\s*"


def plan_taxpayer_identity(text: str, company_id: str) -> dict[str, Any]:
    """Use the applicant/plan debtor, not a representative's fiscal code."""
    text = re.sub(r"\s+", " ", str(text or "")).upper()
    candidates = set(re.findall(rf"PRESENTAT[AO]\s+DAL(?:LA)?\s+{_CF_LABEL}{_TAX_ID}", text))
    # The CF on the amortisation statement identifies the plan's debtor. A
    # generic CF elsewhere may identify a representative, signatory or adviser.
    statement = re.search(r"PROSPETTO\s+DEL\s+PIANO\s+DI\s+AMMORTAMENTO(.*)", text)
    if statement:
        candidates.update(re.findall(rf"{_CF_LABEL}{_TAX_ID}", statement.group(1)[:1600]))
    expected = re.sub(r"[^A-Z0-9]", "", str(company_id).upper())
    status = ("MISSING" if not candidates else "CONFIRMED" if candidates == {expected}
              else "AMBIGUOUS" if len(candidates) > 1 else "MISMATCH")
    return {"status": status, "expected_taxpayer_id": expected,
            "printed_taxpayer_ids": sorted(candidates),
            "basis": "APPLICANT_AND_PLAN_STATEMENT"}


def plan_terms_signature(plan: dict[str, Any]) -> str:
    """Exclude file names, upload dates and later-resolved claim suffixes."""
    terms = {field: plan.get(field) for field in (
        "application_date", "installment_count", "first_installment_amount",
        "first_installment_due_date", "total_plan_cents", "rateizzato_cents",
    )}
    terms["documents"] = sorted(
        [{key: doc.get(key) for key in ("printed_reference", "amount_cents")}
         for doc in plan.get("documents") or []], key=lambda doc: str(doc["printed_reference"]),
    )
    terms["references"] = sorted({str(ref.get("printed_reference") or ref.get("document_number") or "")
                                  for ref in plan.get("document_references") or []})
    terms["installments"] = sorted(
        [{key: row.get(key) for key in ("number", "due_date", "amount_cents", "principal_cents",
                                       "plan_interest_cents", "default_interest_cents",
                                       "collection_fees_cents", "notification_fees_cents",
                                       "enforcement_costs_cents")}
         for row in plan.get("installments") or []], key=lambda row: str(row["number"]),
    )
    return hashlib.sha256(json.dumps(terms, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def plan_source_variant(plan: dict[str, Any]) -> dict[str, Any]:
    return {"terms_signature": plan_terms_signature(plan),
            **{field: plan[field] for field in (
                "source_document_id", "source_filename", "application_date", "document_date", "installment_count",
                "first_installment_due_date", "first_installment_amount", "total_plan_cents",
                "rateizzato_cents", "documents", "document_references", "installments",
                "taxpayer_identity", "taxpayer_identity_status", "printed_plan_reference",
                "filename_plan_reference_hint", "filename_reference_discrepancy",
            ) if field in plan}}


def plan_can_reconcile(plan: dict[str, Any]) -> bool:
    """Missing legacy identity and conflicting/unreviewed terms are not exact."""
    return (plan.get("taxpayer_identity_status") == "CONFIRMED"
            and not plan.get("terms_conflict") and not plan.get("requires_review"))
