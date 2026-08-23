from app.services.declaration_field_certainty import (
    AMBIGUOUS_F24,
    CERTAIN,
    EXACT,
    MISSING_F24,
    NOT_EXTRACTED,
    REVIEW,
    extract_annual_iva_fields,
    extract_770_tax_rows,
    extract_lipe_fields,
    reconcile_lipe_management,
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


def _word(text, x, y, width=8):
    return {"text": text, "x0": x, "y0": y, "x1": x + width, "y1": y + 8}


def test_lipe_layout_quadrato_creates_f24_only_for_vp14_debit(monkeypatch):
    from app.services import declaration_field_certainty as certainty

    words = [
        _word("VP1", 108, 158), _word("0", 155, 158), _word("1", 170, 158),
        _word("VP4", 108, 230), _word("100", 376, 230), _word(",", 390, 230), _word("00", 398, 230),
        _word("VP5", 108, 254), _word("20", 503, 254), _word(",", 520, 254), _word("00", 528, 254),
        _word("VP6", 108, 278), _word("80", 376, 278), _word(",", 390, 278), _word("00", 398, 278),
        _word("VP14", 108, 470), _word("80", 376, 470), _word(",", 390, 470), _word("00", 398, 470),
    ]
    monkeypatch.setattr(certainty, "_fitz_pages", lambda _content: [(2, "VP1 VP4 VP5 VP6 VP14", words)])
    result = extract_lipe_fields(b"pdf", document_id="LIPE-1", tax_year=2026)

    assert result["field_level_status"] == CERTAIN
    assert result["declared_fields"][0]["quadrature"] == {"vp6": True, "vp14": True}
    assert result["tax_rows"][0]["tax_code"] == "6001"
    assert result["tax_rows"][0]["reference_period"] == "2026-01"
    assert result["tax_rows"][0]["debit_amount"] == 80.0


def test_annual_iva_requires_repeated_vl_vx_values_to_match(monkeypatch):
    from app.services import declaration_field_certainty as certainty

    def row(field, y, raw, x=500):
        return [_word(field, 108, y, 18), _word(raw, x, y, 35)]

    page_vl = sum((row(field, y, raw) for field, y, raw in (
        ("VL32", 100, ",00"), ("VL33", 120, "4.676,00"),
        ("VL38", 140, ",00"), ("VL39", 160, "4.676,00"),
    )), [])
    page_vx = sum((row(field, y, raw) for field, y, raw in (
        ("VX1", 100, ",00"), ("VX2", 120, "4.676,00"),
    )), [])
    monkeypatch.setattr(certainty, "_fitz_pages", lambda _content: [
        (9, "QUADRO VL", page_vl), (11, "QUADRO VX", page_vx),
    ])
    result = extract_annual_iva_fields(b"pdf", document_id="IVA-1", tax_year=2025)

    assert result["field_level_status"] == CERTAIN
    assert result["quadrature"] == {"vl_debit": True, "vl_credit": True, "vx_debit": True, "vx_credit": True}
    assert next(item for item in result["declared_fields"] if item["field"] == "VX2")["value_cents"] == 467600
    assert result["tax_rows"] == []
    assert result["f24_expectation"] == "NESSUN_F24_6099_A_DEBITO_ATTESO"


def test_lipe_management_compares_sales_and_purchase_vat_at_exact_cents():
    extraction = {
        "declared_fields": [{
            "id": "M1", "reference_period": "2026-01", "page_number": 2,
            "extraction_status": CERTAIN,
            "values": {"vp4_cents": 504743, "vp5_cents": 1277961},
            "raw_evidence": {"VP4": "VP4 5.047,43", "VP5": "VP5 12.779,61"},
        }],
    }
    exact = reconcile_lipe_management(extraction, {"2026-01": {
        "periodo": "2026-01", "stato_calcolo": "CALCOLATA",
        "iva_vendite_cents": 504743, "iva_acquisti_competenza_cents": 1277961,
        "fonte": "calcolo_canonico", "fonte_calcolo": "iva_liquidation_query_v2",
    }})
    assert exact["all_certain"] is True
    assert exact["counts"] == {EXACT: 2}

    mismatch = reconcile_lipe_management(extraction, {"2026-01": {
        "periodo": "2026-01", "stato_calcolo": "CALCOLATA",
        "iva_vendite_cents": 504744, "iva_acquisti_competenza_cents": 1277961,
    }})
    assert mismatch["all_certain"] is False
    assert mismatch["counts"]["DISCORDANTE"] == 1
