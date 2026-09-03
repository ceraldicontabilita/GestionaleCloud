#!/usr/bin/env python3
"""Assegna il fornitore VANDEMOORTELE a tutti i prodotti acquaviva_prodotti che ne sono privi."""
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    result = await db.acquaviva_prodotti.update_many(
        {"fornitore": {"$exists": False}},
        {"$set": {"fornitore": "VANDEMOORTELE EUROPE NV, (SEDE SECONDARIA ITALIA)"}}
    )
    print(f"Prodotti aggiornati con fornitore: {result.modified_count}")
    # verifica
    total = await db.acquaviva_prodotti.count_documents({})
    with_forn = await db.acquaviva_prodotti.count_documents({"fornitore": {"$exists": True}})
    print(f"Totale prodotti: {total} — con fornitore: {with_forn}")
    client.close()

asyncio.run(main())
