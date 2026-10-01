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


@pytest.mark.parametrize(("modulo", "tipo"), [
    ("app.services.cedolino_originale", None),
    ("app.services.f24_originale", "f24"),
    ("app.services.f24_originale", "quietanza"),
])
def test_originali_per_id_passano_dalla_cartella_unica(monkeypatch, modulo, tipo):
    import importlib

    lettore = importlib.import_module(modulo)

    async def _finto(file_id, md5=None):
        return b"%PDF-" + file_id.encode()

    monkeypatch.setattr(drive_download, "scarica_originale", _finto)
    doc = {"drive_file_id": "x1"}
    esito = lettore.carica_originale(doc) if tipo is None else lettore.carica_originale(doc, tipo=tipo)
    assert asyncio.run(esito) == b"%PDF-x1"


def test_servizio_indice_usa_la_cartella_unica(monkeypatch):
    from app.services import drive_document_index

    sentinella = object()
    monkeypatch.setattr(cu, "_service", lambda: sentinella)
    assert drive_document_index.build_drive_service() is sentinella


def test_originale_sparito_si_cerca_la_copia_nel_protocollo(monkeypatch):
    """L'API Drive non cerca per MD5 (400): la copia viva si trova nel protocollo."""
    class _Servizio:
        def close(self):
            pass

    chiesti = []

    def _scarica(_s, file_id, conferma_abuso=False):
        chiesti.append(file_id)
        if file_id == "sparito":
            raise RuntimeError("File not found")
        return b"%PDF-copia"

    async def _altro(md5, escluso):
        assert escluso == "sparito"
        return "viva"

    monkeypatch.setattr(cu, "_service", lambda: _Servizio())
    monkeypatch.setattr(drive_download, "scarica_bytes", _scarica)
    monkeypatch.setattr(drive_download, "_altro_id_per_md5", _altro)

    assert asyncio.run(drive_download.scarica_originale("sparito", md5="a" * 32)) == b"%PDF-copia"
    assert chiesti == ["sparito", "viva"]


def test_file_segnalato_come_malware_si_riprova_con_la_conferma(monkeypatch):
    class _Servizio:
        def close(self):
            pass

    def _scarica(_s, file_id, conferma_abuso=False):
        if not conferma_abuso:
            raise RuntimeError("cannotDownloadAbusiveFile")
        return b"%PDF-ok"

    monkeypatch.setattr(cu, "_service", lambda: _Servizio())
    monkeypatch.setattr(drive_download, "scarica_bytes", _scarica)
    assert asyncio.run(drive_download.scarica_originale("x")) == b"%PDF-ok"
