"""Migrazione non distruttiva P1 §5.2 — consolida i contratti dall'alias inglese
legacy `employee_contracts` nella canonica `contratti_dipendenti` (dove vive tutto
il CRUD contratti: create/read/update/delete/scadenze/report).

`employee_contracts` NON viene cancellata (archivio). Idempotente: dedup per `id`
del contratto; in assenza di `id`, per (dipendente_id + data_inizio + tipo_contratto).
Non sovrascrive un contratto già presente nella canonica.

Uso:
    python -m app.scripts.migra_employee_contracts_a_contratti          # dry-run
    python -m app.scripts.migra_employee_contracts_a_contratti --esegui # applica
"""
import asyncio
import sys

from app.database import Database

LEGACY = "employee_contracts"
CANONICA = "contratti_dipendenti"


def _chiave(doc: dict) -> dict:
    if doc.get("id"):
        return {"id": doc["id"]}
    return {
        "dipendente_id": doc.get("dipendente_id"),
        "data_inizio": doc.get("data_inizio"),
        "tipo_contratto": doc.get("tipo_contratto"),
    }


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)
    migrati = 0
    gia_presenti = 0
    incompleti = 0
    for doc in docs:
        chiave = _chiave(doc)
        if not any(v for v in chiave.values()):
            incompleti += 1
            continue
        if await db[CANONICA].find_one(chiave, {"_id": 1}):
            gia_presenti += 1
            continue
        if esegui:
            d = {k: v for k, v in doc.items() if k != "_id"}
            await db[CANONICA].insert_one(d)
        migrati += 1
    return {"trovati": len(docs), "da_migrare": migrati,
            "gia_presenti": gia_presenti, "incompleti": incompleti,
            "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect()
    r = await migra(esegui)
    print(f"employee_contracts -> {CANONICA}: {r['da_migrare']} da migrare, "
          f"{r['gia_presenti']} già presenti, {r['incompleti']} incompleti "
          f"(su {r['trovati']}), applicato={r['applicato']} (legacy NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
