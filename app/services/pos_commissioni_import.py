"""Import dei riepiloghi commissioni POS Numia/Banco BPM.

Questi file non sono chiusure POS e non sono estratti conto: documentano,
per giorno, transato lordo, commissioni e netto atteso. Restano quindi una
fonte di supporto alla riconciliazione, senza creare incassi o movimenti banca.
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import openpyxl
from openpyxl.utils.datetime import from_excel


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    raw = _text(value).replace("€", "").replace(" ", "")
    if not raw:
        raise ValueError("importo vuoto")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return round(float(raw), 2)


def _date(value: Any, epoch) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return from_excel(value, epoch).date().isoformat()
    raw = _text(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"data commissioni POS non valida: {raw!r}")


def parse_pos_commissioni_file(content: bytes, filename: str) -> Dict[str, Any]:
    """Legge il blocco ``Sintesi giornaliera commissioni`` dell'XLSX."""
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("Le commissioni POS richiedono un file XLSX")
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = next(
        (ws for ws in workbook.worksheets if "sintesi giornaliera commissioni" in ws.title.lower()),
        None,
    )
    if sheet is None:
        raise ValueError("Foglio 'Sintesi giornaliera commissioni' non trovato")

    header_found = False
    days: List[Dict[str, Any]] = []
    invalid = 0
    for raw in sheet.iter_rows(values_only=True):
        values = list(raw)
        lowered = {_text(value).lower() for value in values if _text(value)}
        if not header_found:
            if {"data", "numero transazioni", "importo lordo", "importo netto", "importo commissioni"}.issubset(lowered):
                header_found = True
            continue
        if not values or values[0] in (None, ""):
            if days:
                break
            continue
        try:
            data_iso = _date(values[0], workbook.epoch)
            transazioni = int(float(values[1] or 0))
            lordo = _float(values[2])
            netto = _float(values[3])
            commissioni_originali = _float(values[4])
        except (TypeError, ValueError, IndexError):
            if days:
                break
            invalid += 1
            continue
        scarto = round(lordo + commissioni_originali - netto, 2)
        days.append({
            "data": data_iso,
            "numero_transazioni": transazioni,
            "importo_lordo": lordo,
            "importo_netto": netto,
            "commissioni": round(abs(commissioni_originali), 2),
            "importo_commissioni_originale": commissioni_originali,
            "quadratura": scarto,
            "quadrato": abs(scarto) <= 0.02,
            "source_filename": filename,
        })
    if not days:
        raise ValueError("Nessun riepilogo giornaliero commissioni riconosciuto")
    return {"days": days, "rows": len(days), "invalid": invalid}


async def importa_pos_commissioni_file(
    db, content: bytes, filename: str, *, drive_file_id: str | None = None,
) -> Dict[str, Any]:
    """Salva un solo riepilogo per data, scegliendo la fotografia più completa.

    Gli export mensili possono sovrapporsi ai confini mese. A parità di data
    non si sommano: prevale la riga con il maggior numero di transazioni.
    """
    parsed = parse_pos_commissioni_file(content, filename)
    now = datetime.now(timezone.utc).isoformat()
    file_hash = hashlib.sha256(content).hexdigest()
    inserted = updated = skipped = 0
    for item in parsed["days"]:
        existing = await db["pos_commissioni_giornaliere"].find_one(
            {"data": item["data"]}, {"_id": 0, "numero_transazioni": 1, "file_hash": 1}
        )
        if existing and int(existing.get("numero_transazioni") or 0) >= item["numero_transazioni"]:
            skipped += 1
            continue
        if existing:
            updated += 1
        else:
            inserted += 1
        await db["pos_commissioni_giornaliere"].update_one(
            {"data": item["data"]},
            {"$set": {
                **item,
                "file_hash": file_hash,
                "drive_file_id": drive_file_id,
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    await db["pos_commissioni_imports"].update_one(
        {"drive_file_id": drive_file_id or file_hash},
        {"$set": {
            "filename": filename,
            "file_hash": file_hash,
            "days": parsed["rows"],
            "invalid": parsed["invalid"],
            "updated_at": now,
        }},
        upsert=True,
    )
    return {
        "days": parsed["rows"],
        "inserted": inserted,
        "updated": updated,
        "duplicates": skipped,
    }
