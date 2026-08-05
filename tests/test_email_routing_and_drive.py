from app.services.email_drive_archive import route_for_document_type
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
