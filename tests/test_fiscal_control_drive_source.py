import asyncio


def test_source_certainty_uses_only_drive_index_and_splits_models_from_receipts(monkeypatch):
    from app.routers import fiscal_control
    from app.services import drive_document_index

    rows = [
        {
            "id": "MODEL-ROW", "document_id": "MODEL-1", "filename": "commercialista.pdf",
            "payment_year": "2024", "tax_code": "2003", "reference_period": "2024",
            "section": "ERARIO", "entity": "", "debit_amount": 1000, "credit_amount": 0,
            "payment_status": "MODELLO_F24_PRESENTE", "documentary_payment_status": "DA_VERIFICARE",
        },
        {
            "id": "RECEIPT-ROW", "document_id": "Q-1", "filename": "quietanza.pdf",
            "payment_year": "2024", "tax_code": "2003", "reference_period": "2024",
            "section": "ERARIO", "entity": "", "debit_amount": 1000, "credit_amount": 0,
            "payment_status": "DOCUMENTATO_DA_QUIETANZA",
            "documentary_payment_status": "QUIETANZA_PRESENTE",
        },
    ]
    monkeypatch.setattr(
        drive_document_index, "list_tax_obligations",
        lambda **_kwargs: {"items": rows, "total": len(rows)},
    )
    monkeypatch.setattr(
        drive_document_index, "list_declarations",
        lambda **_kwargs: {"results": []},
    )
    monkeypatch.setattr(
        fiscal_control.Database, "get_db",
        classmethod(lambda _cls: (_ for _ in ()).throw(AssertionError("legacy runtime access"))),
    )

    result = asyncio.run(fiscal_control.source_certainty(year=2024, _admin={"role": "admin"}))

    assert result["sources"] == {
        "quietanza_drive_rows": 1,
        "commercialista_f24_documents": 1,
        "declaration_documents": 0,
        "canonical": "google_drive",
    }
    assert result["items"][0]["status"] == "CONCORDANTE"
    assert result["items"][0]["erario_state"] == "NULLA_DOVUTO_ERARIO_DOCUMENTATO"
