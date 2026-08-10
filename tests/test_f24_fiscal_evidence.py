from app.services.f24_fiscal_evidence import normalize_f24_evidence_rows


def test_normalization_keeps_equal_rows_as_distinct_ordinals():
    parsed = {
        "sezione_erario": [
            {"codice_tributo": "8906", "periodo_riferimento": "2019", "importo_debito": 2.89},
            {"codice_tributo": "8906", "periodo_riferimento": "2019", "importo_debito": 2.89},
        ],
    }
    rows = normalize_f24_evidence_rows(parsed)
    assert len(rows) == 2
    assert [row["ordinal"] for row in rows] == [1, 2]
    assert rows[0]["tax_code"] == rows[1]["tax_code"] == "8906"


def test_credit_is_kept_separate_from_debit_and_not_marked_as_cost():
    parsed = {
        "sezione_erario": [
            {"codice_tributo": "1704", "periodo_riferimento": "01/2026", "importo_credito": 250.55},
        ],
    }
    [row] = normalize_f24_evidence_rows(parsed)
    assert row["debit_amount"] == 0
    assert row["credit_amount"] == 250.55
    assert row["row_kind"] == "CREDIT_OFFSET_USE"
    assert row["is_accounting_cost"] is False
