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
    async def fake_download(file_id, md5=None):
        assert file_id == "drive-q-1"
        return b"%PDF-drive"

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", fake_download)
    result = asyncio.run(f24_originale.carica_originale(
        {"drive_file_id": "drive-q-1"}, tipo="quietanza",
    ))
    assert result == b"%PDF-drive"


def test_originale_f24_rifiuta_contenuto_non_pdf(monkeypatch):
    async def fake_download(_file_id, md5=None):
        return b"contenuto-errato"

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", fake_download)
    with pytest.raises(ValueError, match="non è un PDF"):
        asyncio.run(f24_originale.carica_originale({"drive_file_id": "drive-f24-1"}))


def _drive_finto(monkeypatch, *, scaricabili, copia_md5=None):
    """Drive finto: solo gli id in `scaricabili` si scaricano; la ricerca per MD5 (nel protocollo Drive) dà `copia_md5`."""
    import app.services.drive_cartella_unica as cu
    import app.services.drive_download as dd

    class Rifiutato(Exception):
        pass

    class Service:
        def close(self):
            pass

    monkeypatch.setattr(cu, "_service", lambda: Service())

    def scarica(_service, file_id, **_):
        if file_id not in scaricabili:
            raise Rifiutato("404 file non trovato")
        return scaricabili[file_id]

    monkeypatch.setattr(dd, "scarica_bytes", scarica)

    async def altro_id(_md5, _escluso):
        return copia_md5

    monkeypatch.setattr(dd, "_altro_id_per_md5", altro_id)
    return dd


def test_quietanza_con_id_drive_rifiutato_si_apre_dalla_copia_con_lo_stesso_md5(monkeypatch):
    dd = _drive_finto(monkeypatch, scaricabili={"copia": b"%PDF-copia"}, copia_md5="copia")

    assert asyncio.run(dd.scarica_originale("cestino", md5="a" * 32)) == b"%PDF-copia"


def test_quietanza_senza_nessuna_copia_da_vuoto_e_non_un_errore(monkeypatch):
    dd = _drive_finto(monkeypatch, scaricabili={}, copia_md5=None)

    assert asyncio.run(dd.scarica_originale("cestino", md5="a" * 32)) == b""
    assert asyncio.run(dd.scarica_originale("cestino")) == b""
