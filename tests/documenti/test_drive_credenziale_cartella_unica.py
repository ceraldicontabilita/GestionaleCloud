"""I servizi Drive generici provano la credenziale sulla cartella unica.

Smontata la cartella del canale cedolini, ogni pagina che apriva un file Drive
rispondeva «nessun service account configurato ha accesso al folder Drive
canonico …»: la credenziale si provava su una cartella che non c'e' piu'.
"""
import asyncio

import pytest

from app.services import drive_cartella_unica as cu
from app.services import drive_download


def test_scarica_originale_usa_la_credenziale_della_cartella_unica(monkeypatch):
    usato = []

    class _Servizio:
        def close(self):
            usato.append("chiuso")

    monkeypatch.setattr(cu, "_service", lambda: usato.append("cartella_unica") or _Servizio())
    monkeypatch.setattr(drive_download, "scarica_bytes", lambda _s, file_id: b"%PDF-" + file_id.encode())

    assert asyncio.run(drive_download.scarica_originale("abc")) == b"%PDF-abc"
    assert usato == ["cartella_unica", "chiuso"]


def test_scarica_originale_senza_credenziale_non_esplode(monkeypatch):
    def _nessuna():
        raise RuntimeError("credenziali Drive non disponibili: cartella non configurata")

    monkeypatch.setattr(cu, "_service", _nessuna)
    assert asyncio.run(drive_download.scarica_originale("abc")) == b""
    assert asyncio.run(drive_download.scarica_originale("")) == b""


@pytest.mark.parametrize("modulo", [
    "app.services.drive_cedolini_ingest",
    "app.services.drive_f24_ingest",
    "app.services.drive_quietanze_ingest",
])
def test_originali_dei_canali_passano_dalla_cartella_unica(monkeypatch, modulo):
    import importlib

    ingest = importlib.import_module(modulo)

    async def _finto(file_id):
        return b"%PDF-" + file_id.encode()

    monkeypatch.setattr(drive_download, "scarica_originale", _finto)
    assert asyncio.run(ingest.download_file_by_id("x1")) == b"%PDF-x1"


def test_servizio_indice_e_registro_fiscale_usano_la_cartella_unica(monkeypatch):
    from app.services import drive_document_index, drive_fiscal_registry

    sentinella = object()
    monkeypatch.setattr(cu, "_service", lambda: sentinella)
    assert drive_document_index.build_drive_service() is sentinella
    assert drive_fiscal_registry.build_drive_service() is sentinella
