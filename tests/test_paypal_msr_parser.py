from app.parsers.paypal_msr_parser import (
    extract_period_from_header,
    extract_transactions_from_english_text,
)


def test_periodo_report_annuale_inglese_non_inventa_un_mese():
    periodo = extract_period_from_header(
        "Transaction History\nJanuary 01, 2022 through December 31, 2022"
    )

    assert periodo == {
        "periodo_inizio": "2022-01-01",
        "periodo_fine": "2022-12-31",
        "mese": None,
        "anno": 2022,
    }


def test_transazioni_report_annuale_supportano_descrizione_su_due_righe():
    text = """Transaction History
January 01, 2022 through December 31, 2022
Date Description Status Currency Gross Fee Net
PreApproved Payment Bill User Payment: Example Supplier
04/01/2022 Completed EUR -30,50 0,00 -30,50
ID: TX-ANNUAL-1
Express Checkout Payment: Example Entertainment
03/02/2022 S.r.l.s Completed EUR -278,16 0,00 -278,16
ID: TX-ANNUAL-2
January 01, 2022 through December 31, 2022 Page 1
"""

    transactions = extract_transactions_from_english_text(text)

    assert len(transactions) == 2
    assert transactions[0]["transaction_id"] == "TX-ANNUAL-1"
    assert transactions[0]["data"] == "2022-01-04"
    assert transactions[0]["lordo"] == -30.50
    assert transactions[0]["tipo"] == "pagamento_utenza"
    assert transactions[0]["nome_controparte"] == "Example Supplier"
    assert transactions[1]["transaction_id"] == "TX-ANNUAL-2"
    assert transactions[1]["descrizione"].endswith("Example Entertainment S.r.l.s")
    assert transactions[1]["netto"] == -278.16
    assert transactions[1]["tipo"] == "express_checkout"
