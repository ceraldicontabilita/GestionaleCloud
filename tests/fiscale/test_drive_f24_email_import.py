import os

from app.services import drive_f24_email_import as email_import


def test_only_verified_accountant_attachments_are_imported(tmp_path, monkeypatch):
    accountant = tmp_path / "accountant.pdf"
    consultant = tmp_path / "consultant.pdf"
    accountant.write_bytes(b"%PDF-accountant")
    consultant.write_bytes(b"%PDF-consultant")
    calls = []
    monkeypatch.setattr(email_import, "parse_quietanza_f24", lambda **_kwargs: {"dati_generali": {}})
    monkeypatch.setattr(email_import, "upload_f24_accountant_model", lambda **kwargs: (
        calls.append(kwargs) or {"document_id": "DOC-1", "payment_proven": False}
    ))

    result = email_import.import_downloaded_accountant_attachments({
        "totale_email": 2, "totale_allegati": 2, "allegati": [{
            "file_path": str(accountant), "original_filename": "f24.pdf",
            "mittente_tipo": "commercialista", "email_from": "studio@example.it",
            "email_subject": "F24 giugno", "email_date": "Tue, 16 Jun 2026 09:00:00 +0200",
        }, {
            "file_path": str(consultant), "original_filename": "paghe.pdf",
            "mittente_tipo": "consulente_lavoro", "email_from": "paghe@example.it",
        }],
    }, service=object())

    assert result["storage"] == "google_drive"
    assert result["payment_proven"] is False
    assert result["imported_count"] == 1
    assert result["skipped"] == [{"file": "paghe.pdf", "reason": "MITTENTE_NON_COMMERCIALISTA"}]
    assert calls[0]["filing_year"] == 2026
    assert calls[0]["source_metadata"]["source_kind"] == "trusted_accountant_email"
    assert calls[0]["source_metadata"]["email_from"] == "studio@example.it"
    assert not os.path.exists(accountant)
    assert not os.path.exists(consultant)


def test_missing_attachment_is_reported_without_false_import():
    result = email_import.import_downloaded_accountant_attachments({
        "totale_email": 1, "totale_allegati": 1, "allegati": [{
            "file_path": "missing.pdf", "original_filename": "missing.pdf",
            "mittente_tipo": "commercialista", "email_from": "studio@example.it",
        }],
    })

    assert result["success"] is False
    assert result["imported_count"] == 0
    assert result["error_count"] == 1


def test_quietanza_from_accountant_is_never_imported_as_model(tmp_path, monkeypatch):
    receipt = tmp_path / "quietanza.pdf"
    receipt.write_bytes(b"%PDF-receipt")
    monkeypatch.setattr(email_import, "parse_quietanza_f24", lambda **_kwargs: {
        "dati_generali": {
            "protocollo_telematico": "26060212304532735",
            "data_pagamento": "2026-06-16",
        },
    })
    monkeypatch.setattr(email_import, "upload_f24_accountant_model", lambda **_kwargs: (
        (_ for _ in ()).throw(AssertionError("quietanza importata come modello"))
    ))

    result = email_import.import_downloaded_accountant_attachments({
        "totale_email": 1, "totale_allegati": 1, "allegati": [{
            "file_path": str(receipt), "original_filename": "quietanza.pdf",
            "mittente_tipo": "commercialista", "email_from": "studio@example.it",
        }],
    })

    assert result["imported_count"] == 0
    assert result["skipped"][0]["reason"] == "QUIETANZA_ADE_NON_IMPORTATA_COME_MODELLO"
    assert result["skipped"][0]["protocol"] == "26060212304532735"
