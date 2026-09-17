"""Invarianti del writer atomico dei pagamenti fattura."""
import asyncio

import pytest
from fastapi import HTTPException
from app.services.sheets_document_store import MemorySheetsClient

from app.services.invoice_payments import (
    ManualInvoicePaymentRequest,
    register_manual_invoice_payment,
)


def test_retry_identico_non_duplica_movimento_ne_importo_pagato():
    db = MemorySheetsClient()["invoice_payment_idempotency"]
    asyncio.run(db["invoices"].insert_one({
        "id": "fatt-1", "total_amount": 100.0, "importo_pagato": 0,
        "tipo_documento": "TD01",
    }))
    req = ManualInvoicePaymentRequest(
        fattura_id="fatt-1", importo=100.0, metodo="banca",
        data_pagamento="2026-08-08", fornitore="Test", numero_fattura="1",
    )

    first = asyncio.run(register_manual_invoice_payment(db, req))
    replay = asyncio.run(register_manual_invoice_payment(db, req))

    assert first["movimento_id"] == replay["movimento_id"]
    assert replay["idempotent_replay"] is True
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 1
    invoice = asyncio.run(db["invoices"].find_one({"id": "fatt-1"}))
    assert invoice["importo_pagato"] == 100.0


def test_cassa_e_banca_hanno_chiavi_idempotenza_distinte():
    db = MemorySheetsClient()["invoice_payment_methods"]
    asyncio.run(db["invoices"].insert_one({
        "id": "fatt-2", "total_amount": 200.0, "importo_pagato": 0,
        "tipo_documento": "TD01",
    }))

    banca = ManualInvoicePaymentRequest(
        fattura_id="fatt-2", importo=100.0, metodo="banca",
        data_pagamento="2026-08-08", idempotency_key="fatt-2-banca-quota-1",
    )
    cassa = ManualInvoicePaymentRequest(
        fattura_id="fatt-2", importo=100.0, metodo="cassa",
        data_pagamento="2026-08-08", idempotency_key="fatt-2-cassa-quota-2",
    )
    asyncio.run(register_manual_invoice_payment(db, banca))
    asyncio.run(register_manual_invoice_payment(db, cassa))

    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 1
    assert asyncio.run(db["prima_nota_cassa"].count_documents({})) == 1
    invoice = asyncio.run(db["invoices"].find_one({"id": "fatt-2"}))
    assert invoice["importo_pagato"] == 200.0


def test_importo_superiore_al_residuo_e_bloccato_senza_scritture():
    db = MemorySheetsClient()["invoice_payment_overpayment"]
    asyncio.run(db["invoices"].insert_one({
        "id": "fatt-3", "total_amount": 100.0, "importo_pagato": 40.0,
        "tipo_documento": "TD01",
    }))
    req = ManualInvoicePaymentRequest(
        fattura_id="fatt-3", importo=70.0, metodo="banca",
        data_pagamento="2026-08-08",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(register_manual_invoice_payment(db, req))

    assert error.value.status_code == 409
    assert "residuo" in str(error.value.detail).lower()
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0
    assert asyncio.run(db["pagamenti_operazioni"].count_documents({})) == 0


def test_parziale_senza_scadenza_o_chiave_idempotenza_e_bloccato():
    db = MemorySheetsClient()["invoice_payment_ambiguous_partial"]
    asyncio.run(db["invoices"].insert_one({
        "id": "fatt-4", "total_amount": 100.0, "importo_pagato": 0,
        "tipo_documento": "TD01",
    }))
    req = ManualInvoicePaymentRequest(
        fattura_id="fatt-4", importo=30.0, metodo="cassa",
        data_pagamento="2026-08-08",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(register_manual_invoice_payment(db, req))

    assert error.value.status_code == 422
    assert "parziale ambiguo" in str(error.value.detail).lower()
    assert asyncio.run(db["prima_nota_cassa"].count_documents({})) == 0
