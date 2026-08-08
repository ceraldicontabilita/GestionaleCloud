"""Invarianti dello scheduler in un deploy con piu' worker."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.database import Database
from app.scheduler import _esegui_con_lease_distribuito


def test_due_worker_non_eseguono_lo_stesso_job_in_parallelo(monkeypatch):
    db = AsyncMongoMockClient()["scheduler_lock_test"]
    monkeypatch.setattr(Database, "db", db)
    iniziato = asyncio.Event()
    termina = asyncio.Event()
    esecuzioni = []

    async def job():
        esecuzioni.append("run")
        iniziato.set()
        await termina.wait()
        return "ok"

    async def scenario():
        primo = asyncio.create_task(
            _esegui_con_lease_distribuito("job-contabile", job)
        )
        await iniziato.wait()
        secondo = await _esegui_con_lease_distribuito("job-contabile", job)
        termina.set()
        risultato_primo = await primo
        return risultato_primo, secondo

    primo, secondo = asyncio.run(scenario())
    assert primo == "ok"
    assert secondo is None
    assert esecuzioni == ["run"]
