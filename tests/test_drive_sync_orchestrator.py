import asyncio

from app.services import drive_sync_orchestrator as orchestrator


class _ExistingService:
    def __init__(self, configured=True, started=True):
        self.configured = configured
        self.started = started
        self.calls = 0

    def is_configured(self):
        return self.configured

    def start_background_sync(self, _db):
        self.calls += 1
        return self.started


def test_start_all_avvia_solo_canali_configurati(monkeypatch):
    services = [_ExistingService(), _ExistingService(False), _ExistingService(), _ExistingService()]
    monkeypatch.setattr(orchestrator, "drive_invoice_ingest", services[0])
    monkeypatch.setattr(orchestrator, "drive_cedolini_ingest", services[1])
    monkeypatch.setattr(orchestrator, "drive_corrispettivi_ingest", services[2])
    monkeypatch.setattr(orchestrator, "drive_quietanze_ingest", services[3])

    estratti_done = asyncio.Event()
    documenti_done = asyncio.Event()

    class _Estratti:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        async def sync(_db):
            estratti_done.set()
            return {"status": "ok"}

    class _Documenti:
        CANALI = {"bonifico": {}}

        @staticmethod
        def is_enabled(_channel):
            return True

        @staticmethod
        def is_configured(_channel):
            return True

        @staticmethod
        async def sync_tutti(_db):
            documenti_done.set()
            return {"status": "ok"}

    monkeypatch.setattr(orchestrator, "drive_estratti_conto_ingest", _Estratti)
    monkeypatch.setattr(orchestrator, "drive_documenti_ingest", _Documenti)
    async def exercise():
        orchestrator._tasks.clear()
        result = orchestrator.start_all(object())
        await asyncio.wait_for(estratti_done.wait(), timeout=1)
        await asyncio.wait_for(documenti_done.wait(), timeout=1)
        return result

    result = asyncio.run(exercise())

    assert result == {
        "fatture": "started",
        "cedolini": "not_configured",
        "corrispettivi": "started",
        "quietanze": "started",
        "estratti_conto": "started",
        "documenti": "started",
    }
    assert services[1].calls == 0


def test_start_all_non_duplica_task_generiche_in_corso(monkeypatch):
    for name in (
        "drive_invoice_ingest",
        "drive_cedolini_ingest",
        "drive_corrispettivi_ingest",
        "drive_quietanze_ingest",
    ):
        monkeypatch.setattr(orchestrator, name, _ExistingService(False))

    release = asyncio.Event()

    class _Estratti:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        async def sync(_db):
            await release.wait()
            return {"status": "ok"}

    class _Documenti:
        CANALI = {}

    monkeypatch.setattr(orchestrator, "drive_estratti_conto_ingest", _Estratti)
    monkeypatch.setattr(orchestrator, "drive_documenti_ingest", _Documenti)
    async def exercise():
        orchestrator._tasks.clear()
        first = orchestrator.start_all(object())
        second = orchestrator.start_all(object())
        release.set()
        await orchestrator._tasks["estratti_conto"]
        return first, second

    first, second = asyncio.run(exercise())

    assert first["estratti_conto"] == "started"
    assert second["estratti_conto"] == "running"
    assert second["documenti"] == "not_configured"
