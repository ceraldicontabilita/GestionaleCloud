from app.services.email_drive_archive import route_for_document_type
from app.services import email_drive_archive
from app.services.email_monitor_service import _risolvi_tipo_documento_email


def test_classificazione_allegato_prevale_sul_tipo_mittente():
    doc = {"category": "f24", "filename": "modello-f24.pdf"}
    mittente = {"tipo_documento": "fattura_estera_pdf"}
    assert _risolvi_tipo_documento_email(doc, mittente) == "f24"


def test_allegato_sconosciuto_non_diventa_generico():
    assert _risolvi_tipo_documento_email(
        {"category": "altro", "filename": "foto.pdf"},
        {"tipo_documento": "generico"},
    ) is None


def test_fallback_specifico_del_mittente_resta_disponibile():
    assert _risolvi_tipo_documento_email(
        {"category": "altro", "filename": "invoice-123.pdf"},
        {"tipo_documento": "fattura_estera_pdf"},
    ) == "fattura_estera_pdf"


def test_routing_drive_documenti_amministrativi():
    assert route_for_document_type("avviso_bonario") == ("avvisi_bonari", "Avvisi bonari")
    assert route_for_document_type("verbale") == ("verbali", "Verbali")
    assert route_for_document_type("busta_paga") == ("cedolini", "Cedolini")
    assert route_for_document_type("scheda_tecnica") == ("schede_tecniche", "Schede tecniche")
    assert route_for_document_type("altro") is None


def test_archivio_email_senza_cartella_unica_non_tocca_drive(monkeypatch):
    monkeypatch.delenv("GOOGLE_DRIVE_DATI_FOLDER_ID", raising=False)
    monkeypatch.setattr(email_drive_archive, "_drive_service",
                        lambda: (_ for _ in ()).throw(AssertionError("Drive non va aperto")))

    esito = email_drive_archive.archive_document_copy(
        {"id": "doc-1", "filename": "documento.pdf", "content": b"pdf"}, "partenopay"
    )

    assert esito == {"status": "not_configured", "area": "partenopay"}


def test_archivio_email_senza_contenuto_non_scrive(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice-dati")
    esito = email_drive_archive.archive_document_copy(
        {"id": "doc-1", "filename": "documento.pdf", "content": b""}, "partenopay"
    )
    assert esito == {"status": "error", "area": "partenopay", "reason": "contenuto_mancante"}


class _DriveRequest:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.payload


class _QuotaError(Exception):
    def __init__(self):
        self.resp = type("Response", (), {"status": 403})()

    def __str__(self):
        return "Service Accounts do not have storage quota"


class _DriveFiles:
    def __init__(self):
        self.list_calls = 0
        self.created_body = None

    def list(self, **kwargs):
        self.list_calls += 1
        if self.list_calls == 1:
            return _DriveRequest({"files": [{"id": "elaborate-folder"}]})
        return _DriveRequest({"files": []})

    def create(self, **kwargs):
        self.created_body = kwargs["body"]
        return _DriveRequest(error=_QuotaError())


class _DriveFilesDuplicate(_DriveFiles):
    def list(self, **kwargs):
        self.list_calls += 1
        if self.list_calls == 1:
            return _DriveRequest({"files": [{"id": "elaborate-folder"}]})
        if "gestionale_sha256" in kwargs.get("q", ""):
            return _DriveRequest({"files": [{"id": "canonical-1", "name": "prima-copia.pdf"}]})
        return _DriveRequest({"files": []})

    def create(self, **kwargs):
        raise AssertionError("un SHA-256 gia' presente non va caricato di nuovo")


class _DriveService:
    def __init__(self):
        self.files_api = _DriveFiles()

    def files(self):
        return self.files_api


def test_archivio_deduplica_per_sha256_anche_con_nome_diverso(monkeypatch):
    service = _DriveService()
    service.files_api = _DriveFilesDuplicate()
    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice-dati")
    monkeypatch.setattr(email_drive_archive, "_drive_service", lambda: service)

    result = email_drive_archive.archive_document_copy(
        {"id": "scheda-1", "filename": "seconda-copia.pdf", "content": b"%PDF-stesso"},
        "scheda_tecnica",
    )

    assert result["status"] == "duplicate"
    assert result["drive_file_id"] == "canonical-1"
    assert len(result["sha256"]) == 64


def test_archivio_usa_elaborate_della_cartella_unica_e_registra_quota(monkeypatch):
    """La copia va in ELABORATE della cartella unica, non in DA ELABORARE:
    il documento e' gia' entrato dall'email e lo smistatore lo rileggerebbe."""
    service = _DriveService()
    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice-dati")
    monkeypatch.setattr(email_drive_archive, "_drive_service", lambda: service)

    result = email_drive_archive.archive_document_copy(
        {"id": "verbale-1", "filename": "verbale.pdf", "content": b"pdf"},
        "verbale",
    )

    assert service.files_api.created_body["parents"] == ["elaborate-folder"]
    assert result == {
        "status": "blocked_owner_auth",
        "area": "verbali",
        "reason": "service_account_storage_quota",
    }
