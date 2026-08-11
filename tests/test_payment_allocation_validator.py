from app.services.payment_allocation_validator import (
    allocation_summary,
    is_credit_note,
    to_cents,
    validate_invoice_allocation,
)


def test_to_cents_uses_decimal_and_italian_separators():
    assert to_cents("98,63") == 9863
    assert to_cents("1.656,00") == 165600
    assert to_cents("646.72") == 64672
    assert to_cents(3575.00) == 357500


def test_second_allocation_over_residual_is_conflicting():
    invoice = {
        "id": "56d",
        "tipo_documento": "TD01",
        "total_amount": "646,72",
        "importo_pagato": "0,00",
        "assegni_collegati": [{
            "assegno_id": "a1", "quota": "646,72", "banca_confermata": True,
        }, {
            "assegno_id": "a2", "quota": "646,72", "banca_confermata": True,
        }],
    }
    result = validate_invoice_allocation(invoice, "646,72", allocation_id="a2")
    assert result["allowed"] is False
    assert result["status"] == "conflicting"
    assert result["reason"] == "quota_supera_residuo"
    assert allocation_summary(invoice)["payment_allocation_status"] == "conflicting"


def test_credit_note_cannot_receive_check_payment():
    invoice = {"tipo_documento": "TD04", "total_amount": 100.0}
    assert is_credit_note(invoice)
    result = validate_invoice_allocation(invoice, 10000)
    assert result["allowed"] is False
    assert result["reason"] == "nota_di_credito_non_pagabile"
