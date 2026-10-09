from app.parsers.paypal_msr_parser import (
    extract_period_from_header,
    extract_single_transaction_detail,
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


def test_dettaglio_paypal_usa_data_operazione_e_id_non_data_visualizzazione():
    text = """07/04/26, 11:14 Transazioni - PayPal
Pagamento inviato a Intesa Sanpaolo SpA
29 aprile 2025 09:51:48 CEST Pagamento 74418673ST3611131
-58,55 � EUR
Completato
https://www.paypal.com/unifiedtransactions/details/payment/74418673ST3611131
"""
    tx = extract_single_transaction_detail(text)

    assert tx["transaction_id"] == "74418673ST3611131"
    assert tx["data"] == "2025-04-29"
    assert tx["lordo"] == -58.55
    assert tx["nome_controparte"] == "Intesa Sanpaolo SpA"
    assert tx["tipo"] == "pagamento"


def test_dettaglio_senza_id_paypal_non_diventa_movimento():
    assert extract_single_transaction_detail(
        "Pagamento inviato a Fornitore\n29 aprile 2025 09:51:48 CEST\n-58,55 EUR"
    ) is None


def test_report_annuale_italiano_legge_id_importi_e_versamenti_distinti():
    text = """Cronologia transazioni
dicembre 31, 2024 tramite agosto 04, 2025
Data Descrizione Stato Valuta Lordo Tariffa Netto
Pagamento preautorizzato utenza: Spotify AB
12/01/2025 Completata EUR -17,99 0,00 -17,99
ID/Codice: 7DR45019GN8991907
Versamento generico con carta
12/01/2025 Completata EUR 17,99 0,00 17,99
ID/Codice: 5TW59825X4574884X
Pagamento Express Checkout: Intesa Sanpaolo
29/04/2025 S.p.A. Completata EUR -58,55 0,00 -58,55
ID/Codice: 74418673ST3611131
dicembre 31, 2024 tramite agosto 04, 2025 Pagina 1
"""

    transactions = extract_transactions_from_english_text(text)

    assert len(transactions) == 3
    assert [tx["transaction_id"] for tx in transactions] == [
        "7DR45019GN8991907", "5TW59825X4574884X", "74418673ST3611131",
    ]
    assert [tx["lordo"] for tx in transactions] == [-17.99, 17.99, -58.55]
    assert [tx["tipo"] for tx in transactions] == [
        "pagamento_utenza", "accredito", "express_checkout",
    ]
    assert transactions[2]["nome_controparte"] == "Intesa Sanpaolo S.p.A."
