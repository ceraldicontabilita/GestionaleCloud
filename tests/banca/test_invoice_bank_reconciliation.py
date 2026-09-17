"""Contratti anti-falso-positivo della riconciliazione fattura-banca."""
import asyncio

import pytest
from fastapi import HTTPException
from app.services.sheets_document_store import MemorySheetsClient

from app.services.invoice_payments import (
    InvoiceBankReconciliationRequest,
    find_invoice_bank_candidates,
    reconcile_invoice_bank_movement,
)


def _db(number="FT-123", invoice_amount=100.0, bank_amount=100.0, description=None):
    db = MemorySheetsClient()["invoice_bank_reconciliation"]
    asyncio.run(db["invoices"].insert_one({
        "id": "f-1", "invoice_number": number, "total_amount": invoice_amount,
        "prima_nota_banca_id": "pn-1",
    }))
    asyncio.run(db["prima_nota_banca"].insert_one({"id": "pn-1", "riconciliato": False}))
    asyncio.run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-1", "importo": bank_amount,
        "descrizione": description or f"BONIFICO PAGAMENTO FATTURA {number}",
    }))
    return db


def test_numero_e_importo_esatti_aggiornano_tutto_e_lasciano_audit():
    db = _db()
    req = InvoiceBankReconciliationRequest(fattura_id="f-1", movimento_id="ec-1")
    result = asyncio.run(reconcile_invoice_bank_movement(db, req))

    assert result["success"] is True
    assert asyncio.run(db["invoices"].find_one({"id": "f-1"}))["riconciliato"] is True
    assert asyncio.run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"}))["fattura_id"] == "f-1"
    assert asyncio.run(db["prima_nota_banca"].find_one({"id": "pn-1"}))["riconciliato"] is True
    assert asyncio.run(db["audit_riconciliazioni"].count_documents({})) == 1


@pytest.mark.parametrize("bank_amount,description", [
    (99.99, "PAGAMENTO FATTURA FT-123"),
    (100.0, "BONIFICO GENERICO SENZA RIFERIMENTO"),
])
def test_differenza_un_centesimo_o_numero_assente_bloccano(bank_amount, description):
    db = _db(bank_amount=bank_amount, description=description)
    req = InvoiceBankReconciliationRequest(fattura_id="f-1", movimento_id="ec-1")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(reconcile_invoice_bank_movement(db, req))
    assert exc.value.status_code == 409
    assert asyncio.run(db["audit_riconciliazioni"].count_documents({})) == 0


def test_candidati_bancari_mostrano_match_forte_e_non_collegano_da_soli():
    db = _db(number="FPR 105/26", invoice_amount=1332.24,
             bank_amount=-1332.24, description="BONIFICO FULVIO FERRANTINI")
    asyncio.run(db["invoices"].update_one({"id": "f-1"}, {"$set": {
        "supplier_name": "FULVIO FERRANTINI", "invoice_date": "2026-08-06",
    }}))
    asyncio.run(db["estratto_conto_movimenti"].update_one({"id": "ec-1"}, {"$set": {
        "data": "2026-08-06", "tipo": "uscita",
    }}))

    result = asyncio.run(find_invoice_bank_candidates(db, "f-1"))

    assert result["totale_candidati"] == 1
    assert result["candidati"][0]["livello"] == "forte"
    assert result["candidati"][0]["richiede_conferma"] is True
    assert asyncio.run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"})).get("fattura_id") is None


def test_candidato_con_numero_fattura_e_importo_e_verificato():
    db = _db(number="FPR 105/26", invoice_amount=1332.24,
             bank_amount=-1332.24, description="BONIFICO FATTURA FPR 105/26")
    asyncio.run(db["invoices"].update_one({"id": "f-1"}, {"$set": {"invoice_date": "2026-08-06"}}))
    asyncio.run(db["estratto_conto_movimenti"].update_one({"id": "ec-1"}, {"$set": {
        "data": "2026-08-07", "tipo": "uscita",
    }}))

    candidate = asyncio.run(find_invoice_bank_candidates(db, "f-1"))["candidati"][0]

    assert candidate["livello"] == "verificato"
    assert candidate["richiede_conferma"] is False
