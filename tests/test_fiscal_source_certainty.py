from app.services.fiscal_source_certainty import (
    AMBIGUOUS, CERTAIN, DIFFERENT, MISSING_ACCOUNTANT, MISSING_OFFICIAL,
    reconcile_f24_sources,
)


def _drive(document_id, code="6099", debit=0, credit=1604.90, period="2025-01"):
    return {
        "document_id": document_id, "filename": f"{document_id}.pdf",
        "protocol": f"P-{document_id}", "tax_code": code,
        "reference_period": period, "section": "ERARIO", "entity": "",
        "debit_amount": debit, "credit_amount": credit,
    }


def _accountant(document_id, code="6099", debit=0, credit=1604.90, period="2025-01"):
    return {
        "id": document_id, "file_name": f"{document_id}.pdf",
        "normalized_tax_rows": [{
            "tax_code": code, "reference_period": period, "section": "ERARIO",
            "entity_code": "", "debit_amount": debit, "credit_amount": credit,
        }],
    }


def test_exact_composite_fiscal_identity_is_certain_and_bidirectional():
    result = reconcile_f24_sources([_drive("Q1")], [_accountant("F1")])
    assert result["all_certain"] is True
    assert result["items"][0]["status"] == CERTAIN
    assert result["items"][0]["official_document"]["document_id"] == "Q1"
    assert result["semantics"]["amount_only_match_allowed"] is False


def test_same_amount_with_different_tax_code_is_not_a_match():
    result = reconcile_f24_sources([_drive("Q1", code="3918", debit=1604.90, credit=0)], [
        _accountant("F1", code="6099", debit=1604.90, credit=0),
    ])
    statuses = {item["status"] for item in result["items"]}
    assert DIFFERENT in statuses
    assert MISSING_ACCOUNTANT in statuses
    assert result["certain"] == 0


def test_missing_sources_are_explicit_in_both_directions():
    missing_receipt = reconcile_f24_sources([], [_accountant("F1")])
    missing_accountant = reconcile_f24_sources([_drive("Q1")], [])
    assert missing_receipt["items"][0]["status"] == MISSING_OFFICIAL
    assert missing_accountant["items"][0]["status"] == MISSING_ACCOUNTANT


def test_duplicate_exact_receipts_are_ambiguous_not_confirmed():
    result = reconcile_f24_sources([_drive("Q1"), _drive("Q2")], [_accountant("F1")])
    assert result["items"][0]["status"] == AMBIGUOUS
    assert result["items"][0]["candidate_count"] == 2
    assert result["certain"] == 0


def test_duplicate_accountant_documents_are_ambiguous_not_confirmed():
    result = reconcile_f24_sources(
        [_drive("Q1")], [_accountant("F1"), _accountant("F2")],
    )
    assert result["certain"] == 0
    assert result["requires_review"] == 2
    assert {item["status"] for item in result["items"]} == {AMBIGUOUS}
