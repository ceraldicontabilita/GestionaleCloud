"""Migrazione non distruttiva P1 §5.4 — consolida le fatture passive dalla legacy
`fatture_passive` (alimentata dal ponte ERP) nella canonica `invoices`,
deduplicando per `invoice_key` (numero+P.IVA+data).

Le fatture legacy NON vengono cancellate (archivio). Idempotente: rilanciarlo non
crea doppioni. NON sovrascrive lo stato derivato di fatture già presenti in
`invoices` (pagamento, IVA, riconciliazioni): salta i duplicati.

Uso:
    python -m app.scripts.migra_fatture_passive_a_invoices          # dry-run
    python -m app.scripts.migra_fatture_passive_a_invoices --esegui # applica
"""
import asyncio
import sys

from app.database import Database
from app.services.fatture_canonico import salva_invoice_passiva, mappa_fattura_passiva

LEGACY = "fatture_passive"


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)
    if len(docs) >= 100000:
        print("migra_fatture_passive_a_invoices: raggiunto il tetto di 100000 documenti, possibile troncamento")
    migrati = 0
    saltati_incompleti = 0
    gia_presenti = 0
    for doc in docs:
        canonico = mappa_fattura_passiva(doc)
        if not canonico["invoice_number"] or not canonico["supplier_vat"]:
            saltati_incompleti += 1
            continue
        esistente = await db["invoices"].find_one(
            {"invoice_key": canonico["invoice_key"]}, {"_id": 1}
        )
        if esistente:
            gia_presenti += 1
            continue
        if esegui:
            await salva_invoice_passiva(db, doc, source="migrazione:fatture_passive")
        migrati += 1
    return {
        "trovati": len(docs),
        "da_migrare": migrati,
        "gia_presenti": gia_presenti,
        "saltati_incompleti": saltati_incompleti,
        "applicato": bool(esegui),
    }


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect_db()
    r = await migra(esegui)
    print(f"fatture_passive -> invoices: {r['da_migrare']} da migrare, "
          f"{r['gia_presenti']} già presenti, {r['saltati_incompleti']} incompleti "
          f"(su {r['trovati']}), applicato={r['applicato']} (legacy NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
