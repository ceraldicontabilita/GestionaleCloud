from app.services.paypal_invoice_matching import (
    business_name_matches,
    evaluate_paypal_invoice_match,
    normalize_tax_id,
)


def test_normalizza_partita_iva_italiana():
    assert normalize_tax_id("IT05851861210") == "05851861210"
    assert normalize_tax_id("05851861210") == "05851861210"


def test_stessa_fattura_numero_120_non_basta_se_il_fornitore_e_diverso():
    tx = {
        "transaction_id": "PAY-120",
        "nome_controparte": "CARTA & PARTY SNC DI COSITORE GIOVANNI",
        "invoice_id_fornitore": "120",
        "importo": -122.0,
        "data": "2025-07-02",
    }
    mapping = {
        "fornitore_piva": "IT05851861210",
        "fornitore_ragione_sociale": "CARTA & PARTY SNC DI COSITORE GIOVANNI",
    }
    corretta = {
        "id": "carta-party-120",
        "invoice_number": "120",
        "invoice_date": "2025-06-30",
        "supplier_name": "CARTA & PARTY S.N.C. DI COSITORE GIOVANNI",
        "supplier_vat": "05851861210",
        "total_amount": 122.0,
    }
    errata = {
        "id": "altro-fornitore-120",
        "invoice_number": "120",
        "invoice_date": "2025-06-30",
        "supplier_name": "ALTRO FORNITORE SRL",
        "supplier_vat": "01234567890",
        "total_amount": 122.0,
    }

    ok = evaluate_paypal_invoice_match(tx, corretta, mapping)
    no = evaluate_paypal_invoice_match(tx, errata, mapping)

    assert ok["associabile"] is True
    assert "partita_iva_o_cf" in ok["evidenze"]
    assert "numero_fattura" in ok["evidenze"]
    assert no["associabile"] is False
    assert no["scarto"] == "identita_fornitore_non_verificata"


def test_solo_importo_non_produce_mai_associazione():
    tx = {"nome_controparte": "SPOTIFY AB", "importo": -20.99}
    invoice = {
        "supplier_name": "RICAMBI MANZO SAS",
        "supplier_vat": "01234567890",
        "total_amount": 20.99,
    }
    result = evaluate_paypal_invoice_match(tx, invoice)
    assert result["associabile"] is False
    assert result["evidenze"] == ["importo"]


def test_denominazione_giuridica_punteggiata_e_equivalente():
    assert business_name_matches("InfoCert Spa", "INFOCERT S.P.A.")


def test_stesso_fornitore_e_importo_senza_numero_non_bastano():
    tx = {"nome_controparte": "InfoCert Spa", "importo": -54.90}
    invoice = {
        "invoice_number": "ABC-42",
        "supplier_name": "INFOCERT S.P.A.",
        "total_amount": 54.90,
    }
    result = evaluate_paypal_invoice_match(tx, invoice)
    assert result["associabile"] is False
    assert result["scarto"] == "data_non_compatibile"


def test_un_centesimo_di_differenza_blocca_il_match():
    tx = {
        "nome_controparte": "InfoCert Spa",
        "invoice_id_fornitore": "ABC-42",
        "importo": -54.91,
    }
    invoice = {
        "invoice_number": "ABC-42",
        "supplier_name": "INFOCERT S.P.A.",
        "total_amount": 54.90,
    }
    result = evaluate_paypal_invoice_match(tx, invoice)
    assert result["associabile"] is False
    assert result["scarto"] == "importo_non_coincidente_al_centesimo"


def test_stesso_numero_importo_e_fornitore_ma_valuta_diversa_non_si_associano():
    tx = {
        "nome_controparte": "OpenAI Ireland Limited",
        "invoice_id_fornitore": "INV-USD-42",
        "importo": -100.00,
        "currency": "USD",
    }
    invoice = {
        "invoice_number": "INV-USD-42",
        "supplier_name": "OpenAI Ireland Limited",
        "total_amount": 100.00,
        "divisa": "EUR",
    }

    result = evaluate_paypal_invoice_match(tx, invoice)

    assert result["associabile"] is False
    assert result["scarto"] == "valuta_non_coincidente"


def test_valuta_uguale_diventa_evidenza_del_match():
    tx = {
        "nome_controparte": "OpenAI Ireland Limited",
        "invoice_id_fornitore": "INV-USD-42",
        "importo": -100.00,
        "currency": "USD",
    }
    invoice = {
        "invoice_number": "INV-USD-42",
        "supplier_name": "OpenAI Ireland Limited",
        "total_amount": 100.00,
        "divisa": "USD",
    }

    result = evaluate_paypal_invoice_match(tx, invoice)

    assert result["associabile"] is True
    assert "valuta" in result["evidenze"]
