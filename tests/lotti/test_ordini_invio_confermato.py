import asyncio
import os

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from app.lotti.routers import ordini_fornitori as mod
from app.lotti.routers import email_ordini
from app.lotti import eventi


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_conferma_non_segna_inviato_e_invio_registra_canale_e_destinatario(monkeypatch):
    database = AsyncMongoMockClient()["Ordini_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def admin(_request):
        return None

    async def pubblica(_tipo, _payload):
        return None

    monkeypatch.setattr(mod, "require_admin", admin)
    monkeypatch.setattr(mod, "request_actor", lambda _request: {"id": "hr-admin"})
    monkeypatch.setattr(eventi, "publish", pubblica)

    async def scenario():
        await database.ordini_fornitori.insert_one({
            "id": "ord-1", "stato": "bozza", "fornitore": "Fornitore Uno",
            "prodotti": [
                {"prodotto_id": "p-1", "nome": "Farina", "fornitore": "Fornitore Uno", "quantita": 2},
                {"prodotto_id": "p-2", "nome": "Zucchero", "fornitore": "Fornitore Uno", "quantita": 1},
            ],
        })
        await mod.conferma_righe("ord-1", {"prodotto_ids": ["p-1"]}, request=object())
        dopo_conferma = await database.ordini_fornitori.find_one({"id": "ord-1"})
        inviato = await mod.invia_ordine_confermato("ord-1", mod.InvioConfermato(
            canale="email", destinatario="fornitore@example.com"), request=object())
        dopo_invio = await database.ordini_fornitori.find_one({"id": "ord-1"})
        residui = await database.ordini_fornitori.find({"stato": "bozza"}).to_list(10)
        secondo = await mod.invia_ordine_confermato("ord-1", mod.InvioConfermato(
            canale="email", destinatario="fornitore@example.com"), request=object())
        return dopo_conferma, inviato, dopo_invio, residui, secondo

    conferma, risposta, ordine, residui, secondo = run(scenario())
    assert conferma["stato"] == "confermato"
    assert risposta["righe_inviate"] == 1
    assert ordine["stato"] == "inviato_fornitori"
    assert ordine["invio_canale"] == "email"
    assert ordine["invio_destinatario"] == "fornitore@example.com"
    assert ordine["inviato_da_dipendente_id"] == "hr-admin"
    assert len(residui) == 1 and residui[0]["prodotti"][0]["prodotto_id"] == "p-2"
    assert secondo["gia_inviato"] is True


def test_ordine_non_confermato_non_risulta_inviato(monkeypatch):
    database = AsyncMongoMockClient()["Ordini_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def admin(_request):
        return None

    monkeypatch.setattr(mod, "require_admin", admin)
    monkeypatch.setattr(mod, "request_actor", lambda _request: {"id": "hr-admin"})

    async def scenario():
        await database.ordini_fornitori.insert_one({
            "id": "ord-1", "stato": "bozza", "prodotti": [
                {"prodotto_id": "p-1", "nome": "Farina", "fornitore": "Fornitore Uno", "confermato": True},
            ],
        })
        with pytest.raises(HTTPException) as error:
            await mod.invia_ordine_confermato("ord-1", mod.InvioConfermato(
                canale="whatsapp", destinatario="393331234567"), request=object())
        return error.value.status_code, await database.ordini_fornitori.find_one({"id": "ord-1"})

    status, ordine = run(scenario())
    assert status == 409
    assert ordine["stato"] == "bozza"


def test_pdf_preparato_contiene_solo_le_righe_confermate(monkeypatch):
    database = AsyncMongoMockClient()["Ordini_Test"]
    monkeypatch.setattr(email_ordini, "db", database)
    righe_pdf = []

    def crea_pdf(_ordine, _fornitore, prodotti, azienda=None):
        righe_pdf.extend(prodotti)
        return b"pdf-di-test"

    async def azienda():
        return {}

    monkeypatch.setattr(email_ordini, "genera_pdf_ordine_fornitore", crea_pdf)
    monkeypatch.setattr(email_ordini, "get_azienda", azienda)

    async def scenario():
        await database.ordini_fornitori.insert_one({
            "id": "ord-1", "stato": "confermato", "prodotti": [
                {"prodotto_id": "p-1", "nome": "Farina", "fornitore": "Fornitore Uno", "confermato": True},
                {"prodotto_id": "p-2", "nome": "Zucchero", "fornitore": "Fornitore Uno", "confermato": False},
            ],
        })
        return await email_ordini.scarica_pdf_ordine("ord-1", "Fornitore Uno")

    response = run(scenario())
    assert response.media_type == "application/pdf"
    assert [r["prodotto_id"] for r in righe_pdf] == ["p-1"]
