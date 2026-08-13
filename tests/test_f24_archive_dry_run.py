import csv
import hashlib
import io
import zipfile

from openpyxl import Workbook

from app.scripts import import_f24_fiscal_archive as archive_import


def test_dry_run_legge_zip_senza_database_o_scritture(tmp_path, monkeypatch):
    content = b"%PDF-1.4 synthetic"
    digest = hashlib.sha256(content).hexdigest()
    manifest_stream = io.StringIO()
    writer = csv.DictWriter(
        manifest_stream,
        fieldnames=["file", "sha256", "tipo_documento", "data_versamento", "protocollo_telematico"],
        delimiter=";",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow({
        "file": "2026/quietanza.pdf",
        "sha256": digest,
        "tipo_documento": "Quietanza Agenzia Entrate",
        "data_versamento": "21/07/2026",
        "protocollo_telematico": "26072135472143961/000001",
    })
    archive_path = tmp_path / "fiscale.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        prefix = "PACCHETTO/02_F24_QUIETANZE"
        archive.writestr(f"{prefix}/{archive_import.MANIFEST_NAME}", manifest_stream.getvalue())
        archive.writestr(f"{prefix}/2026/quietanza.pdf", content)

    monkeypatch.setattr(archive_import, "parse_f24_evidence", lambda *_args, **_kwargs: {
        "dati_generali": {"protocollo_telematico": "26072135472143961/000001"},
        "validazione": {"saldo_quadrato": True},
    })
    monkeypatch.setattr(archive_import, "normalize_f24_evidence_rows", lambda _parsed: [{
        "debit_amount": 284.0, "credit_amount": 0.0,
    }])

    validated, summary = archive_import.validate_archive(archive_path)

    assert len(validated) == 1
    assert summary["mode"] == "dry-run"
    assert summary["valid_documents"] == 1
    assert summary["invalid_documents"] == 0
    assert summary["normalized_rows"] == 1
    assert summary["total_debits"] == 284.0
    assert summary["unexpected_missing_quietanza_protocols"] == 0
    assert summary["database_duplicate_check"] == "NOT_RUN_NO_DATABASE_CONNECTION"


def test_importo_con_virgola_grafica_finale_non_si_azzera():
    from app.services.parser_f24 import _importo_da_token

    assert _importo_da_token([(366, "137,37"), (384.5, ",")]) == 137.37


def test_dry_run_legge_indice_excel_finale_dallo_zip(tmp_path, monkeypatch):
    content = b"%PDF-1.4 synthetic"
    digest = hashlib.sha256(content).hexdigest()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = archive_import.XLSX_INDEX_SHEET
    sheet.append(["Data", "Tipo", "Protocollo", "Saldo delega", "PDF", "SHA256"])
    sheet.append([
        "21/07/2026",
        "Quietanza AE",
        "26072135472143961/000001",
        284.0,
        "02_ANNI/2026/F24_QUIETANZE/quietanza.pdf",
        digest,
    ])
    workbook_stream = io.BytesIO()
    workbook.save(workbook_stream)

    archive_path = tmp_path / "fiscale-finale.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        prefix = "PACCHETTO"
        archive.writestr(
            f"{prefix}/01_EXCEL/Archivio_Fiscale_COMPLETO.xlsx",
            workbook_stream.getvalue(),
        )
        archive.writestr(
            f"{prefix}/02_ANNI/2026/F24_QUIETANZE/quietanza.pdf",
            content,
        )

    monkeypatch.setattr(archive_import, "parse_f24_evidence", lambda *_args, **_kwargs: {
        "dati_generali": {"protocollo_telematico": "26072135472143961/000001"},
        "validazione": {"saldo_quadrato": True},
    })
    monkeypatch.setattr(archive_import, "normalize_f24_evidence_rows", lambda _parsed: [{
        "debit_amount": 284.0, "credit_amount": 0.0,
    }])

    validated, summary = archive_import.validate_archive(archive_path)

    assert len(validated) == 1
    assert summary["manifest_format"] == "xlsx"
    assert summary["archive_index_reconciliation"] == "NOT_AVAILABLE"
    assert summary["valid_documents"] == 1
    assert summary["invalid_documents"] == 0
    assert summary["total_debits"] == 284.0
