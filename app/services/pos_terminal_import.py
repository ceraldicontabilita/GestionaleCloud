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
from contextlib import asynccontextmanager
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


def _timestamp(value: Any) -> str:
    """Timestamp canonico dell'operazione, indipendente dal formato export.

    CSV e XLSX Numia possono rappresentare la stessa ora rispettivamente
    come ``31/05/2026 20:33:50.000`` e come oggetto ``datetime``. La chiave
    non deve quindi dipendere dalla serializzazione scelta dal file.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = _text(value)
        parsed = None
        for fmt in (
            "%d/%m/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M", "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"data POS non valida: {raw!r}")
    timespec = "milliseconds" if parsed.microsecond else "seconds"
    return parsed.isoformat(timespec=timespec)


def _identity_text(value: Any) -> str:
    return _text(value).upper()


def _operation_key(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _normalizza_row(row: Dict[str, Any], filename: str) -> Dict[str, Any] | None:
    lowered = {_text(key).lower(): value for key, value in row.items() if key is not None}
    data_raw = lowered.get("data e ora") or lowered.get("data")
    importo_raw = lowered.get("importo")
    stato = _text(lowered.get("stato operazione")).lower()
    if not data_raw or importo_raw in (None, "") or not stato:
        return None

    timestamp = _timestamp(data_raw)
    data_iso = timestamp[:10]
    importo = _amount(importo_raw)
    # Identita' del punto di incasso. Serve alla chiave logica
    # provider + terminale + giornata e all'aggancio dell'accredito, che la
    # banca distingue per punto vendita e terminale. Senza questi campi due
    # terminali dello stesso negozio sarebbero indistinguibili: nell'export
    # reale di maggio 2026 ce ne sono due, con MID diversi.
    terminale = _text(lowered.get("id terminale / tml") or lowered.get("id terminale"))
    mid = _text(lowered.get("mid"))
    # Negli export reali lo stesso negozio compare come "CERALDI CAFFE" e
    # "CERALDI CAFFE'": l'apostrofo finale e' incostante. Usato come chiave
    # spaccherebbe in due i raggruppamenti per punto vendita.
    punto_vendita = _text(lowered.get("punto vendita")).rstrip("'\u2019 ").upper()
    id_punto_vendita = _text(lowered.get("id punto vendita"))
    # "Circuito" nell'export e' il circuito della CARTA (Mastercard,
    # PagoBancomat...), non il gestore: sono tutti incassi Numia e vanno
    # sommati nella stessa giornata, non trattati come provider diversi.
    circuito_carta = _text(lowered.get("circuito"))
    transaction_id = _text(lowered.get("id transazione"))
    authorization_code = _text(lowered.get("codice autorizzazione"))
    numero_carta = _text(lowered.get("numero carta"))
    tipo_transazione = _text(lowered.get("tipo transazione")).lower()
    valuta = _identity_text(lowered.get("valuta originale") or "EUR")

    # L'ID del gestore e' la prova forte. Quando manca, la chiave usa tutti
    # gli attributi operativi stabili ma MAI nome/hash del file: due export
    # con periodi sovrapposti devono indicare la stessa operazione.
    if transaction_id:
        key_material = f"pos:numia:v2:id:{_identity_text(transaction_id)}"
        # Conserviamo la vecchia chiave per riconoscere senza migrazioni le
        # righe gia archiviate dalle versioni precedenti.
        legacy_transaction_key = _operation_key(f"bpm:{transaction_id}")
        identity_strength = "provider_transaction_id"
    else:
        key_material = "|".join((
            "pos:numia:v2:composite", timestamp, f"{round(importo * 100):d}",
            valuta, _identity_text(authorization_code),
            _identity_text(numero_carta), _identity_text(tipo_transazione),
            _identity_text(terminale), _identity_text(mid),
            _identity_text(id_punto_vendita), _identity_text(punto_vendita),
        ))
        legacy_transaction_key = None
        identity_strength = "canonical_composite"

    operation_key = _operation_key(key_material)

    return {
        "id": f"POS-NUMIA-{operation_key[:32]}",
        "operation_id": f"pos:numia:{operation_key}",
        "operation_key": operation_key,
        "transaction_key": operation_key,
        "legacy_transaction_key": legacy_transaction_key,
        "identity_version": "pos_numia_v2",
        "identity_strength": identity_strength,
        "transaction_id": transaction_id or None,
        "authorization_code": authorization_code or None,
        "transaction_timestamp": timestamp,
        "data": data_iso,
        "importo": importo,
        "stato": stato,
        "tipo_transazione": tipo_transazione,
        "numero_carta": numero_carta or None,
        "valuta": valuta,
        "provider": "numia",
        "terminale": terminale or None,
        "mid": mid or None,
        "punto_vendita": punto_vendita or None,
        "id_punto_vendita": id_punto_vendita or None,
        "circuito_carta": circuito_carta.upper() or None,
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
    by_key: Dict[str, Dict[str, Any]] = {}
    source_rows = 0
    duplicates = 0
    invalid = 0
    fallback_occurrences: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        source_rows += 1
        try:
            normalized = _normalizza_row(row, filename)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if not normalized:
            invalid += 1
            continue

        # Senza ID gestore, due righe perfettamente uguali possono essere due
        # addebiti reali distinti. L'indice di occorrenza preserva la
        # molteplicita' ed e' stabile al reimport dello stesso sottoinsieme.
        if not normalized.get("transaction_id"):
            base_key = normalized["operation_key"]
            fallback_occurrences[base_key] += 1
            occurrence = fallback_occurrences[base_key]
            operation_key = _operation_key(f"{base_key}|occurrence:{occurrence}")
            normalized.update({
                "id": f"POS-NUMIA-{operation_key[:32]}",
                "operation_id": f"pos:numia:{operation_key}",
                "operation_key": operation_key,
                "transaction_key": operation_key,
                "occurrence_index": occurrence,
            })

        key = normalized["transaction_key"]
        previous = by_key.get(key)
        if previous is not None:
            # Lo stesso ID transazione non puo' descrivere due fatti diversi.
            # Un duplicato identico viene contato per audit ma escluso dai
            # totali; un duplicato contraddittorio blocca l'importazione.
            comparable = (
                "transaction_id", "transaction_timestamp", "data", "importo", "stato",
                "tipo_transazione", "provider", "terminale", "mid",
                "punto_vendita", "id_punto_vendita", "circuito_carta",
            )
            conflicts = [
                field for field in comparable
                if previous.get(field) != normalized.get(field)
            ]
            if conflicts:
                tx_id = normalized.get("transaction_id") or key[:12]
                raise ValueError(
                    "ID transazione POS contraddittorio "
                    f"{tx_id}: campi diversi {', '.join(conflicts)}"
                )
            duplicates += 1
            continue

        by_key[key] = normalized
        transactions.append(normalized)

    if not transactions:
        raise ValueError("Nessuna transazione POS riconosciuta")

    daily = defaultdict(float)
    per_terminale = defaultdict(float)
    for item in transactions:
        if item["stato"] in _APPROVED_STATUSES:
            daily[item["data"]] += item["importo"]
            # Chiave logica della specifica: provider + terminale + giornata.
            per_terminale[(item["data"], item.get("terminale") or "?")] += item["importo"]
    return {
        "transactions": transactions,
        "terminali": sorted({t["terminale"] for t in transactions if t.get("terminale")}),
        "per_terminale": {f"{g}|{t}": round(v, 2)
                          for (g, t), v in sorted(per_terminale.items())},
        "daily_totals": {key: round(value, 2) for key, value in sorted(daily.items())},
        "rows": len(transactions),
        "source_rows": source_rows,
        "duplicates": duplicates,
        "approved": sum(1 for item in transactions if item["stato"] in _APPROVED_STATUSES),
        "invalid": invalid,
    }


async def importa_pos_terminal_file(db, content: bytes, filename: str, *, drive_file_id: str | None = None) -> Dict[str, Any]:
    """Salva le transazioni deduplicate e riallinea i totali giornalieri."""
    parsed = parse_pos_terminal_file(content, filename)
    now = datetime.now(timezone.utc).isoformat()
    file_hash = hashlib.sha256(content).hexdigest()
    affected_dates = set()
    inserted = 0
    updated = 0
    unchanged = 0

    # Una sola lettura della cache Sheets, poi un solo inserimento bulk. La
    # vecchia implementazione faceva find+update remoto per ogni riga (oltre
    # 6.500 chiamate per un mese), causando i 502 visibili in produzione.
    existing_rows = await db["pos_terminal_transactions"].find(
        {}, {"_id": 0}
    ).to_list(250000)
    existing_by_key: Dict[str, Dict[str, Any]] = {}
    for row in existing_rows:
        for key in (
            row.get("operation_key"), row.get("transaction_key"),
            row.get("legacy_transaction_key"),
        ):
            if key:
                existing_by_key[str(key)] = row

    records_to_insert: List[Dict[str, Any]] = []
    records_to_update: List[tuple[str, Dict[str, Any]]] = []
    immutable_fields = (
        "transaction_id", "transaction_timestamp", "data", "importo",
        "tipo_transazione", "provider", "terminale", "mid",
        "id_punto_vendita",
    )
    mutable_fields = (
        "stato", "punto_vendita", "circuito_carta", "authorization_code",
        "numero_carta", "valuta",
    )
    for item in parsed["transactions"]:
        candidate_keys = [
            item.get("operation_key"), item.get("transaction_key"),
            item.get("legacy_transaction_key"),
        ]
        previous = next(
            (existing_by_key[str(key)] for key in candidate_keys
             if key and str(key) in existing_by_key),
            None,
        )
        affected_dates.add(item["data"])
        if previous is None:
            record = {
                **item,
                "source_filename": filename,
                "source_file_hash": file_hash,
                "drive_file_id": drive_file_id,
                "created_at": now,
                "updated_at": now,
            }
            records_to_insert.append(record)
            inserted += 1
            for key in candidate_keys:
                if key:
                    existing_by_key[str(key)] = record
            continue

        affected_dates.add(previous.get("data"))
        conflicts = [
            field for field in immutable_fields
            if previous.get(field) not in (None, "")
            and item.get(field) not in (None, "")
            and previous.get(field) != item.get(field)
        ]
        if conflicts:
            raise ValueError(
                "Chiave operazione POS contraddittoria "
                f"{item['operation_id']}: campi diversi {', '.join(conflicts)}"
            )
        changes = {
            field: item.get(field) for field in mutable_fields
            if item.get(field) not in (None, "")
            and previous.get(field) != item.get(field)
        }
        if changes:
            records_to_update.append((str(previous.get("id") or ""), changes))
            previous.update(changes)
            updated += 1
        else:
            unchanged += 1

    @asynccontextmanager
    async def _write_batch():
        factory = getattr(db, "batch_writes", None)
        if callable(factory):
            async with factory():
                yield
        else:
            yield

    from app.services.scritture_contabili import (
        GESTORE_POS_DEFAULT,
        registra_chiusura_pos_reale,
    )

    async with _write_batch():
        if records_to_insert:
            await db["pos_terminal_transactions"].insert_many(
                records_to_insert, ordered=False,
            )
        for record_id, changes in records_to_update:
            if not record_id:
                continue
            await db["pos_terminal_transactions"].update_one(
                {"id": record_id}, {"$set": {**changes, "updated_at": now}},
            )

        # La cache e' gia aggiornata dentro il batch: una sola scansione
        # sostituisce una query per ogni giorno del file.
        all_rows = await db["pos_terminal_transactions"].find(
            {}, {"_id": 0, "data": 1, "stato": 1, "importo": 1}
        ).to_list(250000)
        totals_by_date: defaultdict[str, float] = defaultdict(float)
        for row in all_rows:
            data_iso = row.get("data")
            if data_iso in affected_dates and row.get("stato") in _APPROVED_STATUSES:
                totals_by_date[data_iso] += float(row.get("importo") or 0)

        totals: Dict[str, float] = {}
        for data_iso in sorted(data for data in affected_dates if data):
            total = round(totals_by_date.get(data_iso, 0), 2)
            if total < 0:
                raise ValueError(f"Totale POS negativo per {data_iso}")
            await registra_chiusura_pos_reale(
                db, data_iso, total,
                gestore=GESTORE_POS_DEFAULT,
                fonte="excel",
                note="Import automatico POS BPM/Numia: somma transazioni approvate",
                actor={"user_id": "drive_pos_bpm", "name": "Import automatico Drive"},
            )
            totals[data_iso] = total

        await db["pos_terminal_imports"].update_one(
            {"file_hash": file_hash},
            {"$set": {
                "id": f"POS-IMPORT-{file_hash[:32]}",
                "operation_id": f"pos-import:{file_hash}",
                "drive_file_id": drive_file_id,
                "filename": filename,
                "file_hash": file_hash,
                "identity_version": "pos_numia_v2",
                "rows": parsed["rows"],
                "source_rows": parsed["source_rows"],
                "duplicates": parsed["duplicates"],
                "approved": parsed["approved"],
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    return {
        "rows": parsed["rows"], "source_rows": parsed["source_rows"],
        "duplicates": parsed["duplicates"], "approved": parsed["approved"],
        "inserted": inserted, "updated": updated, "unchanged": unchanged,
        "operation_identity": "pos_numia_v2",
        "days": len(totals), "daily_totals": totals,
    }
