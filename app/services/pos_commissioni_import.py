"""Import dei riepiloghi commissioni POS Numia/Banco BPM.

Questi file non sono chiusure POS e non sono estratti conto: documentano,
per giorno, transato lordo, commissioni e netto atteso. Restano quindi una
fonte di supporto alla riconciliazione, senza creare incassi o movimenti banca.
"""
from __future__ import annotations

import hashlib
import io
import re
from contextlib import asynccontextmanager
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
    parsed: date | None = None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, (int, float)):
        converted = from_excel(value, epoch)
        if isinstance(converted, datetime):
            parsed = converted.date()
        elif isinstance(converted, date):
            parsed = converted
    else:
        raw = _text(value)
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw[:10], fmt).date()
                break
            except ValueError:
                continue
    # Gli export Numia rappresentano la riga TOTALE con lo zero seriale
    # Excel, che openpyxl converte in 1899-12-29. Non e' un'operazione e non
    # deve diventare un giorno contabile.
    if parsed is None or not 2000 <= parsed.year <= 2100:
        raise ValueError(f"data commissioni POS non valida: {_text(value)!r}")
    return parsed.isoformat()


def parse_pos_commissioni_file(content: bytes, filename: str) -> Dict[str, Any]:
    """Legge il blocco ``Sintesi giornaliera commissioni`` dell'XLSX."""
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("Le commissioni POS richiedono un file XLSX")
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    days: List[Dict[str, Any]] = []
    invalid = 0
    try:
        sheet = next(
            (ws for ws in workbook.worksheets if "sintesi giornaliera commissioni" in ws.title.lower()),
            None,
        )
        if sheet is None:
            raise ValueError("Foglio 'Sintesi giornaliera commissioni' non trovato")

        header_found = False
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
            operation_key = hashlib.sha256(
                f"pos:numia:commissioni:v1:{data_iso}".encode("utf-8")
            ).hexdigest()
            days.append({
                "id": f"POS-COMMISSIONI-{operation_key[:32]}",
                "operation_id": f"pos:numia:commissioni:{operation_key}",
                "operation_key": operation_key,
                "identity_version": "pos_numia_commissioni_v1",
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
    finally:
        workbook.close()
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
    dates = [item["data"] for item in parsed["days"]]
    existing_rows = await db["pos_commissioni_giornaliere"].find(
        {"data": {"$in": dates}},
        {"_id": 0, "data": 1, "numero_transazioni": 1},
    ).to_list(len(dates))
    existing_by_date = {str(row.get("data")): row for row in existing_rows}

    inserted = updated = skipped = 0

    @asynccontextmanager
    async def _write_batch():
        factory = getattr(db, "batch_writes", None)
        if callable(factory):
            async with factory():
                yield
        else:
            yield

    # Un file contiene circa cento righe di sintesi. Senza batch ogni riga
    # provocava una lettura/scrittura completa su Sheets e su Render superava
    # il limite di memoria. La cache viene aggiornata subito, mentre Sheets
    # riceve una sola mutazione aggregata per collezione.
    async with _write_batch():
        # Ripara l'unica riga fantasma prodotta dalla vecchia lettura del
        # totale Excel (seriale 0). Il filtro e' stretto e non tocca dati
        # contabili reali.
        await db["pos_commissioni_giornaliere"].delete_many({
            "data": "1899-12-29",
            "source_filename": {"$regex": r"^Commissioni_", "$options": "i"},
        })
        for item in parsed["days"]:
            existing = existing_by_date.get(item["data"])
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
                "id": f"POS-COMMISSIONI-IMPORT-{file_hash[:32]}",
                "operation_id": f"pos:numia:commissioni-import:{file_hash}",
                "filename": filename,
                "file_hash": file_hash,
                "identity_version": "pos_numia_commissioni_v1",
                "days": parsed["rows"],
                "invalid": parsed["invalid"],
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    return {
        "days": parsed["rows"],
        "inserted": inserted,
        "updated": updated,
        "duplicates": skipped,
    }
