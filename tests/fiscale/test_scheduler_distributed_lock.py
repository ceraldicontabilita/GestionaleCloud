"""Invarianti dello scheduler seriale nel processo Render."""
import asyncio
from contextlib import asynccontextmanager

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app import scheduler as scheduler_module
from app.database import Database
from app.scheduler import _esegui_con_lease


def _scenario_due_job_seriali(job_primo, job_secondo):
    async def scenario():
        primo = asyncio.create_task(
            _esegui_con_lease("job-primo", job_primo)
        )
        await job_primo.iniziato.wait()

        secondo = asyncio.create_task(
            _esegui_con_lease("job-secondo", job_secondo)
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
    db = ClientArchivioMemoria()["scheduler_lock_test"]
    monkeypatch.setattr(Database, "db", db)
    monkeypatch.setattr(scheduler_module, "_lock_scheduler_locale", asyncio.Lock())
    esecuzioni = []
    primo = _job_controllato(esecuzioni, "primo")
    secondo = _job_controllato(esecuzioni, "secondo")

    risultato_primo, risultato_secondo = _scenario_due_job_seriali(primo, secondo)

    assert risultato_primo == "ok"
    assert risultato_secondo == "ok"
    assert esecuzioni == ["primo", "secondo"]


def test_senza_lease_remota_si_usa_il_lock_locale(monkeypatch):
    monkeypatch.setattr(Database, "db", None)
    monkeypatch.setattr(scheduler_module, "_lock_scheduler_locale", asyncio.Lock())
    esecuzioni = []
    primo = _job_controllato(esecuzioni, "primo")
    secondo = _job_controllato(esecuzioni, "secondo")

    risultato_primo, risultato_secondo = _scenario_due_job_seriali(primo, secondo)

    assert risultato_primo == "ok"
    assert risultato_secondo == "ok"
    assert esecuzioni == ["primo", "secondo"]


def test_supabase_salta_job_se_la_lease_e_detenuta_da_unaltra_istanza(monkeypatch):
    class DatabaseConLease:
        @asynccontextmanager
        async def scheduler_lease(self, job_id):
            assert job_id == "job-remoto"
            yield False

    monkeypatch.setattr(Database, "db", DatabaseConLease())
    eseguito = False

    async def job():
        nonlocal eseguito
        eseguito = True

    risultato = asyncio.run(_esegui_con_lease("job-remoto", job))

    assert risultato is None
    assert eseguito is False
