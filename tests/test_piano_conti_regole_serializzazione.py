from __future__ import annotations

import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.accounting.piano_conti import (
    COLLECTION_REGOLE_CATEGORIZZAZIONE,
    inizializza_regole_base,
)


def test_regole_base_restituite_senza_object_id_mongo():
    async def scenario():
        db = AsyncMongoMockClient()["test_piano_conti"]
        regole = await inizializza_regole_base(db)
        persistite = await db[COLLECTION_REGOLE_CATEGORIZZAZIONE].find({}).to_list(100)
        return regole, persistite

    regole, persistite = asyncio.run(scenario())

    assert regole
    assert all("_id" not in regola for regola in regole)
    assert all("_id" in regola for regola in persistite)
