import asyncio

from app.services import document_import_jobs
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def test_job_pos_persistente_e_idempotente_per_hash(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["document-import-job-test"]
        calls = 0

        async def fake_import(_db, content, filename, *, drive_file_id=None):
            nonlocal calls
            calls += 1
            assert content == b"export-pos"
            assert filename == "Export_Transazioni_gennaio_2026.xlsx"
            assert drive_file_id is None
            return {
                "inserted": 2809, "updated": 0, "unchanged": 0,
                "days": 24, "operation_identity": "pos_numia_v2",
            }

        monkeypatch.setattr(
            document_import_jobs, "importa_pos_terminal_file", fake_import,
        )
        first = await document_import_jobs.enqueue_pos_import(
            db, content=b"export-pos",
            filename="Export_Transazioni_gennaio_2026.xlsx",
        )
        await document_import_jobs.wait_for_import_job(first["job_id"])
        completed = await document_import_jobs.get_import_job(db, first["job_id"])
        second = await document_import_jobs.enqueue_pos_import(
            db, content=b"export-pos",
            filename="stesso_periodo_nome_diverso.xlsx",
        )
        return first, completed, second, calls

    first, completed, second, calls = asyncio.run(scenario())

    assert first["queued"] is True
    assert completed["status"] == "completed"
    assert completed["result"]["inserted"] == 2809
    assert second["queued"] is False
    assert second["status"] == "completed"
    assert second["job_id"] == first["job_id"]
    assert calls == 1


def test_job_pos_registra_errore_senza_perdere_identita(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["document-import-job-error-test"]

        async def failed_import(*_args, **_kwargs):
            raise ValueError("foglio non leggibile")

        monkeypatch.setattr(
            document_import_jobs, "importa_pos_terminal_file", failed_import,
        )
        queued = await document_import_jobs.enqueue_pos_import(
            db, content=b"export-errato", filename="Export_Mensile.csv",
        )
        await document_import_jobs.wait_for_import_job(queued["job_id"])
        return await document_import_jobs.get_import_job(db, queued["job_id"])

    failed = asyncio.run(scenario())

    assert failed["status"] == "failed"
    assert failed["content_sha256"]
    assert failed["error"] == "foglio non leggibile"


def test_enqueue_risponde_prima_di_persistire_nell_archivio(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["document-import-fast-ack-test"]
        save_calls = []

        async def fake_save(_db, job_id, values):
            save_calls.append((job_id, values.get("status")))

        async def fake_import(*_args, **_kwargs):
            return {"inserted": 1, "unchanged": 0, "days": 1}

        monkeypatch.setattr(document_import_jobs, "_save_job", fake_save)
        monkeypatch.setattr(
            document_import_jobs, "importa_pos_terminal_file", fake_import,
        )

        queued = await document_import_jobs.enqueue_pos_import(
            db, content=b"export-fast-ack", filename="Export_Mensile.csv",
        )
        calls_before_response = list(save_calls)
        visible = await document_import_jobs.get_import_job(db, queued["job_id"])
        await document_import_jobs.wait_for_import_job(queued["job_id"])
        return queued, visible, calls_before_response, save_calls

    queued, visible, calls_before_response, save_calls = asyncio.run(scenario())

    assert queued["status"] == "queued"
    assert visible["status"] == "queued"
    assert calls_before_response == []
    assert [status for _, status in save_calls] == ["running", "completed"]


def test_zip_in_coda_salva_l_esito_e_non_si_rielabora(monkeypatch):
    """Uno ZIP da 400 fatture superava i 2 minuti del browser: il server si
    fermava con 3 fatture importate su 400. In coda l'esito resta salvato."""
    async def scenario():
        db = ClientArchivioMemoria()["document-import-zip-test"]
        chiamate = []

        async def process(filename, content):
            chiamate.append((filename, content))
            return {"success": True, "imported": 398, "duplicates": 2, "errors": 0}

        primo = await document_import_jobs.enqueue_zip_import(
            db, content=b"PK-zip", filename="20260923_ExportFattureRicevute.zip",
            process=process,
        )
        await document_import_jobs.wait_for_import_job(primo["job_id"])
        stato = await document_import_jobs.get_import_job(db, primo["job_id"])
        secondo = await document_import_jobs.enqueue_zip_import(
            db, content=b"PK-zip", filename="stesso.zip", process=process,
        )
        return primo, stato, secondo, chiamate

    primo, stato, secondo, chiamate = asyncio.run(scenario())

    assert primo["queued"] is True
    assert stato["status"] == "completed"
    assert stato["document_type"] == "archivio_zip"
    assert stato["result"]["imported"] == 398
    assert secondo["queued"] is False
    assert chiamate == [("20260923_ExportFattureRicevute.zip", b"PK-zip")]
