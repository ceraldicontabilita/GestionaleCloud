"""Registro canonico dei pagamenti buoni importati da Documenti.

Il registro conserva la riga originale e usa il riferimento dell'operazione
come chiave di deduplicazione. L'assenza del riferimento non autorizza alcuna
associazione automatica: la riga resta ``da_verificare``.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from pymongo.errors import DuplicateKeyError


COLLECTION = "pagamenti_buoni"
GOOD_PAYMENT_COLUMNS = (
    "source_row", "source_bank", "accounting_date", "accounting_month",
    "accounting_year", "amount", "direction", "currency",
    "transfer_reference", "beneficiary_raw",
)


def _parse_date(value: str) -> date:
    value = value.strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError("data non valida")


def _parse_amount(value: str) -> Decimal:
    normalized = value.strip().replace("€", "").replace(" ", "")
    if not normalized:
        raise ValueError("importo vuoto")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("importo non valido") from exc
    if amount < 0:
        raise ValueError("importo negativo non ammesso")
    return amount


def parse_csv(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """Parsa il formato canonico UTF-8 CSV con separatore ``;``."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("il CSV deve essere codificato in UTF-8") from exc
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    if not rows:
        raise ValueError("CSV vuoto")
    header = [cell.strip() for cell in rows[0]]
    if header != list(GOOD_PAYMENT_COLUMNS):
        raise ValueError("intestazione non valida: attese le 10 colonne del registro Pagamenti buoni")

    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, values in enumerate(rows[1:], start=2):
        if not values or not any(value.strip() for value in values):
            continue
        if len(values) != len(GOOD_PAYMENT_COLUMNS):
            errors.append(f"riga {line_number}: numero colonne non valido")
            continue
        raw = dict(zip(GOOD_PAYMENT_COLUMNS, (value.strip() for value in values)))
        try:
            source_row = int(raw["source_row"])
            month = int(raw["accounting_month"])
            year = int(raw["accounting_year"])
            accounting_date = _parse_date(raw["accounting_date"])
            amount = _parse_amount(raw["amount"])
            if source_row < 1 or not 1 <= month <= 12 or not 2000 <= year <= 2100:
                raise ValueError("numero riga o periodo non valido")
            if not raw["source_bank"] or not raw["currency"] or not raw["direction"]:
                raise ValueError("campo obbligatorio vuoto")
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"riga {line_number}: {exc}")
            continue
        parsed.append({
            "source_row": source_row,
            "source_bank": raw["source_bank"],
            "accounting_date": accounting_date.isoformat(),
            "accounting_month": month,
            "accounting_year": year,
            "amount": format(amount, ".2f"),
            "direction": raw["direction"],
            "currency": raw["currency"],
            "transfer_reference": raw["transfer_reference"] or None,
            "beneficiary_raw": raw["beneficiary_raw"],
        })
    return parsed, errors


def is_canonical_csv(content: bytes) -> bool:
    """Riconosce l'intestazione senza classificare un CSV bancario generico."""
    try:
        first_line = content.decode("utf-8-sig", errors="strict").splitlines()[0]
    except (UnicodeDecodeError, IndexError):
        return False
    return [cell.strip() for cell in next(csv.reader([first_line], delimiter=";"), [])] == list(GOOD_PAYMENT_COLUMNS)


async def import_rows(db, rows: list[dict[str, Any]], source_name: str, errors: list[str] | None = None) -> dict[str, Any]:
    imported = 0
    duplicates = 0
    missing_reference = 0
    duplicate_references: list[str] = []
    for row in rows:
        document = {
            "id": str(uuid.uuid4()),
            **row,
            "verification_status": "verificato" if row.get("transfer_reference") else "da_verificare",
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_name": source_name,
        }
        try:
            await db[COLLECTION].insert_one(document)
            imported += 1
            if not row.get("transfer_reference"):
                missing_reference += 1
        except DuplicateKeyError:
            duplicates += 1
            if row.get("transfer_reference"):
                duplicate_references.append(row["transfer_reference"])
    return {
        "source_name": source_name,
        "columns": list(GOOD_PAYMENT_COLUMNS),
        "rows_read": len(rows),
        "imported": imported,
        "duplicates": duplicates,
        "invalid": len(errors or []),
        "missing_reference": missing_reference,
        "duplicate_references": sorted(set(duplicate_references)),
        "errors": list(errors or [])[:50],
    }


def serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    result = {key: record.get(key) for key in GOOD_PAYMENT_COLUMNS}
    result.update({
        "id": str(record.get("id") or record.get("_id")),
        "verification_status": record.get("verification_status", "da_verificare"),
        "source_name": record.get("source_name"),
    })
    return result
