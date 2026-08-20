"""Invarianti dello scheduler in un deploy con piu' worker."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.database import Database
from app.config import settings
from app.scheduler import _esegui_con_lease_distribuito, _sheets_job_locks


def test_due_worker_non_eseguono_lo_stesso_job_in_parallelo(monkeypatch):
    monkeypatch.setattr(settings, "DATA_BACKEND", "mongo")
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


def test_sheets_usa_lock_locale_senza_collezione_tecnica(monkeypatch):
    monkeypatch.setattr(settings, "DATA_BACKEND", "sheets")
    monkeypatch.setattr(Database, "db", None)
    _sheets_job_locks.clear()
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
            _esegui_con_lease_distribuito("job-sheets", job)
        )
        await iniziato.wait()
        secondo = await _esegui_con_lease_distribuito("job-sheets", job)
        termina.set()
        return await primo, secondo

    primo, secondo = asyncio.run(scenario())
    assert primo == "ok"
    assert secondo is None
    assert esecuzioni == ["run"]
    assert "job-sheets" in _sheets_job_locks
