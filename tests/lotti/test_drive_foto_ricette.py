import pytest

from app.lotti.servizi import drive_foto_ricette as foto_drive


class _Get:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Files:
    def __init__(self, payload):
        self.payload = payload

    def get(self, **_kwargs):
        return _Get(self.payload)


class _Service:
    def __init__(self, payload):
        self._files = _Files(payload)

    def files(self):
        return self._files


def test_metadata_accetta_solo_file_nella_cartella_ricette():
    metadata = {
        "id": "foto-1", "name": "ricetta.png", "mimeType": "image/png",
        "size": "10", "parents": ["cartella-ricette"], "trashed": False,
    }
    assert foto_drive._metadata(
        _Service(metadata), "foto-1", folder_id="cartella-ricette"
    )["id"] == "foto-1"

    fuori = {**metadata, "parents": ["altra-cartella"]}
    with pytest.raises(FileNotFoundError):
        foto_drive._metadata(_Service(fuori), "foto-1", folder_id="cartella-ricette")

    cestinata = {**metadata, "trashed": True}
    with pytest.raises(FileNotFoundError):
        foto_drive._metadata(_Service(cestinata), "foto-1", folder_id="cartella-ricette")


def test_cestina_verifica_cartella_prima_di_spostare_il_file():
    metadata = {
        "id": "foto-1", "name": "foto.png", "mimeType": "image/png",
        "size": "3", "parents": ["cartella-ricette"], "trashed": False,
    }

    class _Update:
        def execute(self):
            return {**metadata, "trashed": True}

    class _FilesConUpdate(_Files):
        def __init__(self, payload):
            super().__init__(payload)
            self.updated = None

        def update(self, **kwargs):
            self.updated = kwargs
            return _Update()

    files = _FilesConUpdate(metadata)
    service = type("Service", (), {"files": lambda self: files})()

    result = foto_drive.cestina(
        "foto-1", folder_id="cartella-ricette", service=service
    )

    assert result == {"id": "foto-1", "trashed": True}
    assert files.updated["body"] == {"trashed": True}


def test_credenziale_provata_sulla_cartella_della_foto(monkeypatch):
    """La foto non dipende dalla cartella di un altro canale (es. cedolini)."""
    from app.services import drive_credential_probe

    provate = []

    def finta_probe(folder_id):
        provate.append(folder_id)
        return None, "nessun accesso"

    monkeypatch.setattr(drive_credential_probe, "load_credentials_for_folder", finta_probe)
    with pytest.raises(RuntimeError):
        foto_drive.leggi("foto-1", folder_id="cartella-ricette")
    assert provate == ["cartella-ricette"]
