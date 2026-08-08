"""Provisioning MongoDB esplicito e ripetibile.

Da eseguire come fase amministrativa/deploy, mai dentro ogni worker web.
Non cancella dati. Le incompatibilita' degli indici vengono riportate nel log.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.database import Database


async def provision(*, seed: bool) -> None:
    settings.RUN_STARTUP_INDEX_MIGRATIONS = False
    settings.RUN_STARTUP_SEED_DATA = False
    await Database.connect_db()
    try:
        await Database._create_indexes(strict=True)
        if seed:
            await Database._ensure_builtin_senders()
    finally:
        await Database.close_db()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Inserisce anche i mittenti istituzionali mancanti",
    )
    args = parser.parse_args()
    asyncio.run(provision(seed=args.seed))


if __name__ == "__main__":
    main()
