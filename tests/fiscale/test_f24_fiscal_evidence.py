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
            {
                "codice_tributo": "1704", "periodo_riferimento": "01/2026",
                "importo_credito": 250.55, "pagina": 2, "riga_y": 412,
                "testo_sorgente": "1704 0001 2026 250,55",
            },
        ],
    }
    [row] = normalize_f24_evidence_rows(parsed)
    assert row["debit_amount"] == 0
    assert row["credit_amount"] == 250.55
    assert row["credit_cents"] == 25055
    assert row["debit_cents"] == 0
    assert row["page_number"] == 2
    assert row["source_row_y"] == 412
    assert row["source_text"] == "1704 0001 2026 250,55"
    assert row["row_kind"] == "CREDIT_OFFSET_USE"
    assert row["is_accounting_cost"] is False


def test_rata_unica_del_modello_non_e_gennaio():
    """«01 / 01 2021» è la rata unica: come nella quietanza, nessun mese."""
    parsed = {
        "sezione_erario": [
            {
                "codice_tributo": "2003", "mese": "01", "anno": "2021", "rateazione": "0001",
                "periodo_riferimento": "01/2021", "importo_debito": 100.0,
                "testo_sorgente": "2003 01 / 01 2021 100,00 0,00",
            },
            {
                "codice_tributo": "2001", "mese": "01", "anno": "2022", "rateazione": "0001",
                "periodo_riferimento": "01/2022", "importo_debito": 50.0,
                "testo_sorgente": "IMPOSTE DIRETTE – IVA 2001 01 / 01 2022 50,00 , 0,00 ,",
            },
            {
                "codice_tributo": "1001", "mese": "11", "anno": "2022", "rateazione": "0011",
                "periodo_riferimento": "11/2022", "importo_debito": 10.0,
                "testo_sorgente": "1001 11 2022 10,00 0,00",
            },
        ],
    }
    rows = normalize_f24_evidence_rows(parsed)
    assert [row["reference_period"] for row in rows] == [None, None, "2022-11"]


def test_riga_inps_finita_in_erario_torna_alla_sezione_inps():
    """Il modello del commercialista legge la riga INPS con codice = anno: si
    riconosce dal testo (sede, causale, matricola, periodo)."""
    parsed = {
        "sezione_erario": [
            {
                "codice_tributo": "2022", "mese": "11", "anno": "2022", "importo_debito": 2840.0,
                "testo_sorgente": "5100 RC01 0000000001 11 2022 11 2022 2.840,00 , 0,00 ,",
            },
        ],
    }
    [row] = normalize_f24_evidence_rows(parsed)
    assert (row["section"], row["tax_code"], row["entity_code"]) == ("INPS", "RC01", "5100")
    assert row["reference_period"] == "2022-11"
    assert row["debit_cents"] == 284000
