"""Ricostruisce Prima Nota Cassa/Banca dai corrispettivi canonici."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.database import Database
from app.routers.invoices.corrispettivi_helpers import (
    rebuild_prima_nota_from_corrispettivi,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anno", type=int, required=True)
    return parser.parse_args()


async def _run(anno: int) -> int:
    await Database.connect_db()
    try:
        result = await rebuild_prima_nota_from_corrispettivi(
            Database.get_db(), anno=anno,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        await Database.close_db()


def main() -> None:
    args = _arguments()
    raise SystemExit(asyncio.run(_run(args.anno)))


if __name__ == "__main__":
    main()
