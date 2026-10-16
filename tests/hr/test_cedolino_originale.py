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


def test_originale_recupera_il_blob_persistente(monkeypatch):
    class Archivio:
        async def get(self, key):
            assert key == "sha256:cedolino"
            return base64.b64encode(b"%PDF-da-blob").decode("ascii")

    monkeypatch.setattr("app.services.blob_store.blob_store_per_runtime", lambda _runtime: Archivio())
    result = asyncio.run(cedolino_originale.carica_originale({"blob_key": "sha256:cedolino"}))
    assert result == b"%PDF-da-blob"


def test_originale_drive_letto_per_id(monkeypatch):
    async def fake_download(file_id, md5=None):
        assert file_id == "drive-1"
        return b"%PDF-drive"

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", fake_download)
    result = asyncio.run(cedolino_originale.carica_originale({"drive_file_id": "drive-1"}))
    assert result == b"%PDF-drive"


def test_originale_rifiuta_contenuto_non_pdf(monkeypatch):
    async def fake_download(_file_id, md5=None):
        return b"contenuto-errato"

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", fake_download)
    with pytest.raises(ValueError, match="non è un PDF"):
        asyncio.run(cedolino_originale.carica_originale({"drive_file_id": "drive-1"}))


@pytest.mark.parametrize("da_drive", [True, False])
def test_fascicolo_mostra_solo_le_pagine_del_dipendente(monkeypatch, da_drive):
    import fitz

    with fitz.open() as pdf:
        for nome in ("ROSSI MARIO", "BIANCHI ANNA", "VERDI LUCA"):
            pdf.new_page().insert_text((40, 40), nome)
        content = pdf.tobytes()

    async def download(*args, **kwargs):
        return content

    monkeypatch.setattr("app.services.drive_download.scarica_originale", download)
    source = {"drive_file_id": "fascicolo"} if da_drive else {
        "pdf_data": base64.b64encode(content).decode()}
    result = asyncio.run(cedolino_originale.carica_originale({
        **source, "source_page_start": 2, "source_page_end": 2, "source_document_pages": 3,
    }))
    with fitz.open(stream=result, filetype="pdf") as selected:
        assert len(selected) == 1
        assert "BIANCHI ANNA" in selected[0].get_text()
        assert "ROSSI" not in selected[0].get_text()


def test_copia_gia_separata_non_viene_tagliata_di_nuovo():
    import fitz

    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), "BIANCHI ANNA")
        content = pdf.tobytes()
    result = asyncio.run(cedolino_originale.carica_originale({
        "pdf_data": base64.b64encode(content).decode(),
        "source_page_start": 2, "source_page_end": 2, "source_document_pages": 3,
    }))
    assert result == content


def test_pagine_incoerenti_non_espongono_il_fascicolo():
    import fitz

    with fitz.open() as pdf:
        pdf.new_page()
        pdf.new_page()
        content = pdf.tobytes()
    with pytest.raises(ValueError, match="pagine"):
        asyncio.run(cedolino_originale.carica_originale({
            "pdf_data": base64.b64encode(content).decode(),
            "source_page_start": 2, "source_page_end": 2, "source_document_pages": 3,
        }))


def test_deposito_hr_conserva_pagine_e_impronta():
    from app.services.hr_cedolini_deposito import mappa_cedolino_per_hr

    mapped = mappa_cedolino_per_hr({
        "codice_fiscale": "RSSMRA80A01H501Z", "anno": 2026, "mese": 1,
        "drive_file_id": "fascicolo", "drive_md5": "a" * 32,
        "source_page_start": 2, "source_page_end": 3, "source_document_pages": 10,
    })
    assert mapped["source_page_start"] == 2
    assert mapped["source_page_end"] == 3
    assert mapped["source_document_pages"] == 10
    assert mapped["drive_md5"] == "a" * 32


def test_download_non_associa_allegati_di_un_altro_dipendente(monkeypatch):
    from fastapi import HTTPException
    from app.hr.routers import cedolini
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria

    db = ClientArchivioMemoria()["download-isolato"]
    monkeypatch.setattr(cedolini.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db.cedolini.insert_one({"id": "busta-1", "mese": 1, "anno": 2026})
        await db.cedolini_email_attachments.insert_one({
            "id": "altro-dipendente", "filename": "cedolino.pdf", "mese": 1, "anno": 2026,
            "associato": False, "pdf_data": base64.b64encode(b"%PDF-altro").decode(),
        })
        before = await db.cedolini_email_attachments.find_one({})
        with pytest.raises(HTTPException) as error:
            await cedolini.download_cedolino_pdf("busta-1")
        assert error.value.status_code == 404
        assert await db.cedolini_email_attachments.find_one({}) == before
        assert "pdf_data" not in await db.cedolini.find_one({})

    asyncio.run(scenario())


def test_vecchia_correzione_non_inventa_il_netto(monkeypatch):
    from fastapi import HTTPException
    from app.hr.routers import cedolini

    monkeypatch.setattr(cedolini.Database, "get_db",
                        lambda: pytest.fail("La stima non deve leggere o scrivere cedolini"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(cedolini.correggi_cedolini_problematici())
    assert error.value.status_code == 410
    assert "importo verificato" in error.value.detail


def test_cedolino_hr_storico_recupera_pagine_dal_collegamento_erp(monkeypatch):
    import fitz
    from app.database import Database
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria

    db = ClientArchivioMemoria()["pagine-storiche"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    with fitz.open() as pdf:
        for nome in ("ALTRO DIPENDENTE", "DIPENDENTE SELEZIONATO"):
            pdf.new_page().insert_text((40, 40), nome)
        content = pdf.tobytes()

    async def download(*args, **kwargs):
        return content

    monkeypatch.setattr("app.services.drive_download.scarica_originale", download)

    async def scenario():
        await db.cedolini.insert_one({"id": "erp-1", "drive_file_id": "fascicolo",
                                     "source_page_start": 2, "source_page_end": 2,
                                     "source_document_pages": 2})
        return await cedolino_originale.carica_originale({
            "gestionale_cedolino_id": "erp-1", "drive_file_id": "fascicolo"})

    result = asyncio.run(scenario())
    with fitz.open(stream=result, filetype="pdf") as selected:
        assert len(selected) == 1
        assert "DIPENDENTE SELEZIONATO" in selected[0].get_text()
