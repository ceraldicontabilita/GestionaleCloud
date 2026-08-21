import hashlib
import io
import inspect
import zipfile

from openpyxl import Workbook

from render_workflows.document_ingest import (
    _ingest_configuration,
    classify_document,
    index_hashes_from_xlsx,
    iter_supported_documents,
    route_for,
    scan_document_inbox_preview,
)
from render_workflows.main import calderone_documenti_preview


def test_index_hashes_reads_canonical_sha256_only():
    digest = hashlib.sha256(b"documento").hexdigest()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "DOCUMENTI"
    sheet.append(["ID documento", "SHA-256"])
    sheet.append(["DOC-1", digest.upper()])
    sheet.append(["DOC-2", "non-valido"])
    output = io.BytesIO()
    workbook.save(output)
    assert index_hashes_from_xlsx(output.getvalue()) == {digest}


def test_zip_expands_supported_documents_and_ignores_other_files():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("banca/estratto.csv", b"data;importo")
        archive.writestr("note.txt", b"non importare")
    assert list(iter_supported_documents("raccolta.zip", output.getvalue())) == [
        ("banca/estratto.csv", b"data;importo")
    ]


def test_zip_blocks_path_traversal():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../estratto.csv", b"data;importo")
    try:
        list(iter_supported_documents("raccolta.zip", output.getvalue()))
    except ValueError as exc:
        assert "non sicuro" in str(exc)
    else:
        raise AssertionError("ZIP traversal non bloccato")


def test_classifier_covers_general_document_families_without_guessing_unknown():
    assert classify_document("estratto_conto_2026.csv", b"")["document_type"] == "estratto_conto"
    assert classify_document("dichiarazione_iva_2025.pdf", b"non-pdf")["document_type"] == "dichiarazione_fiscale"
    unknown = classify_document("documento.pdf", b"non-pdf")
    assert unknown["status"] == "DA_VERIFICARE"
    assert unknown["readiness"] == "REVIEW_REQUIRED"


def test_xml_content_routes_fatture_and_corrispettivi_to_existing_importers():
    invoice = classify_document(
        "IT01234567890_00001.xml",
        b"<FatturaElettronica><FatturaElettronicaHeader /></FatturaElettronica>",
    )
    receipt = classify_document(
        "RT_20260821.xml",
        b"<DatiRT><DataOraRilevazione>2026-08-21</DataOraRilevazione></DatiRT>",
    )
    assert invoice["document_type"] == "fattura"
    assert receipt["document_type"] == "corrispettivo"
    assert invoice["readiness"] == receipt["readiness"] == "CANONICAL_IMPORT_READY"
    assert "/api/documenti/upload-auto" in invoice["consumer"]


def test_generic_fiscal_and_payment_documents_stay_in_review():
    for document_type in ("dichiarazione_fiscale", "bonifico", "cartella_esattoriale", "avviso"):
        route = route_for(document_type)
        assert route["readiness"] == "REVIEW_REQUIRED"
        assert route["consumer"].startswith("documents_inbox")


def test_real_ingest_requires_both_explicit_confirmation_and_feature_flag(monkeypatch):
    monkeypatch.setenv("RENDER_INGEST_SHARED_SECRET", "s" * 40)
    monkeypatch.setenv("GESTIONALE_CANONICAL_BASE_URL", "https://example.invalid")
    monkeypatch.delenv("ENABLE_RENDER_CANONICAL_INGEST", raising=False)
    try:
        _ingest_configuration(False)
    except RuntimeError as exc:
        assert "confirm=true" in str(exc)
    else:
        raise AssertionError("ingest senza conferma non bloccato")
    try:
        _ingest_configuration(True)
    except RuntimeError as exc:
        assert "ENABLE_RENDER_CANONICAL_INGEST" in str(exc)
    else:
        raise AssertionError("ingest senza feature flag non bloccato")

    monkeypatch.setenv("ENABLE_RENDER_CANONICAL_INGEST", "true")
    assert _ingest_configuration(True) == (
        "https://example.invalid", "s" * 40,
    )


def test_preview_task_exposes_document_limit_and_rejects_invalid_values():
    assert "max_documents" in inspect.signature(calderone_documenti_preview).parameters
    try:
        scan_document_inbox_preview(max_documents=0)
    except ValueError as exc:
        assert "max_documents" in str(exc)
    else:
        raise AssertionError("limite anteprima non validato")
