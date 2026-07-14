"""Migrazione non distruttiva P1 §5.5 — consolida le fatture emesse dall'alias
inglese legacy `invoices_emesse` nella canonica `fatture_emesse` (unico posto reale
da cui leggono bilancio/contabilità/IVA-debito/dashboard/public_api).

`invoices_emesse` NON viene cancellata (archivio). Idempotente: dedup per `id`;
in assenza di `id`, per (numero + data_fattura|date|data_documento). Non sovrascrive
una fattura già presente nella canonica.

Uso:
    python -m app.scripts.migra_invoices_emesse_a_fatture          # dry-run
    python -m app.scripts.migra_invoices_emesse_a_fatture --esegui # applica
"""
import asyncio
import sys

from app.database import Database

LEGACY = "invoices_emesse"
CANONICA = "fatture_emesse"


def _chiave(doc: dict) -> dict:
    if doc.get("id"):
        return {"id": doc["id"]}
    data = doc.get("data_fattura") or doc.get("date") or doc.get("data_documento")
    return {"numero": doc.get("numero"), "data_fattura": data}


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)
    if len(docs) >= 100000:
        print("migra_invoices_emesse_a_fatture: raggiunto il tetto di 100000 documenti, possibile troncamento")
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
    await Database.connect_db()
    r = await migra(esegui)
    print(f"invoices_emesse -> {CANONICA}: {r['da_migrare']} da migrare, "
          f"{r['gia_presenti']} già presenti, {r['incompleti']} incompleti "
          f"(su {r['trovati']}), applicato={r['applicato']} (legacy NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
