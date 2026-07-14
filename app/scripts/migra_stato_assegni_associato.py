"""Migrazione non distruttiva P0.5 — normalizza lo stato assegno invalido
"associato" (mai presente in ASSEGNO_STATI) verso il canonico "assegnato".

Uso:
    python -m app.scripts.migra_stato_assegni_associato          # dry-run
    python -m app.scripts.migra_stato_assegni_associato --esegui # applica

Idempotente: rilanciarlo non produce ulteriori modifiche.
"""
import asyncio
import sys

from app.database import Database

COLL = "assegni"
STATO_INVALIDO = "associato"
STATO_CANONICO = "assegnato"


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    da_correggere = await db[COLL].count_documents({"stato": STATO_INVALIDO})
    if esegui and da_correggere:
        await db[COLL].update_many(
            {"stato": STATO_INVALIDO},
            {"$set": {"stato": STATO_CANONICO}},
        )
    return {"trovati": da_correggere, "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect_db()
    res = await migra(esegui)
    print(f"assegni stato='{STATO_INVALIDO}' -> '{STATO_CANONICO}': "
          f"{res['trovati']} trovati, applicato={res['applicato']}")


if __name__ == "__main__":
    asyncio.run(_main())
