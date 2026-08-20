from app.config import settings
from app.services import drive_invoice_ingest as drive


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class _Files:
    def __init__(self):
        self.created = []
        self.updated = []

    def list(self, **kwargs):
        return _Request({"files": []})

    def create(self, body, **kwargs):
        self.created.append(body)
        return _Request({"id": f"folder-{len(self.created)}"})

    def update(self, **kwargs):
        self.updated.append(kwargs)
        return _Request({"id": kwargs["fileId"], "parents": [kwargs["addParents"]]})


class _Service:
    def __init__(self):
        self.resource = _Files()

    def files(self):
        return self.resource


def test_crea_le_tre_cartelle_e_sposta_senza_cancellare():
    service = _Service()

    inbox = drive._get_or_create_inbox_folder(service, "root")
    elaborate = drive._get_or_create_elaborate_folder(service, "root")
    errors = drive._get_or_create_error_folder(service, "root")
    drive._move_to_folder(service, "documento-1", inbox, elaborate)

    assert [item["name"] for item in service.resource.created] == [
        "Da elaborare", "Elaborate", "Errori"
    ]
    assert errors == "folder-3"
    assert service.resource.updated == [{
        "fileId": "documento-1",
        "addParents": elaborate,
        "removeParents": inbox,
        "fields": "id, parents",
        "supportsAllDrives": True,
    }]


def test_nome_canonico_render_configura_fatture(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_FATTURE_FOLDER_ID", "folder-private")
    monkeypatch.setattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_FILE", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_JSON", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "{}")
    monkeypatch.setattr(settings, "ENABLE_DRIVE_FATTURE_SYNC", True)

    assert drive._folder_id() == "folder-private"
    assert drive.is_configured() is True


def test_import_fatture_seleziona_un_lotto_limitato(monkeypatch):
    monkeypatch.setattr(settings, "DRIVE_FATTURE_BATCH_SIZE", 3)
    files = [{"id": str(index), "name": f"{index}.xml"} for index in range(8)]

    assert [item["id"] for item in drive._select_batch(files)] == ["0", "1", "2"]


def test_dimensione_lotto_fatture_e_sempre_sicura(monkeypatch):
    monkeypatch.setattr(settings, "DRIVE_FATTURE_BATCH_SIZE", 0)
    assert drive._batch_size() == 1
    monkeypatch.setattr(settings, "DRIVE_FATTURE_BATCH_SIZE", 1000)
    assert drive._batch_size() == 100
