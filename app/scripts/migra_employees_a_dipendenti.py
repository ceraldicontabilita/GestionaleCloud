"""Migrazione non distruttiva P0.3 — porta i documenti anagrafica dalla collezione
legacy `employees` alla canonica `dipendenti`, unendo per `codice_fiscale`.

Non cancella `employees` (archivio). Idempotente: i campi già presenti in
`dipendenti` non vengono sovrascritti da valori vuoti.

Uso:
    python -m app.scripts.migra_employees_a_dipendenti          # dry-run
    python -m app.scripts.migra_employees_a_dipendenti --esegui # applica
"""
import asyncio
import sys

from app.database import Database

LEGACY = "employees"
CANONICA = "dipendenti"


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    legacy_docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)
    migrati = 0
    for doc in legacy_docs:
        cf = doc.get("codice_fiscale")
        chiave = {"codice_fiscale": cf} if cf else {"id": doc.get("id")}
        if not any(chiave.values()):
            continue
        # non sovrascrivere con vuoti
        patch = {k: v for k, v in doc.items() if v not in (None, "", [])}
        if esegui:
            await db[CANONICA].update_one(chiave, {"$set": patch}, upsert=True)
        migrati += 1
    return {"trovati": len(legacy_docs), "migrati": migrati, "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect()
    res = await migra(esegui)
    print(f"employees -> dipendenti: {res['migrati']}/{res['trovati']} "
          f"applicato={res['applicato']} (collezione legacy NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
