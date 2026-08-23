import hashlib

from app.services import drive_f24_model_upload as upload


def test_f24_index_rows_preserve_debits_credits_and_explicit_source(monkeypatch):
    monkeypatch.setattr(upload, "normalize_f24_evidence_rows", lambda _parsed: [{
        "section": "ERARIO", "row_kind": "TRIBUTO", "tax_code": "2003",
        "description": "IRES saldo", "reference_period": "2025",
        "entity_code": "", "debit_amount": 1200.0, "credit_amount": 300.0,
        "page_number": 1, "source_text": "2003 2025 1200,00 300,00",
    }])

    [row] = upload._f24_index_values(
        "DOC-1", "abc", "02_F24_COMMERCIALISTA/2026/f24.pdf", {}, 2026,
    )

    assert row["Debito"] == 1200.0
    assert row["Credito"] == 300.0
    assert row["Protocollo"] == ""
    assert row["Tipo documento"] == "MODELLO_F24_COMMERCIALISTA"
    assert row["Fonte"] == "UPLOAD_GESTIONALE_COMMERCIALISTA"


def test_duplicate_is_reused_without_writing_drive(monkeypatch):
    content = b"%PDF-existing"
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(upload.index, "load_full_catalog", lambda _service: (
        {"root_id": "ROOT"}, {"documents": [{
            "ID documento": "DOC-EXISTING", "SHA-256": digest,
            "Percorso Drive": "02_F24_COMMERCIALISTA/2026/existing.pdf",
        }]},
    ))

    result = upload.upload_f24_accountant_model(
        content=content, filename="existing.pdf", filing_year=2026, service=object(),
    )

    assert result["duplicate"] is True
    assert result["document_id"] == "DOC-EXISTING"
    assert result["drive_path"].startswith("02_F24_COMMERCIALISTA/")


def test_rejects_non_pdf_before_drive_access():
    try:
        upload.upload_f24_accountant_model(
            content=b"not a pdf", filename="x.pdf", filing_year=2026, service=object(),
        )
    except ValueError as exc:
        assert str(exc) == "PDF non valido"
    else:
        raise AssertionError("contenuto non PDF accettato")
