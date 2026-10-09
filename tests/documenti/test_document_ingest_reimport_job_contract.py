"""Confini della deduplicazione della coda, prima di un reset documentale.

Questi test eseguono il servizio job reale con archivio in memoria e un
elaboratore minimo. NON attestano l'idempotenza dell'import dei documenti,
dei relativi eventi, delle scritture contabili o del runtime Supabase.
"""
import asyncio
import importlib.util

from app.services import document_import_jobs as jobs
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.blob_store import MemoryBlobStore


def _isola_coda(monkeypatch, modulo):
    # Evita app.database e ogni accesso esterno: conserva il file solo in RAM.
    archivio = MemoryBlobStore()
    archivio.persistent = True
    monkeypatch.setattr(modulo, "_archivio_contenuti", lambda: archivio)
    monkeypatch.setattr(modulo, "_JOB_START_DELAY_SECONDS", 0)


def test_reupload_identico_nello_stesso_processo_esegue_un_solo_job(monkeypatch):
    _isola_coda(monkeypatch, jobs)

    async def scenario():
        db = ClientArchivioMemoria()["reimport-job-stesso-processo"]
        chiamate = []

        async def elabora(nome, contenuto):
            chiamate.append((nome, contenuto))
            await asyncio.sleep(0)
            return {"imported": 1}

        kwargs = {"content": b"archivio-test-concorrente", "document_type": "archivio_zip", "process": elabora}
        primo = await jobs.enqueue_import(db, filename="primo.zip", **kwargs)
        secondo = await jobs.enqueue_import(db, filename="copia.zip", **kwargs)
        await jobs.wait_for_import_job(primo["job_id"])
        completato = await jobs.enqueue_import(db, filename="terzo.zip", **kwargs)
        return primo, secondo, completato, chiamate

    primo, secondo, completato, chiamate = asyncio.run(scenario())
    assert primo["job_id"] == secondo["job_id"] == completato["job_id"]
    assert completato["queued"] is False
    assert completato["status"] == "completed"
    assert chiamate == [("primo.zip", b"archivio-test-concorrente")]


def test_reset_dei_soli_record_sorgente_non_sblocca_job_completed(monkeypatch):
    """Caratterizza il limite: un reset deve gestire anche il registro job.

    Il risultato cached resta completed anche se il suo record non esiste
    più. Non modificare il registro in questo test: il suo mantenimento è
    proprio il caso di reset incompleto che vogliamo rendere verificabile.
    """
    _isola_coda(monkeypatch, jobs)

    async def scenario():
        db = ClientArchivioMemoria()["reimport-job-reset-incompleto"]
        chiamate = []

        async def elabora(nome, contenuto):
            chiamate.append((nome, contenuto))
            await db["test_reimport_source"].insert_one({"id": "source-1"})
            return {"imported": 1, "source_id": "source-1"}

        kwargs = {"content": b"archivio-test-reset", "document_type": "archivio_zip", "process": elabora}
        primo = await jobs.enqueue_import(db, filename="originale.zip", **kwargs)
        await jobs.wait_for_import_job(primo["job_id"])
        assert await db["test_reimport_source"].count_documents({}) == 1
        await db["test_reimport_source"].delete_many({})
        secondo = await jobs.enqueue_import(db, filename="ricaricato.zip", **kwargs)
        return secondo, chiamate, await db["test_reimport_source"].count_documents({})

    secondo, chiamate, sorgenti = asyncio.run(scenario())
    assert secondo["queued"] is False
    assert secondo["status"] == "completed"
    assert secondo["result"]["source_id"] == "source-1"
    assert len(chiamate) == 1
    assert sorgenti == 0


def test_due_processi_non_condividono_il_blocco_locale_del_job(monkeypatch):
    """Due moduli indipendenti simulano le mappe/lock di due processi.

    Dimostra due chiamate all'elaboratore per lo stesso hash, NON due
    documenti: i deduplicatori downstream possono ancora impedirli.
    """
    spec = importlib.util.spec_from_file_location("coda_import_secondo_processo", jobs.__file__)
    seconda_coda = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seconda_coda)
    _isola_coda(monkeypatch, jobs)
    _isola_coda(monkeypatch, seconda_coda)

    async def scenario():
        db = ClientArchivioMemoria()["reimport-job-due-processi"]
        chiamate = []

        def elaboratore(processo):
            async def elabora(_nome, _contenuto):
                chiamate.append(processo)
                await asyncio.sleep(0)
                return {"imported": 1, "test_process": processo}
            return elabora

        kwargs = {"content": b"archivio-test-due-processi", "filename": "stesso.zip", "document_type": "archivio_zip"}
        # Prima che partano i task, nessuna delle due code ha persistito il job.
        primo = await jobs.enqueue_import(db, process=elaboratore("primo"), **kwargs)
        secondo = await seconda_coda.enqueue_import(db, process=elaboratore("secondo"), **kwargs)
        await asyncio.gather(jobs.wait_for_import_job(primo["job_id"]), seconda_coda.wait_for_import_job(secondo["job_id"]))
        return primo, secondo, chiamate, await db[jobs.COLLECTION].count_documents({})

    primo, secondo, chiamate, job_count = asyncio.run(scenario())
    assert primo["job_id"] == secondo["job_id"]
    assert chiamate == ["primo", "secondo"]
    assert job_count == 1
