"""
DEPRECATO: provisioning e manipolazioni MongoDB

Questo script era usato per provisioning e migrazione su MongoDB. MongoDB è
stato rimosso come backend supportato. Questo script è mantenuto solo a fini
storici e non deve essere eseguito in produzione. Se serve eseguire una
migrazione storica, usare una copia fuori repo e una procedura controllata.
"""

import sys

if __name__ == "__main__":
    print("ERROR: script deprecato — MongoDB non è più supportato. Non eseguire.")
    sys.exit(1)

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
