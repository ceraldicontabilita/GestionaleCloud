"""Ricostruisce l'archivio fatture dal Drive canonico fuori dal web worker."""

from __future__ import annotations

import asyncio
import json

from app.database import Database
from app.services.drive_invoice_ingest import ricostruisci_archivio_drive


_SUMMARY_FIELDS = (
    "status",
    "total",
    "processed",
    "imported",
    "duplicates",
    "archiviate",
    "errors",
    "folders",
)


async def _run() -> int:
    await Database.connect_db()
    try:
        result = await ricostruisci_archivio_drive(Database.get_db())
        summary = {key: result.get(key) for key in _SUMMARY_FIELDS if key in result}
        if result.get("message"):
            summary["message"] = str(result["message"])[:300]
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") == "ok" else 1
    finally:
        await Database.close_db()


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
