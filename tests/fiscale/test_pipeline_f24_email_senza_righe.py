"""Posta: modelli e quietanze passano dagli ingressi canonici, mai da un lettore proprio."""
import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient

from app.services import f24_canonico
from app.services import post_download_pipeline as pipeline


def _allegato(db, coll, id_, nome):
    asyncio.run(db[coll].insert_one({
        "id": id_, "filename": nome,
        "pdf_data": base64.b64encode(b"%PDF-finto").decode(), "pdf_hash": "h-" + id_,
    }))


def test_allegato_senza_righe_non_crea_il_modello(monkeypatch):
    db = AsyncMongoMockClient()["pipeline"]
    _allegato(db, "f24_email_attachments", "att-1", "Servizi Telematici - Sportello virtuale.pdf")
    monkeypatch.setattr(
        "app.services.parser_f24.parse_f24_commercialista",
        lambda pdf_content: {"sezione_erario": [], "sezione_inps": [], "totali": {}},
    )
    monkeypatch.setattr(f24_canonico, "richiedi_quadratura_f24", lambda parsed: {})

    esito = asyncio.run(pipeline.processa_f24_da_email(db))
    assert esito["nuovi"] == 0 and esito["errori"] == 1
    assert asyncio.run(db["f24_unificato"].count_documents({})) == 0
    allegato = asyncio.run(db["f24_email_attachments"].find_one({"id": "att-1"}))
    assert allegato["processed"] is True and allegato["esito"] == "SENZA_RIGHE_TRIBUTO"


def test_modello_email_delega_all_ingresso_unico(monkeypatch):
    db = AsyncMongoMockClient()["pipeline"]
    _allegato(db, "f24_email_attachments", "att-2", "F24.pdf")
    chiamate = []

    async def finto(_db, content, filename, *, source, source_metadata=None):
        chiamate.append((content, filename, source, source_metadata))
        return {"success": True, "duplicate": len(chiamate) > 1, "f24_id": "f-1"}

    monkeypatch.setattr(f24_canonico, "importa_modello_bytes", finto)
    esito = asyncio.run(pipeline.processa_f24_da_email(db))
    assert esito["nuovi"] == 1 and esito["errori"] == 0
    assert chiamate[0][0] == b"%PDF-finto" and chiamate[0][2] == "gmail_scan"
    assert chiamate[0][3]["attachment_id"] == "att-2"
    allegato = asyncio.run(db["f24_email_attachments"].find_one({"id": "att-2"}))
    assert allegato["esito"] == "importato" and allegato["f24_id"] == "f-1"


def test_quietanza_email_delega_e_non_scrive_da_sola(monkeypatch):
    db = AsyncMongoMockClient()["pipeline"]
    _allegato(db, "quietanze_email_attachments", "att-3", "quietanza.pdf")
    _allegato(db, "quietanze_email_attachments", "att-4", "ricevuta.pdf")

    async def finta(_db, content, filename, *, source, source_metadata=None):
        if filename == "ricevuta.pdf":
            return {"success": False, "error": "Nessuna riga tributo letta",
                    "stato_quietanza": "NON_QUIETANZA_F24"}
        return {"success": True, "quietanza_id": "q-1", "f24_matchati": ["a", "b"]}

    monkeypatch.setattr(f24_canonico, "importa_quietanza", finta)
    esito = asyncio.run(pipeline.processa_quietanze_da_email(db))
    assert esito["processati"] == 2 and esito["errori"] == 1 and esito["f24_pagati"] == 2
    assert asyncio.run(db["f24_quietanze"].count_documents({})) == 0
    ok = asyncio.run(db["quietanze_email_attachments"].find_one({"id": "att-3"}))
    ko = asyncio.run(db["quietanze_email_attachments"].find_one({"id": "att-4"}))
    assert ok["esito"] == "importata" and ko["esito"] == "NON_QUIETANZA_F24"
