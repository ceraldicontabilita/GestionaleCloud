import asyncio
import os

import pytest
from fastapi import HTTPException, Request
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from app.lotti.routers import vendita_banco as mod


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def richiesta(dipendente_id="hr-1"):
    request = Request({"type": "http", "method": "PUT", "path": "/api/vendita-banco/v-1/invenduto", "headers": [], "query_string": b""})
    if dipendente_id:
        request.state.user = {"sub": dipendente_id, "nome": "Operatore Serale", "ruolo": "operatore"}
    return request


def test_invenduto_e_correzione_registrano_id_dipendente(monkeypatch):
    database = AsyncMongoMockClient()["Banco_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.vendite_banco.insert_one({
            "id": "v-1", "prodotto_nome": "Arancino", "pezzi_prodotti": 5,
            "stato": "aperto", "operatore_nome": "Produttore Diurno",
        })
        await mod.registra_invenduto("v-1", mod.InvendutoIn(vendita_id="v-1", pezzi_invenduto=2), richiesta())
        registrato = await database.vendite_banco.find_one({"id": "v-1"})
        await mod.riapri_vendita("v-1", richiesta())
        riaperto = await database.vendite_banco.find_one({"id": "v-1"})
        return registrato, riaperto

    registrato, riaperto = run(scenario())
    assert registrato["pezzi_venduti"] == 3
    assert registrato["invenduto_dipendente_id"] == "hr-1"
    assert registrato["invenduto_operatore_nome"] == "Operatore Serale"
    assert riaperto["riaperto_da_dipendente_id"] == "hr-1"


@pytest.mark.parametrize("invenduto,status", [(-1, 400), (6, 400)])
def test_quantita_non_valida_non_modifica_vendita(monkeypatch, invenduto, status):
    database = AsyncMongoMockClient()["Banco_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.vendite_banco.insert_one({"id": "v-1", "prodotto_nome": "Arancino", "pezzi_prodotti": 5, "stato": "aperto"})
        with pytest.raises(HTTPException) as error:
            await mod.registra_invenduto("v-1", mod.InvendutoIn(vendita_id="v-1", pezzi_invenduto=invenduto), richiesta())
        return error.value.status_code, await database.vendite_banco.find_one({"id": "v-1"})

    code, vendita = run(scenario())
    assert code == status
    assert vendita["stato"] == "aperto"
    assert "invenduto_dipendente_id" not in vendita


def test_senza_sessione_dipendente_non_registra_invenduto(monkeypatch):
    database = AsyncMongoMockClient()["Banco_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.vendite_banco.insert_one({"id": "v-1", "prodotto_nome": "Arancino", "pezzi_prodotti": 5, "stato": "aperto"})
        with pytest.raises(HTTPException) as error:
            await mod.registra_invenduto("v-1", mod.InvendutoIn(vendita_id="v-1", pezzi_invenduto=2), richiesta(""))
        return error.value.status_code

    assert run(scenario()) == 401
