import asyncio

from app.services import document_import_jobs
from app.services.sheets_document_store import MemorySheetsClient


def test_job_pos_persistente_e_idempotente_per_hash(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["document-import-job-test"]
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
        db = MemorySheetsClient()["document-import-job-error-test"]

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


def test_enqueue_risponde_prima_di_persistire_su_sheets(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["document-import-fast-ack-test"]
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
