"""
DEPRECATO: verifica ripristino MongoDB

Questo script era usato per verificare ripristini MongoDB in modalità sola-
lettura. MongoDB è stato rimosso come backend supportato; questo script è
mantenuto solo a fini storici. Non eseguire nello stesso ambiente di produzione.
"""

import sys

if __name__ == "__main__":
    print("ERROR: script deprecato — MongoDB non è più supportato. Non eseguire.")
    sys.exit(1)

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo import MongoClient


DEFAULT_SAMPLE_SIZE = 25


def _canonical_json(value: Any) -> str:
    return json_util.dumps(
        value,
        json_options=json_util.CANONICAL_JSON_OPTIONS,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized_indexes(collection) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name, spec in sorted(collection.index_information().items()):
        normalized[name] = {
            "key": list(spec.get("key", [])),
            **{
                option: spec[option]
                for option in (
                    "unique",
                    "sparse",
                    "expireAfterSeconds",
                    "partialFilterExpression",
                    "collation",
                )
                if option in spec
            },
        }
    return normalized


def _sample_hash(collection, sample_size: int) -> str:
    digest = hashlib.sha256()
    cursor = collection.find({}).sort([("_id", 1)]).limit(sample_size)
    for document in cursor:
        digest.update(_canonical_json(document).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_manifest(database, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict[str, Any]:
    """Costruisce un manifest senza includere il contenuto dei documenti."""
    collections: dict[str, Any] = {}
    for name in sorted(database.list_collection_names()):
        if name.startswith("system."):
            continue
        collection = database[name]
        collections[name] = {
            "document_count": collection.count_documents({}),
            "sample_size": sample_size,
            "sample_sha256": _sample_hash(collection, sample_size),
            "indexes": _normalized_indexes(collection),
        }
    return {
        "manifest_version": 1,
        "sample_size": sample_size,
        "collections": collections,
    }


def compare_manifests(source: dict[str, Any], restored: dict[str, Any]) -> dict[str, Any]:
    source_collections = source.get("collections", {})
    restored_collections = restored.get("collections", {})
    source_names = set(source_collections)
    restored_names = set(restored_collections)

    mismatches: dict[str, list[str]] = {}
    for name in sorted(source_names & restored_names):
        fields = [
            field
            for field in ("document_count", "sample_sha256", "indexes")
            if source_collections[name].get(field) != restored_collections[name].get(field)
        ]
        if fields:
            mismatches[name] = fields

    missing = sorted(source_names - restored_names)
    unexpected = sorted(restored_names - source_names)
    return {
        "ok": not missing and not unexpected and not mismatches,
        "source_collection_count": len(source_names),
        "restored_collection_count": len(restored_names),
        "missing_collections": missing,
        "unexpected_collections": unexpected,
        "mismatches": mismatches,
    }


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Variabile obbligatoria assente: {name}")
    return value


def _validate_distinct_targets(
    source_uri: str,
    restored_uri: str,
    source_db_name: str,
    restored_db_name: str,
) -> None:
    if hmac.compare_digest(source_uri, restored_uri) and source_db_name == restored_db_name:
        raise ValueError("Sorgente e ripristino coincidono: verifica annullata")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument(
        "--output",
        type=Path,
        help="File JSON opzionale per il solo rapporto (mai URI o documenti)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.sample_size < 1 or args.sample_size > 1000:
        print("ERRORE: --sample-size deve essere compreso tra 1 e 1000", file=sys.stderr)
        return 2

    source_client = None
    restored_client = None
    try:
        source_uri = _required_env("DR_SOURCE_MONGO_URL")
        restored_uri = _required_env("DR_RESTORE_MONGO_URL")
        source_db_name = os.getenv("DR_SOURCE_DB_NAME", "Gestionale").strip() or "Gestionale"
        restored_db_name = _required_env("DR_RESTORE_DB_NAME")
        _validate_distinct_targets(
            source_uri, restored_uri, source_db_name, restored_db_name
        )

        source_client = MongoClient(
            source_uri,
            appname="GestionaleCloud-DR-source-readonly",
            serverSelectionTimeoutMS=15000,
        )
        restored_client = MongoClient(
            restored_uri,
            appname="GestionaleCloud-DR-restore-readonly",
            serverSelectionTimeoutMS=15000,
        )
        source_client.admin.command("ping")
        restored_client.admin.command("ping")

        # Seconda barriera: anche con URI/utenti diversi, non confrontare lo
        # stesso database sullo stesso insieme di nodi.
        if (
            source_db_name == restored_db_name
            and source_client.nodes
            and source_client.nodes == restored_client.nodes
        ):
            raise ValueError("Sorgente e ripristino puntano allo stesso database")

        source_manifest = build_manifest(source_client[source_db_name], args.sample_size)
        restored_manifest = build_manifest(restored_client[restored_db_name], args.sample_size)
        report = compare_manifests(source_manifest, restored_manifest)

        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["ok"] else 1
    except Exception as exc:
        # Non stampare il messaggio dell'eccezione: alcuni driver includono
        # dettagli della connection string negli errori di configurazione.
        print(
            f"ERRORE: verifica non completata ({type(exc).__name__}). "
            "Controllare configurazione e accessi senza incollare credenziali.",
            file=sys.stderr,
        )
        return 2
    finally:
        if source_client is not None:
            source_client.close()
        if restored_client is not None:
            restored_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
