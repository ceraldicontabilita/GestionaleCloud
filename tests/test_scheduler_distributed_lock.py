"""Invarianti dello scheduler seriale nel processo Render."""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app import scheduler as scheduler_module
from app.database import Database
from app.scheduler import _esegui_con_lock_sheets


def _scenario_due_job_seriali(job_primo, job_secondo):
    async def scenario():
        primo = asyncio.create_task(
            _esegui_con_lock_sheets("job-primo", job_primo)
        )
        await job_primo.iniziato.wait()

        secondo = asyncio.create_task(
            _esegui_con_lock_sheets("job-secondo", job_secondo)
        )
        # Il secondo deve restare in coda, non partire e non terminare con None.
        await asyncio.sleep(0)
        assert not secondo.done()
        assert not job_secondo.iniziato.is_set()

        job_primo.termina.set()
        risultato_primo = await primo
        risultato_secondo = await secondo
        return risultato_primo, risultato_secondo

    return asyncio.run(scenario())


def _job_controllato(esecuzioni, nome):
    iniziato = asyncio.Event()
    termina = asyncio.Event()

    async def job():
        esecuzioni.append(nome)
        iniziato.set()
        if nome == "primo":
            await termina.wait()
        return "ok"

    job.iniziato = iniziato
    job.termina = termina
    return job


def test_due_job_non_si_sovrappongono_e_il_secondo_non_viene_perso(monkeypatch):
    db = MemorySheetsClient()["scheduler_lock_test"]
    monkeypatch.setattr(Database, "db", db)
    monkeypatch.setattr(scheduler_module, "_sheets_scheduler_lock", asyncio.Lock())
    esecuzioni = []
    primo = _job_controllato(esecuzioni, "primo")
    secondo = _job_controllato(esecuzioni, "secondo")

    risultato_primo, risultato_secondo = _scenario_due_job_seriali(primo, secondo)

    assert risultato_primo == "ok"
    assert risultato_secondo == "ok"
    assert esecuzioni == ["primo", "secondo"]


def test_sheets_usa_lock_locale_senza_collezione_tecnica(monkeypatch):
    monkeypatch.setattr(Database, "db", None)
    monkeypatch.setattr(scheduler_module, "_sheets_scheduler_lock", asyncio.Lock())
    esecuzioni = []
    primo = _job_controllato(esecuzioni, "primo")
    secondo = _job_controllato(esecuzioni, "secondo")

    risultato_primo, risultato_secondo = _scenario_due_job_seriali(primo, secondo)

    assert risultato_primo == "ok"
    assert risultato_secondo == "ok"
    assert esecuzioni == ["primo", "secondo"]
