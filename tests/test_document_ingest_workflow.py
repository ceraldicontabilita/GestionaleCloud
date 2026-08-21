import hashlib
import io
import zipfile

from openpyxl import Workbook

from render_workflows.document_ingest import (
    classify_document,
    index_hashes_from_xlsx,
    iter_supported_documents,
)


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
