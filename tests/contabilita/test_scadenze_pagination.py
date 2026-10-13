import asyncio
from datetime import date
from mongomock_motor import AsyncMongoMockClient
from app.routers import scadenze


def test_paginazione_filtri_e_totale_non_cambiano_al_cambio_pagina(monkeypatch):
    db = AsyncMongoMockClient()["pagination"]
    monkeypatch.setattr(scadenze.Database, "get_db", lambda: db)
    monkeypatch.setattr(scadenze, "oggi_roma", lambda: date(2026, 10, 13))

    async def scenario():
        await db.notifiche_scadenze.insert_many(
            [
                {
                    "id": "2025",
                    "data_scadenza": "2025-08-01",
                    "tipo": "IVA",
                    "importo": 700,
                },
                {
                    "id": "agosto-iva",
                    "data_scadenza": "2026-08-01",
                    "tipo": "IVA",
                    "importo": 100,
                },
                {
                    "id": "agosto-f24",
                    "data_scadenza": "2026-08-02",
                    "tipo": "F24",
                    "importo": 200,
                },
                {
                    "id": "settembre",
                    "data_scadenza": "2026-09-01",
                    "tipo": "IVA",
                    "importo": 300,
                },
            ]
        )
        first = await scadenze.get_tutte_scadenze(
            anno=2026, tipo="CUSTOM", limit=1, offset=0
        )
        second = await scadenze.get_tutte_scadenze(
            anno=2026, tipo="CUSTOM", limit=1, offset=1
        )
        august = await scadenze.get_tutte_scadenze(
            anno=2026, tipo="IVA", mese=8, limit=500
        )
        return first, second, august

    first, second, august = asyncio.run(scenario())
    assert first["totale"] == second["totale"] == 3
    assert first["statistiche"] == second["statistiche"]
    assert first["statistiche"]["totale_importo_cents"] == 60000
    assert [r["id"] for r in second["scadenze"]] == ["agosto-f24"]
    assert second["pagination"] == {"offset": 1, "limit": 1}
    assert [r["id"] for r in august["scadenze"] if r["source"] == "custom"] == [
        "agosto-iva"
    ]
