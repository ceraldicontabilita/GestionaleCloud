"""Migrazione non distruttiva P1 §5.1 — consolida i MODELLI F24 dalle collezioni
legacy nella canonica `f24_unificato`, deduplicando per chiave naturale.

Sorgenti legacy dei modelli F24 (NON i sottosistemi parser/tributi, che restano):
    f24_models, f24_commercialista, f24_uploaded, f24

Le collezioni legacy NON vengono cancellate (archivio). Idempotente: rilanciarlo
non crea doppioni (dedup per chiave naturale contribuente+periodo+saldo+hash+prot.).

Uso:
    python -m app.scripts.migra_f24_unificato          # dry-run (conta soltanto)
    python -m app.scripts.migra_f24_unificato --esegui # applica
"""
import asyncio
import sys

from app.database import Database
from app.services.f24_canonico import COLL, salva_f24, chiave_f24

SORGENTI_LEGACY = ["f24_models", "f24_commercialista", "f24_uploaded", "f24"]


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    report = {"per_sorgente": {}, "migrati": 0, "gia_presenti": 0, "applicato": bool(esegui)}
    # chiavi già presenti nella canonica (per il conteggio dry-run)
    presenti = set()
    async for d in db[COLL].find({}, {"_id": 0}):
        presenti.add(chiave_f24(d))

    for coll in SORGENTI_LEGACY:
        if coll == COLL:
            continue
        docs = await db[coll].find({}, {"_id": 0}).to_list(100000)
        n_mig = 0
        for doc in docs:
            k = chiave_f24(doc)
            if k in presenti:
                report["gia_presenti"] += 1
                continue
            presenti.add(k)
            if esegui:
                await salva_f24(db, doc, source=f"migrazione:{coll}")
            n_mig += 1
        report["per_sorgente"][coll] = {"trovati": len(docs), "da_migrare": n_mig}
        report["migrati"] += n_mig
    return report


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect()
    r = await migra(esegui)
    print(f"F24 -> {COLL}: {r['migrati']} da migrare, {r['gia_presenti']} già presenti, "
          f"applicato={r['applicato']}")
    for coll, s in r["per_sorgente"].items():
        print(f"  {coll}: trovati={s['trovati']} da_migrare={s['da_migrare']}")
    print("(collezioni legacy NON cancellate)")


if __name__ == "__main__":
    asyncio.run(_main())
