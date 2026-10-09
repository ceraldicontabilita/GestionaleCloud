"""Contratto HTTP usato dal Backoffice: archivio solo in memoria, nessuna AI."""
import asyncio

import httpx
from fastapi import FastAPI

from app.lotti.routers import food_cost
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def test_get_elenco_senza_body_include_dosi_mancanti_ed_esclude_rivendita(monkeypatch):
    db = ClientArchivioMemoria()["ricette_http_isolate"]
    monkeypatch.setattr(food_cost, "db", db)
    app = FastAPI()
    app.include_router(food_cost.router)

    async def scenario():
        await db.ricette.insert_many([
            {"id": "r-vuota", "nome": "Ricetta vuota", "ingredienti": []},
            {"id": "r-qb", "nome": "Ricetta senza dosi", "ingredienti_dettaglio": [{"nome": "Sale", "quantita": "q.b."}]},
            {"id": "r-zero", "nome": "Ricetta a zero", "ingredienti_dettaglio": [{"nome": "Farina", "quantita": 0}]},
            {"id": "r-nomi", "nome": "Ricetta con soli nomi", "ingredienti": ["Farina"]},
            {"id": "r-completa", "nome": "Ricetta completa", "ingredienti_dettaglio": [{"nome": "Farina", "quantita": "0,5"}]},
            {"id": "r-rivendita", "nome": "Prodotto acquistato", "rivendita": True},
        ])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://fixture.invalid") as client:
            risposta = await client.get("/food-cost/ricette-senza-ingredienti")
        assert risposta.status_code == 200, risposta.text
        dati = risposta.json()
        assert dati["totale_ricette"] == 6
        assert dati["da_compilare"] == 4
        assert dati["senza_ingredienti"] == 1
        assert dati["senza_quantita"] == 3
        assert {r["id"]: r["motivo"] for r in dati["ricette"]} == {
            "r-vuota": "senza_ingredienti", "r-qb": "senza_quantita", "r-zero": "senza_quantita",
            "r-nomi": "senza_quantita",
        }
        assert "requestBody" not in app.openapi()["paths"]["/food-cost/ricette-senza-ingredienti"]["get"]

    asyncio.run(scenario())
