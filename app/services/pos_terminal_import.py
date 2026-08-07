"""Import deterministico degli export del terminale POS Banco BPM.

Gli export CSV/XLSX contengono le singole transazioni. Il valore operativo
giornaliero e' la somma delle operazioni approvate, deduplicate per ID
transazione. Le righe negate o marcate ``Stornata`` restano nell'audit ma non
entrano nel totale; uno ``Storno approvato`` entra con il proprio segno.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List


_APPROVED_STATUSES = {"acquisto approvato", "storno approvato"}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _amount(value: Any) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    raw = _text(value).replace("€", "").replace(" ", "")
    if not raw:
        raise ValueError("importo vuoto")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return round(float(raw), 2)


def _date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = _text(value)
    for fmt in (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw[:19], fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"data POS non valida: {raw!r}")


def _normalizza_row(row: Dict[str, Any], filename: str) -> Dict[str, Any] | None:
    lowered = {_text(key).lower(): value for key, value in row.items() if key is not None}
    data_raw = lowered.get("data e ora") or lowered.get("data")
    importo_raw = lowered.get("importo")
    stato = _text(lowered.get("stato operazione")).lower()
    if not data_raw or importo_raw in (None, "") or not stato:
        return None

    data_iso = _date(data_raw)
    importo = _amount(importo_raw)
    transaction_id = _text(
        lowered.get("id transazione") or lowered.get("codice autorizzazione")
    )
    if transaction_id:
        key_material = f"bpm:{transaction_id}"
    else:
        key_material = "|".join((
            filename, _text(data_raw), f"{importo:.2f}", stato,
            _text(lowered.get("numero carta")),
            _text(lowered.get("tipo transazione")),
        ))

    return {
        "transaction_key": hashlib.sha256(key_material.encode("utf-8")).hexdigest(),
        "transaction_id": transaction_id or None,
        "data": data_iso,
        "importo": importo,
        "stato": stato,
        "tipo_transazione": _text(lowered.get("tipo transazione")).lower(),
        "source_filename": filename,
    }


def _csv_rows(content: bytes) -> Iterable[Dict[str, Any]]:
    decoded = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("CSV POS non decodificabile")
    first_line = decoded.splitlines()[0] if decoded.splitlines() else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    return csv.DictReader(io.StringIO(decoded), delimiter=delimiter)


def _xlsx_rows(content: bytes) -> Iterable[Dict[str, Any]]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    iterator = sheet.iter_rows(values_only=True)
    headers = None
    for raw in iterator:
        candidate = [_text(value) for value in raw]
        lowered = {value.lower() for value in candidate if value}
        if "data e ora" in lowered and "importo" in lowered and "stato operazione" in lowered:
            headers = candidate
            break
    if headers is None:
        return []
    return (
        {headers[index]: value for index, value in enumerate(raw) if index < len(headers) and headers[index]}
        for raw in iterator
    )


def parse_pos_terminal_file(content: bytes, filename: str) -> Dict[str, Any]:
    """Legge CSV/XLSX BPM senza scrivere sul database."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        rows = _csv_rows(content)
    elif lower.endswith((".xlsx", ".xlsm")):
        rows = _xlsx_rows(content)
    else:
        raise ValueError("Formato POS supportato: CSV o XLSX")

    transactions: List[Dict[str, Any]] = []
    invalid = 0
    for row in rows:
        try:
            normalized = _normalizza_row(row, filename)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if normalized:
            transactions.append(normalized)
        else:
            invalid += 1

    if not transactions:
        raise ValueError("Nessuna transazione POS riconosciuta")

    daily = defaultdict(float)
    for item in transactions:
        if item["stato"] in _APPROVED_STATUSES:
            daily[item["data"]] += item["importo"]
    return {
        "transactions": transactions,
        "daily_totals": {key: round(value, 2) for key, value in sorted(daily.items())},
        "rows": len(transactions),
        "approved": sum(1 for item in transactions if item["stato"] in _APPROVED_STATUSES),
        "invalid": invalid,
    }


async def importa_pos_terminal_file(db, content: bytes, filename: str, *, drive_file_id: str | None = None) -> Dict[str, Any]:
    """Salva le transazioni deduplicate e riallinea i totali giornalieri."""
    parsed = parse_pos_terminal_file(content, filename)
    now = datetime.now(timezone.utc).isoformat()
    affected_dates = set()
    inserted = 0
    updated = 0

    for item in parsed["transactions"]:
        previous = await db["pos_terminal_transactions"].find_one(
            {"transaction_key": item["transaction_key"]}, {"_id": 0, "stato": 1, "importo": 1, "data": 1}
        )
        if previous:
            affected_dates.add(previous.get("data"))
            updated += 1
        else:
            inserted += 1
        affected_dates.add(item["data"])
        await db["pos_terminal_transactions"].update_one(
            {"transaction_key": item["transaction_key"]},
            {"$set": {**item, "drive_file_id": drive_file_id, "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    from app.services.scritture_contabili import (
        GESTORE_POS_DEFAULT,
        registra_chiusura_pos_reale,
    )

    totals: Dict[str, float] = {}
    for data_iso in sorted(data for data in affected_dates if data):
        approved = await db["pos_terminal_transactions"].find(
            {"data": data_iso, "stato": {"$in": sorted(_APPROVED_STATUSES)}},
            {"_id": 0, "importo": 1},
        ).to_list(100000)
        total = round(sum(float(row.get("importo") or 0) for row in approved), 2)
        if total < 0:
            raise ValueError(f"Totale POS negativo per {data_iso}")
        await registra_chiusura_pos_reale(
            db, data_iso, total,
            # Questo flusso storico e' il terminale gia' esistente: resta il
            # gestore predefinito, cosi' non nasce un secondo terminale
            # fantasma accanto alle chiusure gia' registrate.
            gestore=GESTORE_POS_DEFAULT,
            note="Import automatico POS BPM da Drive: somma transazioni approvate",
            actor={"user_id": "drive_pos_bpm", "name": "Import automatico Drive"},
        )
        totals[data_iso] = total

    await db["pos_terminal_imports"].update_one(
        {"drive_file_id": drive_file_id or hashlib.sha256(content).hexdigest()},
        {"$set": {
            "filename": filename,
            "file_hash": hashlib.sha256(content).hexdigest(),
            "rows": parsed["rows"],
            "approved": parsed["approved"],
            "updated_at": now,
        }},
        upsert=True,
    )
    return {
        "rows": parsed["rows"], "approved": parsed["approved"],
        "inserted": inserted, "updated": updated,
        "days": len(totals), "daily_totals": totals,
    }
