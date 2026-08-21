import hashlib
import io
import inspect
import zipfile

from openpyxl import Workbook

from render_workflows.document_ingest import (
    _drive_move_configuration,
    _ingest_configuration,
    classify_document,
    ingest_document_inbox,
    index_hashes_from_xlsx,
    iter_supported_documents,
    lifecycle_destination,
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
    monkeypatch.setenv("ENABLE_RENDER_DRIVE_MOVES", "true")
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


def test_lifecycle_destination_is_atomic_and_error_has_priority():
    assert lifecycle_destination(["DONE", "DONE"], complete=True) == "DONE"
    assert lifecycle_destination(["DONE", "REVIEW"], complete=True) == "REVIEW"
    assert lifecycle_destination(["REVIEW", "ERROR"], complete=True) == "ERROR"
    assert lifecycle_destination(["DONE"], complete=False) is None
    assert lifecycle_destination([], complete=True) == "REVIEW"


def test_drive_moves_require_confirmation_and_feature_flag(monkeypatch):
    monkeypatch.delenv("ENABLE_RENDER_DRIVE_MOVES", raising=False)
    for confirm in (False, True):
        try:
            _drive_move_configuration(confirm)
        except RuntimeError:
            pass
        else:
            raise AssertionError("spostamento Drive non bloccato")
    monkeypatch.setenv("ENABLE_RENDER_DRIVE_MOVES", "true")
    _drive_move_configuration(True)


def test_ingest_moves_completed_source_to_processed(monkeypatch):
    class Request:
        def __init__(self, value):
            self.value = value

        def execute(self):
            return self.value

    class Files:
        def __init__(self):
            self.updates = []

        def get_media(self, **kwargs):
            return Request(b"cedolino netto del mese")

        def update(self, **kwargs):
            self.updates.append(kwargs)
            return Request({
                "id": kwargs["fileId"],
                "parents": [kwargs["addParents"]],
                "appProperties": kwargs["body"]["appProperties"],
            })

    class Service:
        def __init__(self):
            self.files_api = Files()

        def files(self):
            return self.files_api

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            if url.endswith("/preview"):
                return Response({"success": True, "duplicate": False, "confirmation_token": "ok"})
            return Response({"success": True, "duplicate": False})

    service = Service()
    source = {
        "id": "source-1", "name": "cedolino_agosto.pdf",
        "capabilities": {"canEdit": True}, "parents": ["inbox"],
    }
    monkeypatch.setenv("ENABLE_RENDER_CANONICAL_INGEST", "true")
    monkeypatch.setenv("ENABLE_RENDER_DRIVE_MOVES", "true")
    monkeypatch.setenv("RENDER_INGEST_SHARED_SECRET", "s" * 40)
    monkeypatch.setenv("GESTIONALE_CANONICAL_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("GOOGLE_DRIVE_INBOX_FOLDER_ID", "inbox")
    monkeypatch.setattr("render_workflows.document_ingest._drive_service", lambda **kwargs: service)
    monkeypatch.setattr(
        "render_workflows.document_ingest._resolve_lifecycle_folders",
        lambda *args: {"DONE": "done", "REVIEW": "review", "ERROR": "error"},
    )
    monkeypatch.setattr("render_workflows.document_ingest._canonical_index_hashes", lambda *args: set())
    monkeypatch.setattr("render_workflows.document_ingest._list_inbox_sources", lambda *args: [source])
    monkeypatch.setattr("httpx.Client", Client)

    result = ingest_document_inbox(confirm=True, max_documents=1)

    assert result["results"]["IMPORTATO"] == 1
    assert result["results"]["SPOSTATO_DONE"] == 1
    assert result["moves"] == 1
    update = service.files_api.updates[0]
    assert update["addParents"] == "done"
    assert update["removeParents"] == "inbox"
