from app.config import settings
from app.services import drive_invoice_ingest as drive
from mongomock_motor import AsyncMongoMockClient


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
        self.closed = 0

    def files(self):
        return self.resource

    def close(self):
        self.closed += 1


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


def test_ricostruzione_rilegge_tutte_le_cartelle_senza_spostare_file(monkeypatch):
    service = _Service()
    db = AsyncMongoMockClient()["test"]
    files = {
        "root": [{"id": "1", "name": "uno.xml"}],
        "inbox": [{"id": "2", "name": "due.xml"}],
        "done": [{"id": "1", "name": "uno.xml"}],
        "errors": [{"id": "3", "name": "tre.xml"}],
    }

    monkeypatch.setattr(drive, "is_configured", lambda: True)
    monkeypatch.setattr(drive, "_load_credentials_fatture", lambda: ({}, None))
    monkeypatch.setattr(drive, "_build_drive_service", lambda: service)
    monkeypatch.setattr(drive, "_folder_id", lambda: "root")
    monkeypatch.setattr(drive, "_source_folders", lambda *_: [
        ("radice", "root"), ("Da elaborare", "inbox"),
        ("Elaborate", "done"), ("Errori", "errors"),
    ])
    monkeypatch.setattr(drive, "_list_xml_files", lambda _service, folder: files[folder])
    monkeypatch.setattr(drive, "_download_bytes", lambda _service, file_id: file_id.encode())

    async def fake_process(_db, content, filename, **kwargs):
        assert kwargs["source"] == "ricostruzione_drive"
        assert kwargs["applica_filtro_anno"] is True
        assert kwargs["replay_storico"] is True
        return {"status": "duplicate" if filename == "uno.xml" else "imported"}

    from app.routers.invoices import fatture_upload
    monkeypatch.setattr(fatture_upload, "process_xml_bytes", fake_process)

    result = __import__("asyncio").run(drive.ricostruisci_archivio_drive(db))

    assert result["status"] == "ok"
    assert result["total"] == 3
    assert result["processed"] == 3
    assert result["duplicates"] == 1
    assert result["imported"] == 2
    assert service.resource.updated == []


def test_ricostruzione_web_riprende_dal_cursore_senza_spostare_file(monkeypatch):
    service = _Service()
    db = AsyncMongoMockClient()["test_lotti"]
    files = {
        "root": [{"id": "1", "name": "uno.xml"}],
        "inbox": [{"id": "2", "name": "due.xml"}],
        "done": [{"id": "1", "name": "uno.xml"}],
        "errors": [{"id": "3", "name": "tre.xml"}],
    }

    monkeypatch.setattr(drive, "is_configured", lambda: True)
    monkeypatch.setattr(drive, "_load_credentials_fatture", lambda: ({}, None))
    monkeypatch.setattr(drive, "_build_drive_service", lambda: service)
    monkeypatch.setattr(drive, "_folder_id", lambda: "root")
    monkeypatch.setattr(drive, "_source_folders", lambda *_: [
        ("radice", "root"), ("Da elaborare", "inbox"),
        ("Elaborate", "done"), ("Errori", "errors"),
    ])
    monkeypatch.setattr(drive, "_list_xml_files", lambda _service, folder: files[folder])
    monkeypatch.setattr(drive, "_download_bytes", lambda _service, file_id: file_id.encode())

    calls = []

    async def fake_process(_db, content, filename, **kwargs):
        calls.append(filename)
        assert kwargs["replay_storico"] is True
        return {"status": "duplicate" if filename == "uno.xml" else "imported"}

    from app.routers.invoices import fatture_upload
    monkeypatch.setattr(fatture_upload, "process_xml_bytes", fake_process)

    first = __import__("asyncio").run(
        drive.ricostruisci_archivio_drive_lotto(db, batch_size=2, reset=True)
    )
    second = __import__("asyncio").run(
        drive.ricostruisci_archivio_drive_lotto(db, batch_size=2)
    )

    assert first["status"] == "pending"
    assert first["processed"] == 2
    assert first["pending"] == 1
    assert first["cursor"] == "2"
    assert second["status"] == "ok"
    assert second["processed"] == 3
    assert second["pending"] == 0
    assert second["duplicates"] == 1
    assert second["imported"] == 2
    assert calls == ["uno.xml", "due.xml", "tre.xml"]
    assert service.resource.updated == []
    assert service.closed == 2


def test_ricostruzione_web_isola_file_che_ha_interrotto_il_processo(monkeypatch):
    service = _Service()
    db = AsyncMongoMockClient()["test_quarantena"]
    files = {
        "root": [
            {"id": "1", "name": "uno.xml"},
            {"id": "2", "name": "corrotto.xml.p7m"},
            {"id": "3", "name": "tre.xml"},
        ],
    }

    monkeypatch.setattr(drive, "is_configured", lambda: True)
    monkeypatch.setattr(drive, "_load_credentials_fatture", lambda: ({}, None))
    monkeypatch.setattr(drive, "_build_drive_service", lambda: service)
    monkeypatch.setattr(drive, "_folder_id", lambda: "root")
    monkeypatch.setattr(drive, "_source_folders", lambda *_: [("radice", "root")])
    monkeypatch.setattr(drive, "_list_xml_files", lambda _service, folder: files[folder])
    monkeypatch.setattr(drive, "_download_bytes", lambda _service, file_id: file_id.encode())

    __import__("asyncio").run(db["drive_sync_state"].insert_one({
        "_id": "fatture_drive",
        "last_rebuild_result": {
            "status": "processing",
            "total": 3,
            "processed": 1,
            "cursor": "1",
            "inflight": {"id": "2", "name": "corrotto.xml.p7m"},
            "imported": 1,
            "duplicates": 0,
            "archiviate": 0,
            "errors": 0,
            "started_at": "2026-08-21T00:00:00+00:00",
        },
    }))

    calls = []

    async def fake_process(_db, content, filename, **kwargs):
        calls.append(filename)
        return {"status": "imported"}

    from app.routers.invoices import fatture_upload
    monkeypatch.setattr(fatture_upload, "process_xml_bytes", fake_process)

    result = __import__("asyncio").run(
        drive.ricostruisci_archivio_drive_lotto(db, batch_size=1)
    )

    assert result["status"] == "ok"
    assert result["processed"] == 3
    assert result["pending"] == 0
    assert result["imported"] == 2
    assert result["errors"] == 1
    assert result["cursor"] == "3"
    assert calls == ["tre.xml"]
    assert result["details"][-1]["file"] == "corrotto.xml.p7m"
    assert service.closed == 1
