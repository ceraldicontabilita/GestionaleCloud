"""L'OCR non deve mai far morire il servizio per memoria esaurita (502 su ogni pagina, 01/10/2026)."""
import asyncio
import sys
import types

import pytest

from app.services import memoria_processo, ocr_locale


def _memoria(monkeypatch, rss, limite=2048.0):
    monkeypatch.setattr(memoria_processo, "rss_mb", lambda: rss)
    monkeypatch.setattr(memoria_processo, "limite_mb", lambda: limite)


def test_con_poca_memoria_libera_l_ocr_non_parte_e_il_file_si_riprova(monkeypatch):
    _memoria(monkeypatch, 1400.0)              # il picco vero fu 1,4 -> 1,8 GB su 2 GB
    with pytest.raises(ocr_locale.MemoriaInsufficiente) as errore:
        ocr_locale.verifica_memoria()
    assert errore.value.status_code == 503 and errore.value.rinviabile is True
    assert "da ripassare" in errore.value.detail


def test_a_riposo_c_e_posto_per_il_motore_e_fuori_da_linux_non_si_blocca(monkeypatch):
    _memoria(monkeypatch, 1150.0)
    ocr_locale.verifica_memoria()              # 1150 + 600 < 95% di 2048
    _memoria(monkeypatch, None)                # senza /proc non si misura: nessun limite inventato
    ocr_locale.verifica_memoria()


def test_il_motore_si_libera_dopo_ogni_documento(monkeypatch):
    creati, liberati = [], []

    class Motore:
        def __init__(self):
            creati.append(self)

    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", types.SimpleNamespace(RapidOCR=Motore))
    monkeypatch.setattr(memoria_processo, "restituisci", lambda: liberati.append(1) or {})
    _memoria(monkeypatch, 900.0)
    with ocr_locale.motore() as primo:
        assert isinstance(primo, Motore)
    with ocr_locale.motore():
        pass
    assert len(creati) == 2 and len(liberati) == 2      # un motore per documento, mai una quota permanente


def test_senza_memoria_il_motore_non_si_crea(monkeypatch):
    creati = []
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", types.SimpleNamespace(
        RapidOCR=lambda: creati.append(1)))
    _memoria(monkeypatch, 1700.0)
    with pytest.raises(ocr_locale.MemoriaInsufficiente):
        with ocr_locale.motore():
            pass
    assert creati == []


def test_la_cartella_unica_rinvia_il_file_e_non_lo_manda_in_errori(monkeypatch):
    from app.routers import documenti
    from app.services import drive_cartella_unica as cu

    async def tipo(_nome, _contenuto):
        return "ricevuta_pagopa"

    async def carica(file):
        raise ocr_locale.MemoriaInsufficiente(1700.0, 2048.0)

    monkeypatch.setattr(documenti, "rileva_tipo_documento", tipo)
    monkeypatch.setattr(documenti, "upload_documento_automatico", carica)
    risultato = asyncio.run(cu._smista("scansione.pdf", b"%PDF-x", {}))
    assert risultato["rinviato"] is True and risultato["http_status"] == 503
