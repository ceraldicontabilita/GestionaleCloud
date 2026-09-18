import asyncio
import base64

import pytest

from app.services import cedolino_originale


def test_originale_storico_embedded():
    content = b"%PDF-storico"
    result = asyncio.run(cedolino_originale.carica_originale({
        "pdf_data": base64.b64encode(content).decode("ascii")
    }))
    assert result == content


def test_originale_drive_letto_per_id(monkeypatch):
    async def fake_download(file_id):
        assert file_id == "drive-1"
        return b"%PDF-drive"

    import app.services.drive_cedolini_ingest as ingest
    monkeypatch.setattr(ingest, "download_file_by_id", fake_download)
    result = asyncio.run(cedolino_originale.carica_originale({"drive_file_id": "drive-1"}))
    assert result == b"%PDF-drive"


def test_originale_rifiuta_contenuto_non_pdf(monkeypatch):
    async def fake_download(_file_id):
        return b"contenuto-errato"

    import app.services.drive_cedolini_ingest as ingest
    monkeypatch.setattr(ingest, "download_file_by_id", fake_download)
    with pytest.raises(ValueError, match="non è un PDF"):
        asyncio.run(cedolino_originale.carica_originale({"drive_file_id": "drive-1"}))
