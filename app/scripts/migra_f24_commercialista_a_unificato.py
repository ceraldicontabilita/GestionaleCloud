"""
Migrazione F24: f24_commercialista → f24_unificato (scelta utente 13/07/2026).

Gli F24 arrivati via email venivano salvati nella collezione separata
`f24_commercialista` e non comparivano nel modulo F24 principale (che legge
`f24_unificato`). Da ora il codice scrive direttamente in `f24_unificato`;
questo script sposta i documenti STORICI già presenti in `f24_commercialista`.

NON distruttivo: fa un UPSERT in `f24_unificato` per `pdf_hash` (o `id` se manca
l'hash) e NON cancella nulla da `f24_commercialista`. Se un documento è già in
`f24_unificato` (stesso hash) viene saltato. Dopo aver verificato l'esito puoi
decidere se archiviare `f24_commercialista` con `archivia_collection_*`.

Uso (richiede .env con MONGO_URL raggiungibile; NON eseguibile dal sandbox):
    python -m app.scripts.migra_f24_commercialista_a_unificato            # dry-run
    python -m app.scripts.migra_f24_commercialista_a_unificato --esegui   # esegue
"""
import argparse
import asyncio
import logging
from typing import Dict, Any

from app.database import Database

logger = logging.getLogger(__name__)

SORGENTE = "f24_commercialista"
DESTINAZIONE = "f24_unificato"


async def migra(esegui: bool = False) -> Dict[str, Any]:
    db = Database.get_db()
    nomi = set(await db.list_collection_names())
    ris: Dict[str, Any] = {
        "modalita": "esecuzione" if esegui else "dry_run",
        "sorgente": SORGENTE,
        "destinazione": DESTINAZIONE,
        "totale_sorgente": 0,
        "gia_presenti": 0,
        "da_migrare": 0,
        "migrati": 0,
        "errori": [],
    }
    if SORGENTE not in nomi:
        ris["nota"] = f"Collezione '{SORGENTE}' non presente: niente da migrare."
        return ris

    cursor = db[SORGENTE].find({})
    async for doc in cursor:
        ris["totale_sorgente"] += 1
        doc.pop("_id", None)
        chiave = {"pdf_hash": doc["pdf_hash"]} if doc.get("pdf_hash") else {"id": doc.get("id")}
        if not chiave or (list(chiave.values())[0] in (None, "")):
            ris["errori"].append(f"doc senza pdf_hash né id: {doc.get('filename')}")
            continue
        try:
            esistente = await db[DESTINAZIONE].find_one(chiave, {"_id": 1})
            if esistente:
                ris["gia_presenti"] += 1
                continue
            ris["da_migrare"] += 1
            if esegui:
                await db[DESTINAZIONE].insert_one(doc)
                ris["migrati"] += 1
        except Exception as e:  # pragma: no cover
            ris["errori"].append(f"{doc.get('filename')}: {e}")

    ris["successo"] = len(ris["errori"]) == 0
    return ris


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esegui", action="store_true",
                        help="Esegue davvero l'upsert (default: dry-run, non scrive)")
    args = parser.parse_args()

    async def main():
        await Database.connect_db()
        if not args.esegui:
            print("=== DRY RUN — nessuna scrittura ===")
            print("Rilancia con --esegui per migrare davvero.\n")
        r = await migra(esegui=args.esegui)
        print(f"Sorgente {r['sorgente']}: {r['totale_sorgente']} documenti")
        print(f"  già in {r['destinazione']}: {r['gia_presenti']}")
        print(f"  da migrare: {r['da_migrare']}")
        if args.esegui:
            print(f"  migrati: {r['migrati']}")
        if r["errori"]:
            print(f"  errori: {len(r['errori'])}")
            for e in r["errori"][:20]:
                print(f"    - {e}")
        else:
            print(f"\nCompletato ({r['modalita']}).")
        await Database.close_db()

    asyncio.run(main())
