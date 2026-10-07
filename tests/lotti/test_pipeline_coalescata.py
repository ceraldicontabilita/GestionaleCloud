"""La pipeline post-import parte una volta per ondata di fatture, non per fattura.

07/10/2026: ogni fattura del ponte avviava ``esegui_pipeline_post_import``
(~210 s, ricostruzione completa di prodotti_master) con ``create_task``; a
decine sovrapposte tenevano fermo il loop, Render non riceveva /api/health
e riavviava l'istanza uccidendo il giro della cartella unica.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.lotti import bulk_compat
from app.lotti.routers import pipeline as mod


@pytest.fixture(autouse=True)
def _pipeline_veloce(monkeypatch):
    monkeypatch.setattr(mod, "QUIETE_PIPELINE_S", 0.05)
    monkeypatch.setitem(mod._richiesta, "task", None)
    monkeypatch.setitem(mod._richiesta, "motivi", [])
    monkeypatch.setitem(mod._richiesta, "ultima", 0.0)


def test_dieci_fatture_una_pipeline(monkeypatch):
    eseguita = AsyncMock(return_value={"esito": "OK"})
    monkeypatch.setattr(mod, "esegui_pipeline_post_import", eseguita)

    async def scenario():
        avviati = [mod.richiedi_pipeline_post_import(f"xml_manuale_{i}") for i in range(10)]
        assert avviati == [True] + [False] * 9
        await mod._richiesta["task"]
        return eseguita.await_args_list

    chiamate = asyncio.run(scenario())
    assert len(chiamate) == 1
    assert chiamate[0].kwargs["motivo"] == "import_coalescato_10_richieste"


def test_le_richieste_durante_la_quiete_rinviano_la_partenza(monkeypatch):
    eseguita = AsyncMock(return_value={"esito": "OK"})
    monkeypatch.setattr(mod, "esegui_pipeline_post_import", eseguita)

    async def scenario():
        mod.richiedi_pipeline_post_import("prima")
        for _ in range(3):
            await asyncio.sleep(0.03)  # sotto la quiete: la partenza slitta
            assert eseguita.await_count == 0
            mod.richiedi_pipeline_post_import("ancora")
        await mod._richiesta["task"]

    asyncio.run(scenario())
    assert eseguita.await_count == 1
    assert eseguita.await_args.kwargs["motivo"] == "import_coalescato_4_richieste"


def test_una_richiesta_mentre_gira_vale_un_solo_giro_in_piu(monkeypatch):
    in_corso = asyncio.Event()

    async def lenta(motivo):
        in_corso.set()
        await asyncio.sleep(0.1)
        return {"esito": "OK", "motivo": motivo}

    eseguita = AsyncMock(side_effect=lenta)
    monkeypatch.setattr(mod, "esegui_pipeline_post_import", eseguita)

    async def scenario():
        mod.richiedi_pipeline_post_import("prima")
        await in_corso.wait()
        for i in range(5):
            assert mod.richiedi_pipeline_post_import(f"durante_{i}") is False
        await mod._richiesta["task"]

    asyncio.run(scenario())
    assert eseguita.await_count == 2
    assert [c.kwargs["motivo"] for c in eseguita.await_args_list] == [
        "import_coalescato_1_richieste", "import_coalescato_5_richieste"]


def test_una_pipeline_fallita_non_ferma_la_prossima(monkeypatch):
    eseguita = AsyncMock(side_effect=[RuntimeError("guasto"), {"esito": "OK"}])
    monkeypatch.setattr(mod, "esegui_pipeline_post_import", eseguita)

    async def scenario():
        mod.richiedi_pipeline_post_import("prima")
        await mod._richiesta["task"]
        assert mod.richiedi_pipeline_post_import("seconda") is True
        await mod._richiesta["task"]

    asyncio.run(scenario())
    assert eseguita.await_count == 2


def test_bulk_write_cede_il_loop_ogni_poche_operazioni():
    from pymongo import UpdateOne

    class _Esito:
        matched_count = 1
        modified_count = 1
        upserted_id = None

    class _Collezione:
        async def update_one(self, *_a, **_k):
            return _Esito()

    battiti = 0

    async def cuore():
        nonlocal battiti
        while True:
            battiti += 1
            await asyncio.sleep(0)

    async def scenario():
        compito = asyncio.create_task(cuore())
        ops = [UpdateOne({"key": str(i)}, {"$set": {"n": i}}, upsert=True) for i in range(200)]
        esito = await bulk_compat.bulk_write_compat(_Collezione(), ops, ordered=False)
        compito.cancel()
        return esito

    esito = asyncio.run(scenario())
    assert esito.matched_count == 200
    # la prima operazione non cede: 200 ops → 7 pause
    assert battiti >= 200 // bulk_compat.OPERAZIONI_PER_RESPIRO - 1
