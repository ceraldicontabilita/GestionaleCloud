"""Documenti > Import: un file gia' caricato non si presenta come «Nuovo».

27/09/2026: il titolare ha ricaricato gli ZIP delle ricevute e l'anteprima
diceva «Nuovo» su tutti, anche su uno caricato la notte prima; nel riepilogo
le ricevute gia' in archivio finivano fra gli «importati».
"""
import asyncio
import hashlib
from io import BytesIO

from fastapi import UploadFile
from mongomock_motor import AsyncMongoMockClient

from app.routers import documenti as documenti_mod
from app.services import document_import_jobs
from app.services.document_import_preview import build_import_preview


def test_uno_zip_gia_caricato_lo_dice_l_anteprima():
    db = AsyncMongoMockClient()["t"]
    contenuto = b"PK-zip-finto"
    sha = hashlib.sha256(contenuto).hexdigest()

    async def scenario():
        prima = await build_import_preview(db, content=contenuto, filename="e.zip", document_type="archivio_zip")
        await db[document_import_jobs.COLLECTION].insert_one({
            "id": document_import_jobs.job_id_for_content(contenuto), "status": "completed",
            "filename": "e.zip", "completed_at": "2026-09-26T23:38:23+00:00", "content_sha256": sha,
        })
        dopo = await build_import_preview(db, content=contenuto, filename="e.zip", document_type="archivio_zip")
        return prima, dopo

    prima, dopo = asyncio.run(scenario())
    assert prima["duplicate"] is False
    assert dopo["duplicate"] is True
    assert dopo["duplicate_sources"][-1]["collection"] == "document_import_jobs"
    assert dopo["duplicate_sources"][-1]["completed_at"] == "2026-09-26T23:38:23+00:00"


def test_un_caricamento_fallito_non_vale_come_gia_caricato():
    db = AsyncMongoMockClient()["t"]
    contenuto = b"PK-zip-interrotto"

    async def scenario():
        await db[document_import_jobs.COLLECTION].insert_one({
            "id": document_import_jobs.job_id_for_content(contenuto), "status": "failed",
        })
        return await build_import_preview(db, content=contenuto, filename="e.zip", document_type="archivio_zip")

    assert asyncio.run(scenario())["duplicate"] is False


def test_una_ricevuta_gia_in_archivio_e_un_doppione_e_non_resta_in_inbox(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "bonifici")
    monkeypatch.setattr(documenti_mod.Database, "get_db", lambda: db)

    async def gia_presente(*_args, **_kwargs):
        return {"status": "duplicate", "transfer_id": "tr-1"}

    monkeypatch.setattr("app.services.bonifici_pdf_ingest.importa_pdf_bonifico", gia_presente)
    upload = UploadFile(filename="Bonifico - ricevuta per ordinante_21-01-2026_450,00.pdf",
                        file=BytesIO(b"%PDF-ricevuta"))

    async def scenario():
        esito = await documenti_mod.upload_documento_automatico(file=upload)
        return esito, await db["documents_inbox"].count_documents({})

    esito, in_inbox = asyncio.run(scenario())
    assert esito["duplicate"] is True
    assert esito["action"] == "duplicate"
    assert in_inbox == 0
