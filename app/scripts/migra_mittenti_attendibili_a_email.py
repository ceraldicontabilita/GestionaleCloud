"""
Migrazione mittenti: mittenti_attendibili → mittenti_email (P2-2).

Esistevano due collezioni per lo stesso concetto (mittenti fidati per canale/tipo
documento). `mittenti_email` è la fonte unica canonica; questo script copia i
documenti STORICI di `mittenti_attendibili` nella canonica.

NON distruttivo: fa un insert in `mittenti_email` solo per i mittenti non ancora
presenti (per pattern+canale) e NON cancella nulla da `mittenti_attendibili`.
Idempotente: rieseguirlo non crea doppioni.

Uso (richiede .env con MONGO_URL raggiungibile; NON eseguibile dal sandbox):
    python -m app.scripts.migra_mittenti_attendibili_a_email            # dry-run
    python -m app.scripts.migra_mittenti_attendibili_a_email --esegui   # esegue
"""
import argparse
import asyncio

from app.database import Database
from app.services.mittenti import migra_mittenti_legacy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esegui", action="store_true",
                        help="Esegue davvero l'inserimento (default: dry-run, non scrive)")
    args = parser.parse_args()

    async def main():
        await Database.connect_db()
        if not args.esegui:
            print("=== DRY RUN — nessuna scrittura ===")
            print("Rilancia con --esegui per migrare davvero.\n")
        db = Database.get_db()
        r = await migra_mittenti_legacy(db, dry_run=not args.esegui)
        print(f"Legacy mittenti_attendibili: {r['totale_legacy']} documenti")
        print(f"  già in mittenti_email: {r['gia_presenti']}")
        print(f"  senza indirizzo (saltati): {r['senza_indirizzo']}")
        print(f"  {'migrati' if args.esegui else 'da migrare'}: {r['migrati']}")
        print(f"\nCompletato ({'esecuzione' if args.esegui else 'dry_run'}).")
        await Database.close_db()

    asyncio.run(main())
