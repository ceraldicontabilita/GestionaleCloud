"""Registro versionato dei codici tributo da fonte ufficiale AdE."""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable

SOURCE_URL = "https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/elencoTributi.php"
CODE_RE = re.compile(r"^[A-Z0-9]{4}$", re.I)


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr": self.row = []
        elif tag.lower() in {"td", "th"} and self.row is not None: self.cell = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag.lower() in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag.lower() == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_tax_codes(payload: str) -> list[dict[str, str]]:
    parser = _TableParser()
    parser.feed(payload)
    out: dict[str, dict[str, str]] = {}
    for row in parser.rows:
        code_index = next((i for i, value in enumerate(row) if CODE_RE.fullmatch(value.strip())), None)
        if code_index is None:
            continue
        code = row[code_index].strip().upper()
        description = next((value.strip() for i, value in enumerate(row) if i != code_index and len(value.strip()) > 8), "")
        if description:
            out[code] = {"code": code, "description": html.unescape(description)}
    return sorted(out.values(), key=lambda item: item["code"])


def _fetch() -> str:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "GestionaleCloud/2 tax-registry"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


async def sync_tax_code_registry(db, fetcher: Callable[[], str] | None = None) -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat()
    payload = await asyncio.to_thread(fetcher or _fetch)
    codes = parse_tax_codes(payload)
    if len(codes) < 100:
        raise ValueError(f"Fonte AdE non valida o incompleta: solo {len(codes)} codici")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    version_id = digest[:16]
    existing = await db["tax_code_registry_versions"].find_one({"version_id": version_id})
    if not existing:
        await db["tax_code_registry_versions"].insert_one({
            "version_id": version_id, "source_url": SOURCE_URL, "sha256": digest,
            "record_count": len(codes), "fetched_at": fetched_at, "status": "verified",
        })
    for item in codes:
        await db["tax_code_registry"].update_one(
            {"code": item["code"]},
            {"$set": {**item, "version_id": version_id, "source_url": SOURCE_URL, "verified_at": fetched_at, "status": "verified"}},
            upsert=True,
        )
    await db["tax_code_registry_sync_runs"].insert_one({
        "version_id": version_id, "record_count": len(codes), "status": "ok", "created_at": fetched_at,
    })
    return {"status": "ok", "version_id": version_id, "record_count": len(codes)}


async def lookup_verified_tax_code(db, code: str) -> dict | None:
    normalized = (code or "").strip().upper()
    if not CODE_RE.fullmatch(normalized):
        return None
    return await db["tax_code_registry"].find_one(
        {"code": normalized, "status": "verified"}, {"_id": 0}
    )
