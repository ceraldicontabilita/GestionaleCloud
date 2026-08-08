"""Archivia e rimuove le sole scritture salari fuori dal periodo operativo.

Dry-run per default. Con ``--apply`` ogni documento viene prima copiato nella
collezione di archivio e soltanto dopo rimosso da ``prima_nota_salari``.
I cedolini/PDF sorgente non vengono mai toccati.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient, ReplaceOne

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.salari_periodo import filtro_fuori_periodo_prima_nota


def _config(env_file: str | None) -> tuple[str, str]:
    values = dotenv_values(env_file) if env_file else {}
    uri = (
        values.get("MONGO_URL")
        or values.get("MONGODB_URI")
        or values.get("MONGO_URI")
        or os.getenv("MONGO_URL")
        or os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
    )
    if not uri:
        raise RuntimeError("URI MongoDB mancante")
    db_name = (
        values.get("DB_NAME")
        or values.get("MONGO_DB_NAME")
        or values.get("MONGODB_DB")
        or os.getenv("DB_NAME")
        or "GestionaleCloud"
    )
    return str(uri), str(db_name)


def esegui(*, env_file: str | None, applica: bool) -> dict:
    uri, db_name = _config(env_file)
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    try:
        db = client[db_name]
        fonte = db["prima_nota_salari"]
        archivio = db["prima_nota_salari_archivio"]
        filtro = filtro_fuori_periodo_prima_nota()
        documenti = list(fonte.find(filtro))
        risultato = {
            "database": db_name,
            "candidati": len(documenti),
            "applicato": applica,
            "archiviati": 0,
            "eliminati": 0,
        }
        if not applica or not documenti:
            return risultato

        batch_id = f"salari-periodo-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        archived_at = datetime.now(timezone.utc).isoformat()
        operazioni = []
        original_ids = []
        for documento in documenti:
            originale_id = documento.pop("_id")
            original_ids.append(originale_id)
            copia = {
                **documento,
                "_id": f"{batch_id}:{originale_id}",
                "original_mongo_id": originale_id,
                "archive_batch_id": batch_id,
                "archived_at": archived_at,
                "archive_reason": "fuori_periodo_contabile_salario_dic2025_da_gen2026",
                "source_collection": "prima_nota_salari",
            }
            operazioni.append(ReplaceOne({"_id": copia["_id"]}, copia, upsert=True))

        esito_archivio = archivio.bulk_write(operazioni, ordered=False)
        archiviati = esito_archivio.upserted_count + esito_archivio.modified_count
        verificati = archivio.count_documents({"archive_batch_id": batch_id})
        if verificati != len(original_ids):
            raise RuntimeError(
                f"Archivio incompleto: attesi {len(original_ids)}, verificati {verificati}"
            )

        esito_delete = fonte.delete_many({"_id": {"$in": original_ids}})
        if esito_delete.deleted_count != len(original_ids):
            raise RuntimeError(
                f"Eliminazione incompleta: attesi {len(original_ids)}, eliminati {esito_delete.deleted_count}"
            )

        db["audit_log"].insert_one({
            "id": str(uuid.uuid4()),
            "evento": "prima_nota_salari_archivia_fuori_periodo",
            "archive_batch_id": batch_id,
            "periodo_mantenuto": "2025-12 e dal 2026 fino al mese corrente",
            "archiviati": verificati,
            "eliminati": esito_delete.deleted_count,
            "documenti_cedolino_eliminati": 0,
            "created_at": archived_at,
        })
        risultato.update({
            "archive_batch_id": batch_id,
            "archiviati": verificati,
            "eliminati": esito_delete.deleted_count,
        })
        return risultato
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(esegui(env_file=args.env_file, applica=args.apply))


if __name__ == "__main__":
    main()
