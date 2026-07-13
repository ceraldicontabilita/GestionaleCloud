"""
Migrazione centri di costo → 4 settori reali (scelta utente).

La struttura dei centri operativi è cambiata:
  CDC-03  Laboratorio  → GELATERIA
  CDC-04  Asporto      → ROSTICCERIA
e la mappa categoria→centro è stata riallineata (es. gelato→CDC-03,
materie prime salate/asporto→CDC-04, materie prime dolci→CDC-02).

Questo script RI-DERIVA il `centro_costo` delle fatture dalla loro
`categoria_contabile` usando la nuova mappa `CATEGORIA_TO_CDC`, aggiornando solo
le fatture per cui il centro cambia. NON distruttivo: salva il valore precedente
in `centro_costo_migrato_da` e non cancella nulla. Idempotente.

Salvaguardie:
  - salta le fatture senza `categoria_contabile` (non rimappabili in automatico);
  - salta quelle con `centro_costo_manuale=True` (assegnazione manuale da preservare).

Uso (richiede .env con MONGO_URL raggiungibile; NON eseguibile dal sandbox):
    python -m app.scripts.migra_cdc_4_settori            # dry-run
    python -m app.scripts.migra_cdc_4_settori --esegui   # esegue
"""
import argparse
import asyncio
from collections import Counter

from app.database import Database, Collections
from app.routers.accounting.centri_costo import CATEGORIA_TO_CDC


async def migra(esegui: bool = False):
    db = Database.get_db()
    cursor = db[Collections.INVOICES].find(
        {"categoria_contabile": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 1, "id": 1, "categoria_contabile": 1, "centro_costo": 1,
         "centro_costo_manuale": 1},
    )
    transizioni = Counter()
    da_aggiornare = 0
    saltate_manuali = 0
    totale = 0
    async for f in cursor:
        totale += 1
        if f.get("centro_costo_manuale") is True:
            saltate_manuali += 1
            continue
        cat = (f.get("categoria_contabile") or "").strip().lower()
        nuovo = CATEGORIA_TO_CDC.get(cat)
        if not nuovo:
            continue
        attuale = f.get("centro_costo")
        if attuale == nuovo:
            continue
        transizioni[f"{attuale or '—'} → {nuovo}"] += 1
        da_aggiornare += 1
        if esegui:
            await db[Collections.INVOICES].update_one(
                {"_id": f["_id"]},
                {"$set": {"centro_costo": nuovo,
                          "centro_costo_migrato_da": attuale}},
            )
    return {
        "totale_con_categoria": totale,
        "saltate_manuali": saltate_manuali,
        "da_aggiornare": da_aggiornare,
        "transizioni": dict(transizioni),
        "modalita": "esecuzione" if esegui else "dry_run",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esegui", action="store_true",
                        help="Esegue davvero l'update (default: dry-run, non scrive)")
    args = parser.parse_args()

    async def main():
        await Database.connect_db()
        if not args.esegui:
            print("=== DRY RUN — nessuna scrittura ===")
            print("Rilancia con --esegui per migrare davvero.\n")
        r = await migra(esegui=args.esegui)
        print(f"Fatture con categoria: {r['totale_con_categoria']}")
        print(f"  saltate (manuali):   {r['saltate_manuali']}")
        print(f"  {'aggiornate' if args.esegui else 'da aggiornare'}: {r['da_aggiornare']}")
        if r["transizioni"]:
            print("  transizioni centro_costo:")
            for k, v in sorted(r["transizioni"].items(), key=lambda x: -x[1]):
                print(f"    {k}: {v}")
        print(f"\nCompletato ({r['modalita']}).")
        await Database.close_db()

    asyncio.run(main())
