"""Anteprima/applicazione della bonifica POS NUMIA sul database configurato.

Uso sicuro (nessuna modifica):
    python scripts/bonifica_pos_numia.py --env-file C:\\percorso\\GestionaleCloud.env

Applicazione (soft-archive con audit, nessuna cancellazione fisica):
    python scripts/bonifica_pos_numia.py --env-file ... --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


def _argomenti() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anno", type=int, default=2026)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


async def _main() -> int:
    args = _argomenti()
    if args.env_file:
        load_dotenv(args.env_file, override=True)

    # Il repository e' la radice d'import anche quando lo script viene
    # avviato dalla cartella scripts.
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)

    from app.services.scritture_contabili import bonifica_accrediti_pos_numia

    uri = os.getenv("MONGODB_ATLAS_URI") or os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME") or "Gestionale"
    if not uri:
        raise RuntimeError("MONGODB_ATLAS_URI/MONGO_URL non configurato")

    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=15000)
    try:
        await client.admin.command("ping")
        esito = await bonifica_accrediti_pos_numia(
            client[db_name], args.anno,
            dry_run=not args.apply,
            actor={"sub": "script-bonifica-pos-numia"},
        )
        esito.pop("dettaglio", None)
        print(json.dumps(esito, ensure_ascii=False, indent=2, default=str))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
