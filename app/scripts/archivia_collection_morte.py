"""
Script di archiviazione collection morte (anomalie confermate da audit codice).

Da un audit sistematico di tutte le collection MongoDB in uso dal gestionale
(luglio 2026), queste 3 collection non hanno più NESSUN punto di codice che
le legge o le scrive:

- estratto_conto (1873 doc)         -> duplicato/backup legacy di
                                        estratto_conto_movimenti (canonica)
- prima_nota_provvisori (126 doc)   -> nome legacy, probabile predecessore
                                        morto dell'attuale dati_provvisori
- movimenti_bancari (14834 doc)     -> tabella legacy pre-migrazione; l'unico
                                        punto di lettura rimasto (fallback in
                                        piano_conti.py) è stato reindirizzato
                                        su estratto_conto_movimenti nella
                                        stessa sessione che ha scritto questo
                                        script

Questo script NON cancella i dati: li RINOMINA con un prefisso `_archiviata_`
e un timestamp, cosà da poterli recuperare (o cancellare definitivamente in
un secondo momento, con calma) se qualcosa non tornasse. Nessun comando
distruttivo (drop/delete_many) viene mai eseguito qui.

Uso (richiede una .env con MONGO_URL valida e raggiungibile — questo script
NON è pensato per essere eseguibile dal sandbox di sviluppo, che non ha
accesso di rete al cluster Atlas):

    python -m app.scripts.archivia_collection_morte           # dry-run (default)
    python -m app.scripts.archivia_collection_morte --esegui   # esegue davvero
"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.database import Database

logger = logging.getLogger(__name__)

COLLECTION_DA_ARCHIVIARE = [
    "estratto_conto",
    "prima_nota_provvisori",
    "movimenti_bancari",
]


async def archivia_collection_morte(esegui: bool = False) -> Dict[str, Any]:
    """
    Rinomina le collection morte confermate con un prefisso `_archiviata_`.

    Args:
        esegui: se False (default), fa solo un dry-run e riporta cosa
                verrebbe fatto senza toccare nulla.
    """
    db = Database.get_db()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    risultati: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "modalita": "esecuzione" if esegui else "dry_run",
        "collection": [],
        "errori": [],
    }

    nomi_esistenti = set(await db.list_collection_names())

    for nome in COLLECTION_DA_ARCHIVIARE:
        if nome not in nomi_esistenti:
            risultati["collection"].append({
                "nome": nome, "stato": "non_trovata", "azione": None
            })
            continue

        conteggio = await db[nome].count_documents({})
        nuovo_nome = f"_archiviata_{nome}_{timestamp}"

        voce = {
            "nome": nome,
            "documenti": conteggio,
            "nuovo_nome": nuovo_nome,
            "stato": "dry_run",
        }

        if esegui:
            try:
                await db[nome].rename(nuovo_nome)
                voce["stato"] = "archiviata"
                logger.info(f"Archiviata '{nome}' ({conteggio} doc) -> '{nuovo_nome}'")
            except Exception as e:
                voce["stato"] = "errore"
                voce["errore"] = str(e)
                risultati["errori"].append(f"{nome}: {e}")
                logger.exception(f"Errore archiviando '{nome}'")

        risultati["collection"].append(voce)

    risultati["successo"] = len(risultati["errori"]) == 0
    return risultati


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--esegui", action="store_true",
        help="Esegue davvero la rinomina (default: dry-run, non tocca nulla)"
    )
    args = parser.parse_args()

    async def main():
        await Database.connect_db()

        if not args.esegui:
            print("=== DRY RUN — nessuna modifica verrà applicata ===")
            print("Rilancia con --esegui per rinominare davvero le collection.\n")

        risultati = await archivia_collection_morte(esegui=args.esegui)

        for voce in risultati["collection"]:
            if voce["stato"] == "non_trovata":
                print(f"  - {voce['nome']}: non trovata nel database, salto")
            elif voce["stato"] == "dry_run":
                print(f"  - {voce['nome']} ({voce['documenti']} doc) -> verrebbe rinominata in '{voce['nuovo_nome']}'")
            elif voce["stato"] == "archiviata":
                print(f"  ✓ {voce['nome']} ({voce['documenti']} doc) -> rinominata in '{voce['nuovo_nome']}'")
            elif voce["stato"] == "errore":
                print(f"  ✗ {voce['nome']}: ERRORE — {voce.get('errore')}")

        if risultati["errori"]:
            print(f"\n{len(risultati['errori'])} errori riscontrati.")
        else:
            print(f"\nCompletato ({risultati['modalita']}).")

    asyncio.run(main())
