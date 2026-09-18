import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.ritenute import _carica_f24
from app.services.iva_f24_verifica import verifica_versamento_iva
from app.services.tax_payment_query import TaxPaymentQueryService


def test_servizio_unico_espone_righe_crediti_quietanza_e_banca_separate():
    db = MemorySheetsClient()["tax-payment-query"]
    asyncio.run(db["f24_unificato"].insert_one({
        "id": "f24-1", "quietanza_id": "q-1",
        "sezione_erario": [
            {"codice_tributo": "6006", "anno_riferimento": "2026", "importo_debito": 1000.0},
            {"codice_tributo": "1704", "periodo_riferimento": "06/2026", "importo_credito": 50.0},
        ],
        "totali": {"totale_debito": 1000.0, "totale_credito": 50.0, "saldo_netto": 950.0},
    }))
    asyncio.run(db["quietanze_f24"].insert_one({
        "id": "q-1", "protocollo_telematico": "PROTO-1",
        "data_pagamento": "2026-07-16", "filename": "quietanza.pdf",
    }))

    [document] = asyncio.run(TaxPaymentQueryService(db).list_documents())
    assert len(document["righe_tributo_normalizzate"]) == 2
    assert document["righe_credito"][0]["tax_code"] == "1704"
    assert document["versato_documentalmente"] is True
    assert document["banca_verificata"] is False
    assert document["protocollo_quietanza"] == "PROTO-1"

    [from_ritenute] = asyncio.run(_carica_f24(db))
    assert from_ritenute["canonical_query_source"] == "tax_payment_query_service"
    iva = asyncio.run(verifica_versamento_iva(db, anno=2026, mese=6, debito_liquidazione=1000))
    assert iva["versato_documentalmente"] is True
    assert iva["pagato_banca"] is False
    assert iva["ravvedimento"]["necessario"] is False
