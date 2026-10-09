import asyncio
import sys
from unittest.mock import AsyncMock, Mock, patch

from app.process_supervisor import build_child_specs
from app.scheduler_runner import settings


def test_web_and_scheduler_use_separate_process_roles():
    web, scheduler = build_child_specs({"PORT": "4321", "EXISTING": "yes"})

    assert web.command == (
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "4321",
    )
    assert web.environment["PROCESS_ROLE"] == "web"
    assert web.environment["ENABLE_SCHEDULER"] == "false"
    assert scheduler.command == (sys.executable, "-m", "app.scheduler_runner")
    assert scheduler.environment["PROCESS_ROLE"] == "scheduler"
    assert scheduler.environment["ENABLE_SCHEDULER"] == "true"
    assert web.environment["EXISTING"] == scheduler.environment["EXISTING"] == "yes"


def test_dedicated_scheduler_owns_and_closes_database():
    async def exercise():
        stop_event = asyncio.Event()
        stop_event.set()
        start = Mock()
        stop = Mock()

        with (
            patch(
                "app.scheduler_runner.Database.connect_db", new=AsyncMock()
            ) as connect,
            patch(
                "app.scheduler_runner.Database.close_db", new=AsyncMock()
            ) as close,
            patch.object(type(settings), "validate_startup"),
            patch("app.scheduler.start_scheduler", start),
            patch("app.scheduler.stop_scheduler", stop),
        ):
            from app.scheduler_runner import run_scheduler

            await run_scheduler(stop_event)

        connect.assert_awaited_once()
        start.assert_called_once()
        stop.assert_called_once()
        close.assert_awaited_once()

    asyncio.run(exercise())
