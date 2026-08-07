import asyncio

from app.routers.operazioni_module import smart


def test_riconciliazione_http_parte_in_background(monkeypatch):
    async def scenario():
        conclusione = asyncio.Event()

        async def worker_lento(tipo=None, limit=100):
            await conclusione.wait()
            return {"success": True, "analizzati": 12, "riconciliati": 3}

        monkeypatch.setattr(smart, "riconcilia_automatico", worker_lento)
        smart._riconciliazione_task = None
        smart._riconciliazione_stato.update({
            "status": "idle", "job_id": None, "started_at": None,
            "finished_at": None, "result": None, "error": None,
        })

        avvio = await smart.avvia_riconciliazione_automatica()
        assert avvio["status"] == "running"
        assert avvio["job_id"]

        secondo_avvio = await smart.avvia_riconciliazione_automatica()
        assert secondo_avvio["job_id"] == avvio["job_id"]

        conclusione.set()
        await smart._riconciliazione_task
        stato = await smart.stato_riconciliazione_automatica()
        assert stato["status"] == "completed"
        assert stato["result"]["riconciliati"] == 3

    asyncio.run(scenario())


def test_riconciliazione_background_espone_errore(monkeypatch):
    async def scenario():
        async def worker_in_errore(tipo=None, limit=100):
            raise RuntimeError("errore controllato")

        monkeypatch.setattr(smart, "riconcilia_automatico", worker_in_errore)
        smart._riconciliazione_task = None
        await smart.avvia_riconciliazione_automatica()
        await smart._riconciliazione_task

        stato = await smart.stato_riconciliazione_automatica()
        assert stato["status"] == "error"
        assert stato["error"] == "errore controllato"

    asyncio.run(scenario())
