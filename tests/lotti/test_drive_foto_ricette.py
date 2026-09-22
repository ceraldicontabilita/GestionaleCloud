import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

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


def test_nome_drive_e_immutabile_per_contenuto():
    assert foto_drive._nome_file("ricetta/uno", "a" * 64, "image/png") == (
        "uno_aaaaaaaaaaaaaaaa.png"
    )


def test_cartella_ricette_risolta_dal_registro_canonico(monkeypatch):
    monkeypatch.setattr(
        foto_drive.settings, "GOOGLE_DRIVE_RICETTE_IMAGES_FOLDER_ID", None
    )
    db = AsyncMongoMockClient()["Gestionale_Test"]
    asyncio.run(db["drive_folder_registry"].insert_one({
        "area": "ricette_immagini",
        "folder_id": "cartella-supabase",
        "source": "manual_owner_verified",
    }))
    assert asyncio.run(foto_drive.risolvi_folder_id(db)) == "cartella-supabase"


def test_cartella_ricette_rifiuta_record_senza_provenienza(monkeypatch):
    monkeypatch.setattr(
        foto_drive.settings, "GOOGLE_DRIVE_RICETTE_IMAGES_FOLDER_ID", None
    )
    db = AsyncMongoMockClient()["Gestionale_Test"]
    asyncio.run(db["drive_folder_registry"].insert_one({
        "area": "ricette_immagini", "folder_id": "cartella-non-provata"
    }))
    with pytest.raises(RuntimeError, match="registro canonico"):
        asyncio.run(foto_drive.risolvi_folder_id(db))
