"""Validate an F24 archive and optionally import its evidence ledger.

Dry-run is the default and never connects to MongoDB. Database writes require
the explicit ``--esegui`` switch after the complete archive has validated.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.config import settings
from app.database import Database
from app.services.f24_fiscal_evidence import (
    PARSER_KIND_PRINTABLE,
    PARSER_KIND_QUIETANZA,
    ingest_f24_evidence,
    normalize_f24_evidence_rows,
    parse_f24_evidence,
)


MANIFEST_NAME = "INDICE_UNICO_DOCUMENTI_F24.csv"


def _kind(row: dict[str, str]) -> str:
    label = (row.get("tipo_documento") or "").casefold()
    return PARSER_KIND_PRINTABLE if "stampabile" in label else PARSER_KIND_QUIETANZA


def _year(value: str) -> int | None:
    for token in reversed((value or "").replace("-", "/").split("/")):
        if len(token) == 4 and token.isdigit():
            return int(token)
    return None


def validate_archive(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifest non trovato: {manifest}")
    with manifest.open("r", encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.DictReader(stream, delimiter=";"))

    validated: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    by_year: Counter[int] = Counter()
    by_type: Counter[str] = Counter()
    totals = defaultdict(float)
    credit_rows = 0

    for source in source_rows:
        relative = Path(source.get("file") or "")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
            if not path.is_file():
                raise FileNotFoundError("PDF non trovato")
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            expected = (source.get("sha256") or "").strip().lower()
            if expected and digest != expected:
                raise ValueError("SHA-256 diverso dal manifest")
            kind = _kind(source)
            parsed = parse_f24_evidence(content, document_kind=kind)
            rows = normalize_f24_evidence_rows(parsed)
            if not rows:
                raise ValueError("nessuna riga fiscale estratta")
            year = _year(source.get("data_versamento") or "")
            by_year[year or 0] += len(rows)
            by_type[kind] += 1
            totals["debits"] += sum(item["debit_amount"] for item in rows)
            totals["credits"] += sum(item["credit_amount"] for item in rows)
            credit_rows += sum(1 for item in rows if item["credit_amount"] > 0)
            validated.append({
                "path": path,
                "relative_path": relative.as_posix(),
                "content": content,
                "sha256": digest,
                "document_kind": kind,
                "manifest": source,
                "parsed": parsed,
                "rows": rows,
            })
        except Exception as exc:
            errors.append({"file": relative.as_posix(), "error": str(exc)})

    summary = {
        "mode": "dry-run",
        "manifest_rows": len(source_rows),
        "valid_documents": len(validated),
        "invalid_documents": len(errors),
        "normalized_rows": sum(by_year.values()),
        "credit_rows": credit_rows,
        "total_debits": round(totals["debits"], 2),
        "total_credits": round(totals["credits"], 2),
        "rows_by_payment_year": {str(key): value for key, value in sorted(by_year.items())},
        "documents_by_type": dict(sorted(by_type.items())),
        "errors": errors,
    }
    return validated, summary


async def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.archive).resolve()
    validated, summary = validate_archive(root)
    if summary["invalid_documents"]:
        summary["write_status"] = "BLOCKED_ARCHIVE_VALIDATION"
        return summary
    if not args.esegui:
        summary["write_status"] = "NOT_REQUESTED"
        return summary

    await Database.connect_db()
    imported = duplicates = failed = 0
    failures: list[dict[str, str]] = []
    try:
        db = Database.get_db()
        for item in validated:
            try:
                result = await ingest_f24_evidence(
                    db,
                    content=item["content"],
                    filename=item["path"].name,
                    document_kind=item["document_kind"],
                    company_id=args.company_id,
                    source="archive_f24_manifest",
                    source_metadata={
                        **item["manifest"],
                        "archive_relative_path": item["relative_path"],
                    },
                    expected_sha256=item["sha256"],
                )
                duplicates += int(result["duplicate_document"])
                imported += int(not result["duplicate_document"])
            except Exception as exc:
                failed += 1
                failures.append({"file": item["relative_path"], "error": str(exc)})
    finally:
        await Database.close_db()
    summary.update({
        "mode": "write",
        "write_status": "COMPLETED" if not failed else "COMPLETED_WITH_ERRORS",
        "imported_documents": imported,
        "duplicate_documents": duplicates,
        "failed_documents": failed,
        "write_errors": failures,
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help=f"Cartella che contiene {MANIFEST_NAME}")
    parser.add_argument("--company-id", default=settings.FISCAL_COMPANY_ID)
    parser.add_argument("--esegui", action="store_true", help="Abilita esplicitamente le scritture nel database")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
