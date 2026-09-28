import asyncio
import base64

import pytest

from app.services import f24_originale


def test_originale_f24_storico_embedded():
    content = b"%PDF-storico"
    result = asyncio.run(f24_originale.carica_originale({
        "pdf_data": base64.b64encode(content).decode("ascii")
    }))
    assert result == content


def test_originale_quietanza_drive_letto_per_id(monkeypatch):
    async def fake_download(file_id):
        assert file_id == "drive-q-1"
        return b"%PDF-drive"

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", fake_download)
    result = asyncio.run(f24_originale.carica_originale(
        {"drive_file_id": "drive-q-1"}, tipo="quietanza",
    ))
    assert result == b"%PDF-drive"


def test_originale_f24_rifiuta_contenuto_non_pdf(monkeypatch):
    async def fake_download(_file_id):
        return b"contenuto-errato"

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", fake_download)
    with pytest.raises(ValueError, match="non e' un PDF"):
        asyncio.run(f24_originale.carica_originale({"drive_file_id": "drive-f24-1"}))
