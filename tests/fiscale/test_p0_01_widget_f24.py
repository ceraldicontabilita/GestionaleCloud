"""Il contatore legge i periodi e le prove, non i flag dei modelli."""

import asyncio
from mongomock_motor import AsyncMongoMockClient
from app.routers.scadenze import conta_f24_da_pagare
from tests.fiscale.test_piano_tributi import _f24, _quietanza


def test_conta_modello_una_volta_dalle_righe_senza_date_top_level():
    async def scenario():
        db = AsyncMongoMockClient()["widget"]
        await db.f24_unificato.insert_many(
            [
                _f24(
                    "a",
                    "2026-05-18",
                    erario=[("1001", 4, 2026, 10000, 0)],
                    inps=[("DM10", 4, 2026, 20000)],
                ),
                _f24("b", "2026-04-16", erario=[("1001", 3, 2026, 10000, 0)]),
                _f24("futuro", "2026-12-16", erario=[("1001", 11, 2026, 10000, 0)]),
            ]
        )
        await db.quietanze_f24.insert_one(_quietanza("q-marzo"))
        return await conta_f24_da_pagare(db, "2026-08-12")

    assert asyncio.run(scenario()) == 1
