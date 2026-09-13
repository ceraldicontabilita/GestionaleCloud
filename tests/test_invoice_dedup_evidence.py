from app.routers.invoices.invoices_main import _dedupe_invoices


def _invoice(invoice_id, *, digest=None, source_id=None):
    return {
        "id": invoice_id,
        "invoice_number": "A/1",
        "supplier_vat": "IT00000000000",
        "invoice_date": "2026-01-01",
        "total_amount": 100,
        "file_hash": digest,
        "source_document_id": source_id,
    }


def test_collisione_contabile_senza_prova_non_viene_nascosta():
    result = _dedupe_invoices([
        _invoice("f1", digest="hash-a"),
        _invoice("f2", digest="hash-b"),
    ])
    assert {row["id"] for row in result} == {"f1", "f2"}
    assert all(row["duplicate_review_required"] for row in result)


def test_stesso_originale_viene_deduplicato_in_lettura():
    result = _dedupe_invoices([
        _invoice("f1", digest="same"),
        _invoice("f2", digest="same"),
    ])
    assert len(result) == 1


def test_stesso_id_origine_e_prova_anche_senza_hash():
    result = _dedupe_invoices([
        _invoice("f1", source_id="drive-1"),
        _invoice("f2", source_id="drive-1"),
    ])
    assert len(result) == 1
