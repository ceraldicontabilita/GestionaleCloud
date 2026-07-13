"""Migrazione non distruttiva P1 §5.3 — consolida i cedolini dall'alias legacy
inglese `payslips` nella canonica `cedolini`, deduplicando per chiave naturale
(contribuente + anno + mese).

`payslips` NON viene cancellata (archivio). Idempotente: rilanciarlo non crea
doppioni. NON tocca `buste_paga` (sottosistema Libro Unico/BPM/TFR, vivo) né
`cedolini_email_attachments` (file origine) né `riepilogo_cedolini` (aggregato).

Uso:
    python -m app.scripts.migra_payslips_a_cedolini          # dry-run
    python -m app.scripts.migra_payslips_a_cedolini --esegui # applica
"""
import asyncio
import sys

from app.database import Database
from app.services.cedolini_canonico import COLL, salva_cedolino, chiave_cedolino

LEGACY = "payslips"


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    presenti = set()
    async for d in db[COLL].find({}, {"_id": 0}):
        presenti.add(chiave_cedolino(d))

    docs = await db[LEGACY].find({}, {"_id": 0}).to_list(100000)
    migrati = 0
    gia_presenti = 0
    incompleti = 0
    for doc in docs:
        k = chiave_cedolino(doc)
        # chiave incompleta -> non affidabile
        if k.endswith("__") or k == "ced___":
            incompleti += 1
            continue
        if k in presenti:
            gia_presenti += 1
            continue
        presenti.add(k)
        if esegui:
            res = await salva_cedolino(db, doc, source="migrazione:payslips")
            if res is None:
                incompleti += 1
                continue
        migrati += 1
    return {"trovati": len(docs), "da_migrare": migrati,
            "gia_presenti": gia_presenti, "incompleti": incompleti,
            "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect()
    r = await migra(esegui)
    print(f"payslips -> {COLL}: {r['da_migrare']} da migrare, {r['gia_presenti']} già "
          f"presenti, {r['incompleti']} incompleti (su {r['trovati']}), "
          f"applicato={r['applicato']} (payslips NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
