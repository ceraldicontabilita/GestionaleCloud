"""Migrazione non distruttiva P1 §5.2 — porta l'anagrafica dall'alias legacy
`staff` alla canonica `dipendenti`, unendo per `codice_fiscale` (in assenza, per
`id`). Non sovrascrive campi già presenti con valori vuoti e NON tocca mai l'id
canonico di un dipendente esistente ($setOnInsert), perché cedolini/TFR/contratti/
prima_nota_salari collegano il dipendente per `id`.

`staff` NON viene cancellata (archivio). Idempotente.

Uso:
    python -m app.scripts.migra_staff_a_dipendenti          # dry-run
    python -m app.scripts.migra_staff_a_dipendenti --esegui # applica
"""
import asyncio
import sys

from app.database import Database

LEGACY = "staff"
CANONICA = "dipendenti"


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)
    migrati = 0
    incompleti = 0
    for doc in docs:
        cf = doc.get("codice_fiscale")
        chiave = {"codice_fiscale": cf} if cf else ({"id": doc.get("id")} if doc.get("id") else None)
        if not chiave:
            incompleti += 1
            continue
        patch = {k: v for k, v in doc.items()
                 if v not in (None, "", []) and k not in ("id", "_id")}
        on_insert = {"id": doc["id"]} if doc.get("id") else {}
        if esegui:
            await db[CANONICA].update_one(
                chiave, {"$set": patch, "$setOnInsert": on_insert}, upsert=True
            )
        migrati += 1
    return {"trovati": len(docs), "migrati": migrati,
            "incompleti": incompleti, "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect()
    r = await migra(esegui)
    print(f"staff -> {CANONICA}: {r['migrati']}/{r['trovati']} migrati, "
          f"{r['incompleti']} incompleti, applicato={r['applicato']} "
          f"(staff NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
