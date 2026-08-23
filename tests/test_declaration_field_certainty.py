from app.services.declaration_field_certainty import (
    AMBIGUOUS_F24,
    CERTAIN,
    EXACT,
    MISSING_F24,
    NOT_EXTRACTED,
    REVIEW,
    extract_770_tax_rows,
    reconcile_declaration_tax_rows,
)


REAL_770_TEXT = """[PAGINA 12]
QUADRO ST
06 2024 1.778,37 1.806,92 28,55
X 1001 24 03 2025
08 2024 1.446,57 1.446,57
1001 16 09 2024
11 2024 119,42 120,09 0,67
X 3802 24 03 2025

[PAGINA 13]
QUADRO ST
12 2024 42,74 42,74
1701 16 01 2025
"""


def test_770_extracts_only_rows_with_unambiguous_columns_and_cent_arithmetic():
    result = extract_770_tax_rows(
        REAL_770_TEXT, document_id="DECL-770", filename="770_2025.pdf", sha256="a" * 64,
    )

    assert result["field_level_status"] == CERTAIN
    assert result["extracted_with_certainty"] == 4
    assert result["requires_review"] == 0
    first = result["tax_rows"][0]
    assert first["page_number"] == 12
    assert first["tax_code"] == "1001"
    assert first["reference_period"] == "2024-06"
    assert first["withholding_amount"] == 1778.37
    assert first["paid_amount"] == 1806.92
    assert first["interest_amount"] == 28.55
    assert first["debit_amount"] == 1806.92
    assert first["payment_date"] == "2025-03-24"
    assert first["source_text"].startswith("06 2024")


def test_770_rejects_amounts_whose_semantics_are_not_proven():
    result = extract_770_tax_rows(
        "[PAGINA 7]\nQUADRO ST\n06 2024 100,00 95,00 5,00\n1001 16 07 2024",
        document_id="DECL-770",
    )

    assert result["tax_rows"] == []
    assert result["field_level_status"] == REVIEW
    assert result["rejected_rows"][0]["certainty_reason"] == "colonne_o_aritmetica_non_univoche"


def test_770_ignores_same_numeric_shape_outside_st_sv_context():
    result = extract_770_tax_rows(
        "[PAGINA 3]\nQUADRO SX\n08 2024 1.446,57 1.446,57\n1001 16 09 2024",
        document_id="DECL-770",
    )
    assert result["tax_rows"] == []
    assert result["rejected_rows"] == []


def test_declaration_rows_match_f24_only_on_full_fiscal_signature():
    extraction = extract_770_tax_rows(REAL_770_TEXT, document_id="DECL-770")
    result = reconcile_declaration_tax_rows(extraction, [{
        "id": "F24-ROW-1", "tax_code": "1001", "reference_period": "06/2024",
        "debit_amount": 1806.92, "credit_amount": 0,
    }])

    first = next(item for item in result["items"] if item["declaration_row"]["reference_period"] == "2024-06")
    assert first["status"] == EXACT
    assert first["f24_row"]["id"] == "F24-ROW-1"
    assert result["semantics"]["amount_only_match_allowed"] is False
    assert result["semantics"]["bank_payment_proven"] is False
    assert result["counts"][MISSING_F24] == 3


def test_same_amount_with_wrong_tax_code_does_not_match():
    extraction = extract_770_tax_rows(
        "QUADRO ST\n08 2024 1.446,57 1.446,57\n1001 16 09 2024", document_id="DECL-770",
    )
    result = reconcile_declaration_tax_rows(extraction, [{
        "id": "F24-WRONG", "tax_code": "1012", "reference_period": "2024-08",
        "debit_amount": 1446.57, "credit_amount": 0,
    }])
    assert result["items"][0]["status"] == MISSING_F24


def test_duplicate_f24_candidates_remain_ambiguous():
    extraction = extract_770_tax_rows(
        "QUADRO ST\n08 2024 1.446,57 1.446,57\n1001 16 09 2024", document_id="DECL-770",
    )
    f24 = {
        "tax_code": "1001", "reference_period": "2024-08",
        "debit_amount": 1446.57, "credit_amount": 0,
    }
    result = reconcile_declaration_tax_rows(extraction, [{"id": "A", **f24}, {"id": "B", **f24}])
    assert result["items"][0]["status"] == AMBIGUOUS_F24
    assert result["items"][0]["candidate_count"] == 2


def test_rejected_rows_are_never_compared_to_f24():
    extraction = extract_770_tax_rows(
        "QUADRO SV\n06 2024 100,00 95,00 5,00\n1001 16 07 2024", document_id="DECL-770",
    )
    result = reconcile_declaration_tax_rows(extraction, [{
        "id": "F24", "tax_code": "1001", "reference_period": "2024-06",
        "debit_amount": 95, "credit_amount": 0,
    }])
    assert result["items"][0]["status"] == NOT_EXTRACTED
    assert result["certain"] == 0
