from __future__ import annotations

import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.accounting.piano_conti import (
    COLLECTION_REGOLE_CATEGORIZZAZIONE,
    inizializza_regole_base,
)


def test_regole_base_restituite_senza_identificatore_interno():
    async def scenario():
        db = MemorySheetsClient()["test_piano_conti"]
        regole = await inizializza_regole_base(db)
        persistite = await db[COLLECTION_REGOLE_CATEGORIZZAZIONE].find({}).to_list(100)
        return regole, persistite

    regole, persistite = asyncio.run(scenario())

    assert regole
    assert all("_id" not in regola for regola in regole)
    assert all("_id" in regola for regola in persistite)
