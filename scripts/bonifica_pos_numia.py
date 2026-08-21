"""Anteprima/applicazione della bonifica POS NUMIA sul registro Sheets.

Uso sicuro (nessuna modifica):
    python scripts/bonifica_pos_numia.py

Applicazione (soft-archive con audit, nessuna cancellazione fisica):
    python scripts/bonifica_pos_numia.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def _argomenti() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anno", type=int, default=2026)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


async def _main() -> int:
    args = _argomenti()
    # Il repository e' la radice d'import anche quando lo script viene
    # avviato dalla cartella scripts.
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)

    from app.database import Database
    from app.services.scritture_contabili import bonifica_accrediti_pos_numia

    await Database.connect_db()
    try:
        esito = await bonifica_accrediti_pos_numia(
            Database.get_db(), args.anno,
            dry_run=not args.apply,
            actor={"sub": "script-bonifica-pos-numia"},
        )
        esito.pop("dettaglio", None)
        print(json.dumps(esito, ensure_ascii=False, indent=2, default=str))
    finally:
        await Database.close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
