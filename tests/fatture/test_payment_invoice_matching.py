from app.services.payment_invoice_matching import (
    amounts_equal_to_cent,
    invoice_reference_equals,
    invoice_reference_in_text,
    money_cents,
)


def test_importi_italiani_convertiti_in_centesimi():
    assert money_cents("2.348,55") == 234855
    assert amounts_equal_to_cent("2.348,55", 2348.55)
    assert not amounts_equal_to_cent(2348.55, 2348.56)


def test_numero_fattura_esplicito_nella_causale_bonifico():
    causale = "saldo fattura 666721 e fattura 716990"
    assert invoice_reference_in_text("666721", causale)
    assert invoice_reference_in_text("716990", causale)
    assert not invoice_reference_in_text("666722", causale)


def test_numero_breve_richiede_contesto_fattura():
    assert invoice_reference_in_text("77", "saldo fattura 77")
    assert not invoice_reference_in_text("77", "CRO 123477900")
    assert invoice_reference_equals("FT-120/26", "FT12026")
