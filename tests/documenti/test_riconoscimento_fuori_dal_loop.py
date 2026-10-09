"""Il riconoscimento di un documento non ferma il server.

``detect_document_type`` legge il PDF e, per una scansione, avvia l'OCR: decine
di secondi di CPU. Chiamato sul loop (lo faceva la simulazione della cartella unica)
fermava anche ``/api/health`` e Render riavviava l'istanza (502).
"""
import asyncio
import time

from app.routers import documenti
from app.services import drive_cartella_unica


def _loop_resta_libero(monkeypatch, chiamata):
    def lento(*_a):
        time.sleep(0.4)
        return "auto"

    monkeypatch.setattr(documenti, "detect_document_type", lento)

    async def scenario():
        battiti = 0

        async def battito():
            nonlocal battiti
            while True:
                await asyncio.sleep(0.02)
                battiti += 1

        tic = asyncio.create_task(battito())
        await chiamata()
        tic.cancel()
        return battiti

    return asyncio.run(scenario())


def test_lo_smistatore_riconosce_il_file_senza_fermare_il_loop(monkeypatch):
    battiti = _loop_resta_libero(
        monkeypatch, lambda: drive_cartella_unica._smista("scan.pdf", b"%PDF-", {}),
    )
    assert battiti >= 5
