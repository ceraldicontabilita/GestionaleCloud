"""Un allegato email senza righe tributo non diventa un F24 «da pagare»."""
import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient

from app.services import post_download_pipeline as pipeline


def test_allegato_senza_righe_non_crea_il_modello(monkeypatch):
    db = AsyncMongoMockClient()["pipeline"]
    asyncio.run(db["f24_email_attachments"].insert_one({
        "id": "att-1", "filename": "Servizi Telematici - Sportello virtuale.pdf",
        "pdf_data": base64.b64encode(b"%PDF-finto").decode(), "pdf_hash": "h1",
    }))

    async def enhanced(*_a, **_k):
        return {"success": True, "sezione_erario": [], "sezione_inps": []}

    import app.services.enhanced_document_parser as edp
    monkeypatch.setattr(edp, "parse_f24_enhanced", enhanced)

    esito = asyncio.run(pipeline.processa_f24_da_email(db))
    assert esito["nuovi"] == 0
    assert asyncio.run(db["f24_unificato"].count_documents({})) == 0
    allegato = asyncio.run(db["f24_email_attachments"].find_one({"id": "att-1"}))
    assert allegato["processed"] is True and allegato["esito"] == "senza_righe_tributo"
