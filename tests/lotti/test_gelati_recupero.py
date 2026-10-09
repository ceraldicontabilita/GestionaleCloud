import asyncio
import os

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from app.lotti.routers import gelati as mod


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_cinque_chili_con_uno_e_mezzo_recuperati_creano_tre_e_mezzo_nuovi(monkeypatch):
    database = AsyncMongoMockClient()["Gelati_Test"]
    monkeypatch.setattr(mod, "db", database)
    lotti = []

    async def salva_lotto(doc, *, origine):
        lotti.append((doc, origine))
        return doc

    monkeypatch.setattr(mod, "crea_lotto", salva_lotto)

    async def scenario():
        await database.gelati_invenduti.insert_one({
            "id": "rientro-cioccolato", "gusto": "Cioccolato", "categoria": "cioccolato",
            "quantita_g": 2000, "riutilizzato_g": 0, "esito": "rientrato", "data": "2026-09-21",
        })
        result = await mod.aggiungi_produzione(mod.ProduzioneIn(
            ricetta="Cioccolato Giawa", peso_g=5000,
            recuperi=[mod.RecuperoRef(gusto="Cioccolato", quantita_g=1500)],
        ))
        rientro = await database.gelati_invenduti.find_one({"id": "rientro-cioccolato"})
        return result, rientro

    result, rientro = run(scenario())
    assert result["peso_nuovo_g"] == 3500
    assert result["peso_recuperato_g"] == 1500
    assert rientro["riutilizzato_g"] == 1500
    assert lotti[0][0]["quantita_g"] == 5000
    assert lotti[0][0]["lotti_fornitori"]["lotti_scalati"][0]["quantita_g"] == 1500


@pytest.mark.parametrize("disponibile,richiesto,codice", [(6000, 6000, 400), (1000, 1500, 409)])
def test_recupero_incoerente_non_consuma_giacenza(monkeypatch, disponibile, richiesto, codice):
    database = AsyncMongoMockClient()["Gelati_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.gelati_invenduti.insert_one({
            "id": "rientro", "gusto": "Cioccolato", "quantita_g": disponibile,
            "riutilizzato_g": 0, "esito": "rientrato", "data": "2026-09-21",
        })
        with pytest.raises(HTTPException) as exc:
            await mod.aggiungi_produzione(mod.ProduzioneIn(
                ricetta="Cioccolato Giawa", peso_g=5000,
                recuperi=[mod.RecuperoRef(gusto="Cioccolato", quantita_g=richiesto)],
            ))
        rientro = await database.gelati_invenduti.find_one({"id": "rientro"})
        return exc.value.status_code, rientro["riutilizzato_g"], await database.gelati_produzioni.count_documents({})

    status, usato, produzioni = run(scenario())
    assert status == codice
    assert usato == 0
    assert produzioni == 0
