"""La sentinella del loop nomina la funzione che tiene fermo il processo."""
import asyncio
import logging
import time

from app.services import sorveglianza_loop


def _lavoro_pesante_senza_cedere(secondi: float) -> None:
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        pass


def test_un_blocco_del_loop_finisce_nel_log_con_il_nome_della_funzione(caplog, monkeypatch):
    monkeypatch.setattr(sorveglianza_loop, "SOGLIA_SECONDI", 0.3)
    monkeypatch.setattr(sorveglianza_loop, "PASSO_SECONDI", 0.05)
    caplog.set_level(logging.WARNING, logger=sorveglianza_loop.__name__)

    async def scenario():
        sorveglianza_loop.avvia()
        try:
            await asyncio.sleep(0.15)
            _lavoro_pesante_senza_cedere(0.9)
            await asyncio.sleep(0.3)
        finally:
            sorveglianza_loop.arresta()

    asyncio.run(scenario())

    messaggi = [r.getMessage() for r in caplog.records]
    bloccato = [m for m in messaggi if "fermo da" in m]
    assert bloccato, messaggi
    assert "_lavoro_pesante_senza_cedere" in bloccato[0]
    assert any("ripartito dopo" in m for m in messaggi)


def test_un_loop_che_respira_non_scrive_niente(caplog, monkeypatch):
    monkeypatch.setattr(sorveglianza_loop, "SOGLIA_SECONDI", 0.3)
    monkeypatch.setattr(sorveglianza_loop, "PASSO_SECONDI", 0.05)
    caplog.set_level(logging.WARNING, logger=sorveglianza_loop.__name__)

    async def scenario():
        sorveglianza_loop.avvia()
        try:
            for _ in range(10):
                await asyncio.sleep(0.05)
        finally:
            sorveglianza_loop.arresta()

    asyncio.run(scenario())
    assert not [r for r in caplog.records if "loop bloccato" in r.getMessage()]
