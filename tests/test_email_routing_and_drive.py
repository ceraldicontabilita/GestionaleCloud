from app.services.email_drive_archive import route_for_document_type
from app.services import email_drive_archive
from app.services.email_monitor_service import _risolvi_tipo_documento_email
from app.services import drive_folder_registry


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
    assert route_for_document_type("altro") is None


def test_registry_risolve_alias_senza_esporre_id(monkeypatch):
    monkeypatch.setattr(
        drive_folder_registry.settings,
        "DRIVE_FOLDER_REGISTRY_JSON",
        '{"folders":[{"area":"cedolini","label":"Cedolini","folder_id":"secret-folder"}]}',
    )
    assert drive_folder_registry.get_folder_id("busta_paga") == "secret-folder"
    public = drive_folder_registry.get_public_catalog()
    assert "secret-folder" not in str(public)


def test_registry_risolve_cartella_reale_verbali_auto(monkeypatch):
    monkeypatch.setattr(
        drive_folder_registry.settings,
        "DRIVE_FOLDER_REGISTRY_JSON",
        '{"folders":[{"area":"verbali_auto","label":"Verbali Auto",'
        '"folder_id":"verbali-folder"}]}',
    )

    assert drive_folder_registry.get_folder_id("verbale") == "verbali-folder"
    assert drive_folder_registry.get_folder_id("verbali") == "verbali-folder"
    catalog = drive_folder_registry.get_public_catalog()
    assert catalog["folders"][0]["mode"] == "automatico"


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


class _DriveService:
    def __init__(self):
        self.files_api = _DriveFiles()

    def files(self):
        return self.files_api


def test_archivio_usa_elaborate_e_registra_quota_account_servizio(monkeypatch):
    service = _DriveService()
    monkeypatch.setattr(email_drive_archive, "get_folder_id", lambda area: "verbali-root")
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
