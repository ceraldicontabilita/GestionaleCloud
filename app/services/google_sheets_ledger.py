"""Registro portabile del gestionale su un unico Google Spreadsheet.

Mongo resta temporaneamente il motore operativo, ma ogni tabella canonica puo'
essere sincronizzata e ricostruita da questo registro. Ogni foglio conserva un
progressivo proprio e il payload JSON completo, senza perdere campi futuri.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import gzip
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from app.config import settings


SCHEMA_VERSION = "1"
WORKBOOK_TITLE = "Ceraldi ERP - Registro dati"
LEDGER_FOLDER_TITLE = "Gestionale ERP - Registro dati"
BASE_HEADERS = [
    "progressivo", "canonical_id", "operation_id", "data", "anno", "tipo",
    "importo", "descrizione", "stato", "documento_id", "fattura_id",
    "movimento_bancario_id", "source", "file_hash", "updated_at", "payload_json",
]
MAX_SHEETS_CELL_CHARS = 49000
PAYLOAD_CHUNK_COUNT = 64
HEADERS = BASE_HEADERS + [f"payload_json_{index:03d}" for index in range(2, PAYLOAD_CHUNK_COUNT + 1)]
LAST_COLUMN = "CA"
GZIP_PREFIX = "gzip+base64:"


@dataclass(frozen=True)
class LedgerSheet:
    title: str
    collection: str
    prefix: str


SHEETS: tuple[LedgerSheet, ...] = (
    LedgerSheet("Documenti", "documents_inbox", "DOC"),
    LedgerSheet("Fatture ricevute", "invoices", "FAR"),
    LedgerSheet("Fatture emesse", "fatture_emesse", "FAE"),
    LedgerSheet("Fornitori", "fornitori", "FOR"),
    LedgerSheet("Dipendenti", "dipendenti", "DIP"),
    LedgerSheet("Cedolini", "cedolini", "CED"),
    LedgerSheet("Estratti conto", "estratti_conto", "ECD"),
    LedgerSheet("Movimenti bancari", "estratto_conto_movimenti", "ECM"),
    LedgerSheet("Prima Nota Cassa", "prima_nota_cassa", "CAS"),
    LedgerSheet("Prima Nota Banca", "prima_nota_banca", "BAN"),
    LedgerSheet("Bonifici", "bonifici_transfers", "BON"),
    LedgerSheet("Assegni", "assegni", "ASS"),
    LedgerSheet("Corrispettivi", "corrispettivi", "COR"),
    LedgerSheet("F24", "f24_unificato", "F24"),
    LedgerSheet("Quietanze F24", "quietanze_f24", "QF24"),
    LedgerSheet("PayPal", "paypal_transactions", "PAY"),
    LedgerSheet("Scadenze fornitori", "scadenziario_fornitori", "SCA"),
    LedgerSheet("Relazioni", "entity_relations", "REL"),
)


def dynamic_sheet(collection: str) -> LedgerSheet:
    """Definizione stabile per ogni collezione non inclusa nei fogli noti."""
    safe_collection = str(collection).strip()
    if not safe_collection:
        raise ValueError("Nome collezione mancante")
    title = f"DB_{safe_collection}"[:100]
    prefix = "D" + hashlib.sha1(safe_collection.encode("utf-8")).hexdigest()[:6].upper()
    return LedgerSheet(title, safe_collection, prefix)


def sheet_definitions(collections: Iterable[str] = ()) -> tuple[LedgerSheet, ...]:
    known = {sheet.collection for sheet in SHEETS}
    extras = sorted({str(name) for name in collections if str(name) and str(name) not in known})
    return SHEETS + tuple(dynamic_sheet(name) for name in extras)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def encode_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=_json_default,
        separators=(",", ":"),
    )
    if len(raw) <= MAX_SHEETS_CELL_CHARS:
        return raw
    compressed = GZIP_PREFIX + base64.b64encode(
        gzip.compress(raw.encode("utf-8"), compresslevel=9)
    ).decode("ascii")
    if len(compressed) > MAX_SHEETS_CELL_CHARS * PAYLOAD_CHUNK_COUNT:
        raise ValueError(
            "Payload troppo grande per il registro Sheets anche dopo compressione"
        )
    return compressed


def payload_chunks(payload: Dict[str, Any]) -> List[str]:
    encoded = encode_payload(payload)
    return [
        encoded[index:index + MAX_SHEETS_CELL_CHARS]
        for index in range(0, len(encoded), MAX_SHEETS_CELL_CHARS)
    ]


def decode_payload(value: Any) -> Dict[str, Any]:
    raw = str(value or "{}")
    if raw.startswith(GZIP_PREFIX):
        raw = gzip.decompress(
            base64.b64decode(raw[len(GZIP_PREFIX):].encode("ascii"))
        ).decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("payload_json non e' un oggetto")
    return payload


def canonical_id(document: Dict[str, Any]) -> str:
    return str(
        document.get("id") or document.get("_mongo_id")
        or document.get("invoice_id")
        or document.get("document_id") or document.get("cedolino_id")
        or document.get("movement_id") or document.get("bonifico_id")
        or document.get("quietanza_id") or document.get("estratto_id")
        or document.get("invoice_key") or document.get("transaction_id")
        or document.get("file_hash")
        or document.get("pdf_hash") or document.get("fingerprint") or ""
    ).strip()


def canonical_filter(document: Dict[str, Any]) -> Dict[str, Any]:
    for field in (
        "id", "_mongo_id", "invoice_id", "document_id", "cedolino_id", "movement_id",
        "bonifico_id", "quietanza_id", "estratto_id", "invoice_key",
        "transaction_id", "file_hash", "pdf_hash", "fingerprint",
    ):
        value = document.get(field)
        if value not in (None, ""):
            return {field: value}
    raise ValueError("Documento senza chiave canonica")


def operation_id(document: Dict[str, Any]) -> str:
    return str(
        document.get("payment_operation_id")
        or document.get("trasferimento_operation_id")
        or document.get("operation_id") or document.get("operazione_id") or ""
    ).strip()


def _first(document: Dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = document.get(name)
        if value not in (None, ""):
            return value
    return ""


def row_for_document(document: Dict[str, Any], progressivo: str) -> List[Any]:
    payload = {key: value for key, value in document.items() if key != "_id"}
    raw_date = _first(document, ("data", "invoice_date", "data_documento", "date", "created_at"))
    data_value = str(raw_date)[:10] if raw_date else ""
    anno = document.get("anno") or (data_value[:4] if re.match(r"^\d{4}", data_value) else "")
    amount = _first(document, ("importo", "total_amount", "importo_totale", "amount", "lordo"))
    return [
        progressivo,
        canonical_id(document),
        operation_id(document),
        data_value,
        anno,
        _first(document, ("tipo", "document_type", "tipo_documento")),
        amount,
        _first(document, ("descrizione", "descrizione_originale", "supplier_name", "filename")),
        _first(document, ("stato", "status", "stato_pagamento", "payment_status")),
        _first(document, ("documento_id", "source_document_id", "documents_inbox_id")),
        _first(document, ("fattura_id", "invoice_id")),
        _first(document, ("movimento_bancario_id", "movimento_banca_id", "estratto_conto_id", "movimento_estratto_conto_id")),
        _first(document, ("source", "fonte")),
        _first(document, ("file_hash", "pdf_hash", "fingerprint")),
        str(_first(document, ("updated_at", "created_at"))),
    ] + payload_chunks(payload)


def next_progressive(prefix: str, values: Iterable[str]) -> int:
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for value in values:
        match = pattern.match(str(value or "").strip())
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def format_progressive(prefix: str, number: int) -> str:
    return f"{prefix}-{number:08d}"


def _credentials():
    from app.services.drive_invoice_ingest import _parse_sa_json
    from google.oauth2 import service_account

    raw = (
        getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE", None)
        or getattr(settings, "GOOGLE_DRIVE_SA_JSON", None)
        or getattr(settings, "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", None)
    )
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    if raw:
        return service_account.Credentials.from_service_account_info(
            _parse_sa_json(raw), scopes=scopes,
        )
    path = getattr(settings, "GOOGLE_DRIVE_SA_FILE", None)
    if path:
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)
    raise RuntimeError("Credenziali Google Drive non configurate")


def _services():
    from googleapiclient.discovery import build
    credentials = _credentials()
    return (
        build("sheets", "v4", credentials=credentials, cache_discovery=False),
        build("drive", "v3", credentials=credentials, cache_discovery=False),
    )


def _setting_value(config: Optional[Dict[str, Any]], name: str) -> Optional[str]:
    if name == "GOOGLE_SHEETS_LEDGER_ID" and (config or {}).get("GOOGLE_SHEETS_LEDGER_FORCE_NEW"):
        return None
    return str((config or {}).get(name) or getattr(settings, name, None) or "").strip() or None


def default_folder_id(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    return (
        _setting_value(config, "GOOGLE_SHEETS_LEDGER_FOLDER_ID")
        or str(getattr(settings, "GOOGLE_DRIVE_FATTURE_FOLDER_ID", None) or "").strip()
        or str(getattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_ID", None) or "").strip()
        or None
    )


def _ensure_workbook_sync(
    config: Optional[Dict[str, Any]] = None,
    collections: Iterable[str] = (),
) -> Dict[str, Any]:
    sheets, drive = _services()
    requested_sheets = sheet_definitions(collections)
    spreadsheet_id = _setting_value(config, "GOOGLE_SHEETS_LEDGER_ID")
    configured_folder_id = _setting_value(config, "GOOGLE_SHEETS_LEDGER_FOLDER_ID")
    folder_id = default_folder_id(config)
    # Se usiamo una cartella Drive gia configurata per gli import, creiamo
    # una sottocartella dedicata: il registro non si mescola ai documenti.
    if folder_id and not configured_folder_id:
        escaped_folder = LEDGER_FOLDER_TITLE.replace("'", "\\'")
        folders = drive.files().list(
            q=(f"name='{escaped_folder}' and '{folder_id}' in parents and "
               "mimeType='application/vnd.google-apps.folder' and trashed=false"),
            fields="files(id,name)", pageSize=2,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        if len(folders) > 1:
            raise RuntimeError("Piu cartelle registro con lo stesso nome")
        if folders:
            folder_id = folders[0]["id"]
        else:
            folder_id = drive.files().create(
                body={
                    "name": LEDGER_FOLDER_TITLE,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [folder_id],
                },
                fields="id", supportsAllDrives=True,
            ).execute()["id"]
    if not spreadsheet_id and folder_id:
        escaped_title = WORKBOOK_TITLE.replace("'", "\\'")
        found = drive.files().list(
            q=(f"name='{escaped_title}' and '{folder_id}' in parents and "
               "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"),
            fields="files(id,name,webViewLink)", pageSize=2,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        if len(found) > 1:
            raise RuntimeError("Piu registri con lo stesso nome nella cartella Drive")
        if found:
            spreadsheet_id = found[0]["id"]
    if not spreadsheet_id:
        if folder_id:
            # Un service account non dispone di quota Drive propria. Creare
            # prima il foglio nella sua radice con Sheets API fallisce con
            # PERMISSION_DENIED anche se la cartella aziendale e' condivisa.
            # Drive API crea invece il file direttamente nella cartella
            # autorizzata, mantenendo proprieta' e spazio sul Drive aziendale.
            created = drive.files().create(
                body={
                    "name": WORKBOOK_TITLE,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [folder_id],
                },
                fields="id,webViewLink,parents",
                supportsAllDrives=True,
            ).execute()
            spreadsheet_id = created["id"]
        else:
            body = {
                "properties": {"title": WORKBOOK_TITLE, "locale": "it_IT", "timeZone": "Europe/Rome"},
                "sheets": [{"properties": {"title": item.title}} for item in requested_sheets]
                + [{"properties": {"title": "_REGISTRO"}}],
            }
            created = sheets.spreadsheets().create(
                body=body, fields="spreadsheetId,spreadsheetUrl"
            ).execute()
            spreadsheet_id = created["spreadsheetId"]

    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="spreadsheetId,spreadsheetUrl,sheets.properties",
    ).execute()
    existing = {item["properties"]["title"] for item in metadata.get("sheets", [])}
    # I fogli dinamici gia presenti sono parte del database anche quando il
    # chiamante non conosce ancora le collezioni (avvio in modalita Sheets).
    existing_dynamic = [
        dynamic_sheet(title[3:]) for title in existing if title.startswith("DB_")
    ]
    requested_sheets = sheet_definitions(
        [item.collection for item in requested_sheets] +
        [item.collection for item in existing_dynamic]
    )
    missing = [item.title for item in requested_sheets if item.title not in existing]
    if "_REGISTRO" not in existing:
        missing.append("_REGISTRO")
    if missing:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}} for title in missing]},
        ).execute()
        metadata = sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="spreadsheetId,spreadsheetUrl,sheets.properties",
        ).execute()
    sheet_ids = {
        item["properties"]["title"]: item["properties"]["sheetId"]
        for item in metadata.get("sheets", [])
    }
    format_requests = []
    for item in requested_sheets:
        sheet_id = sheet_ids[item.title]
        format_requests.extend([
            {"updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }},
            {"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.92, "green": 0.92, "blue": 0.92},
                    "textFormat": {"bold": True},
                    "wrapStrategy": "WRAP",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,wrapStrategy)",
            }},
        ])
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": format_requests},
    ).execute()
    # Una sola richiesta per tutte le intestazioni. Le chiamate seriali per
    # foglio rendevano la sincronizzazione live piu' lenta del timeout HTTP e
    # lasciavano un workbook formalmente creato ma privo di righe.
    header_updates = [
        {"range": f"'{item.title}'!A1:{LAST_COLUMN}1", "values": [HEADERS]}
        for item in requested_sheets
    ]
    header_updates.append({
        "range": "'_REGISTRO'!A1:B4",
        "values": [
            ["chiave", "valore"], ["schema_version", SCHEMA_VERSION],
            ["titolo", WORKBOOK_TITLE],
            ["ultimo_aggiornamento", datetime.now(timezone.utc).isoformat()],
        ],
    })
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": header_updates},
    ).execute()
    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": metadata.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        "folder_id": folder_id or "",
        "sheet_definitions": requested_sheets,
    }


async def ensure_workbook(
    config: Optional[Dict[str, Any]] = None,
    collections: Iterable[str] = (),
) -> Dict[str, Any]:
    return await asyncio.to_thread(_ensure_workbook_sync, config, tuple(collections))


def _drive_duplicate_audit_sync(folder_id: str) -> Dict[str, Any]:
    _, drive = _services()
    files = []
    page_token = None
    while True:
        response = drive.files().list(
            q="trashed = false",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,createdTime,modifiedTime,webViewLink,parents)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in files:
        checksum = str(item.get("md5Checksum") or "").strip()
        size = str(item.get("size") or "")
        if checksum:
            key = f"hash:{checksum}"
            method = "md5"
        else:
            key = f"name-size:{item.get('name', '').casefold()}:{size}"
            method = "nome_dimensione"
        entry = {**item, "metodo": method}
        groups.setdefault(key, []).append(entry)

    duplicates = [
        {"chiave": key, "metodo": items[0]["metodo"], "file": items}
        for key, items in groups.items() if len(items) > 1
    ]
    duplicates.sort(key=lambda group: (-len(group["file"]), group["chiave"]))
    duplicate_files = sum(len(group["file"]) - 1 for group in duplicates)
    recoverable_bytes = sum(
        int(item.get("size") or 0)
        for group in duplicates for item in group["file"][1:]
    )
    return {
        "folder_id": folder_id,
        "ambito": "tutti_i_file_visibili_account_servizio",
        "file_nella_cartella_registro": sum(folder_id in item.get("parents", []) for item in files),
        "totale_file": len(files),
        "gruppi_duplicati": len(duplicates),
        "file_duplicati_eccedenti": duplicate_files,
        "spazio_recuperabile_bytes": recoverable_bytes,
        "duplicati": duplicates,
    }


async def drive_duplicate_audit(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    folder_id = default_folder_id(config)
    if not folder_id:
        raise ValueError("Cartella Drive del registro non configurata")
    return await asyncio.to_thread(_drive_duplicate_audit_sync, folder_id)


def _read_existing_sync(spreadsheet_id: str, sheet: LedgerSheet):
    sheets, _ = _services()
    values = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{sheet.title}'!A2:{LAST_COLUMN}",
    ).execute().get("values", [])
    return values


def _read_identities_sync(spreadsheet_id: str, sheet: LedgerSheet):
    sheets, _ = _services()
    return sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{sheet.title}'!A2:B",
    ).execute().get("values", [])


def _clear_rows_sync(spreadsheet_id: str, sheet: LedgerSheet) -> None:
    sheets, _ = _services()
    sheets.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet.title}'!A2:{LAST_COLUMN}", body={},
    ).execute()


def _ensure_row_capacity_sync(
    spreadsheet_id: str, sheet: LedgerSheet, required_rows: int,
) -> None:
    sheets, _ = _services()
    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties",
    ).execute()
    properties = next(
        item["properties"] for item in metadata.get("sheets", [])
        if item.get("properties", {}).get("title") == sheet.title
    )
    current = int(properties.get("gridProperties", {}).get("rowCount") or 0)
    if current == required_rows:
        return
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"updateSheetProperties": {
            "properties": {
                "sheetId": properties["sheetId"],
                "gridProperties": {"rowCount": required_rows},
            },
            "fields": "gridProperties.rowCount",
        }}]},
    ).execute()


def _resize_all_sheets_sync(
    spreadsheet_id: str, definitions: Iterable[LedgerSheet], counts: Dict[str, int],
) -> None:
    """Elimina le celle vuote preallocate che concorrono al limite di 10M."""
    sheets, _ = _services()
    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties",
    ).execute()
    by_title = {
        item["properties"]["title"]: item["properties"]
        for item in metadata.get("sheets", [])
    }
    requests = []
    for definition in definitions:
        properties = by_title.get(definition.title)
        if not properties:
            continue
        target_rows = max(int(counts.get(definition.collection) or 0) + 1, 2)
        requests.append({"updateSheetProperties": {
            "properties": {
                "sheetId": properties["sheetId"],
                "gridProperties": {
                    "rowCount": target_rows,
                    "columnCount": len(HEADERS),
                },
            },
            "fields": "gridProperties(rowCount,columnCount)",
        }})
    if requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests},
        ).execute()


def _write_batch_sync(
    spreadsheet_id: str, sheet: LedgerSheet, rows: List[List[Any]], start_row: int,
) -> None:
    if not rows:
        return
    sheets, _ = _services()
    end_row = start_row + len(rows) - 1
    request = lambda: sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet.title}'!A{start_row}:{LAST_COLUMN}{end_row}",
        valueInputOption="RAW", body={"values": rows},
    )
    last_error = None
    for attempt in range(5):
        try:
            request().execute()
            return
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(min(2 ** attempt, 8))
    if len(rows) > 1:
        midpoint = len(rows) // 2
        _write_batch_sync(spreadsheet_id, sheet, rows[:midpoint], start_row)
        _write_batch_sync(spreadsheet_id, sheet, rows[midpoint:], start_row + midpoint)
        return
    raise last_error


def _write_rows_sync(spreadsheet_id: str, sheet: LedgerSheet, rows: List[List[Any]]) -> None:
    sheets, _ = _services()
    # Rimuove anche le righe finali non piu' presenti. Un semplice update
    # lasciava record fantasma quando l'archivio diminuiva.
    sheets.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet.title}'!A2:{LAST_COLUMN}",
        body={},
    ).execute()
    if not rows:
        return
    # Evita richieste monolitiche che saturano memoria e proxy con archivi da
    # decine di migliaia di movimenti (POS, audit, magazzino).
    batch_size = 500
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset:offset + batch_size]
        start_row = offset + 2
        end_row = start_row + len(batch) - 1
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet.title}'!A{start_row}:{LAST_COLUMN}{end_row}",
            valueInputOption="RAW", body={"values": batch},
        ).execute()


async def sync_collection(
    db, sheet: LedgerSheet, spreadsheet_id: str, *, preserve_missing: bool = True,
) -> Dict[str, Any]:
    documents = await db[sheet.collection].find({}).to_list(100000)
    for document in documents:
        mongo_id = document.pop("_id", None)
        if mongo_id is not None and not canonical_id(document):
            # Gli archivi storici talvolta hanno soltanto ObjectId. Lo rendiamo
            # esplicito e portabile, senza affidare l'identita a importo/data.
            document["_mongo_id"] = str(mongo_id)
    existing = await asyncio.to_thread(_read_existing_sync, spreadsheet_id, sheet)
    existing_progressives = [str(row[0]).strip() for row in existing if row and str(row[0]).strip()]
    existing_ids = [str(row[1]).strip() for row in existing if len(row) > 1 and str(row[1]).strip()]
    if len(existing_progressives) != len(set(existing_progressives)):
        raise RuntimeError(f"Progressivi duplicati nel foglio {sheet.title}")
    if len(existing_ids) != len(set(existing_ids)):
        raise RuntimeError(f"canonical_id duplicati nel foglio {sheet.title}")
    progress_by_id = {
        str(row[1]): str(row[0]) for row in existing if len(row) > 1 and str(row[1]).strip()
    }
    sequence = next_progressive(sheet.prefix, [row[0] for row in existing if row])
    rows: List[List[Any]] = []
    current_keys = set()
    skipped_without_id = 0
    for document in documents:
        key = canonical_id(document)
        if not key:
            skipped_without_id += 1
            continue
        current_keys.add(key)
        progressive = progress_by_id.get(key)
        if not progressive:
            progressive = format_progressive(sheet.prefix, sequence)
            sequence += 1
        rows.append(row_for_document(document, progressive))
    # Una cancellazione o una collezione temporaneamente incompleta non deve
    # eliminare la copia Drive: le righe non piu' presenti restano recuperabili.
    if preserve_missing:
        for existing_row in existing:
            existing_key = str(existing_row[1] if len(existing_row) > 1 else "").strip()
            if existing_key and existing_key not in current_keys:
                rows.append(list(existing_row) + [""] * max(0, len(HEADERS) - len(existing_row)))
    rows.sort(key=lambda row: row[0])
    await asyncio.to_thread(_write_rows_sync, spreadsheet_id, sheet, rows)
    return {
        "foglio": sheet.title, "collezione": sheet.collection,
        "righe": len(rows), "senza_id": skipped_without_id,
    }


async def sync_collection_streaming(db, sheet: LedgerSheet, spreadsheet_id: str) -> Dict[str, Any]:
    """Migrazione canonica a memoria costante, senza conservare righe fantasma."""
    identities = await asyncio.to_thread(_read_identities_sync, spreadsheet_id, sheet)
    progress_by_id = {
        str(row[1]): str(row[0]) for row in identities
        if len(row) > 1 and str(row[0]).strip() and str(row[1]).strip()
    }
    if len(progress_by_id) != len(identities):
        # Le righe vuote finali non vengono restituite dall'API; ogni altra
        # discrepanza segnala identita mancanti o duplicate.
        valid = [row for row in identities if len(row) > 1 and str(row[0]).strip() and str(row[1]).strip()]
        if len(progress_by_id) != len(valid):
            raise RuntimeError(f"Progressivi o canonical_id duplicati nel foglio {sheet.title}")
    sequence = next_progressive(sheet.prefix, [row[0] for row in identities if row])
    source_count = await db[sheet.collection].count_documents({})
    await asyncio.to_thread(
        _ensure_row_capacity_sync, spreadsheet_id, sheet, max(source_count + 1, 2),
    )
    batch: List[List[Any]] = []
    written = len(progress_by_id)
    skipped_without_id = 0
    cursor = db[sheet.collection].find({})
    async for document in cursor:
        mongo_id = document.pop("_id", None)
        if mongo_id is not None and not canonical_id(document):
            document["_mongo_id"] = str(mongo_id)
        key = canonical_id(document)
        if not key:
            skipped_without_id += 1
            continue
        if key in progress_by_id:
            continue
        progressive = progress_by_id.get(key)
        if not progressive:
            progressive = format_progressive(sheet.prefix, sequence)
            sequence += 1
        batch.append(row_for_document(document, progressive))
        if len(batch) >= 100:
            await asyncio.to_thread(_write_batch_sync, spreadsheet_id, sheet, batch, written + 2)
            written += len(batch)
            batch = []
    if batch:
        await asyncio.to_thread(_write_batch_sync, spreadsheet_id, sheet, batch, written + 2)
        written += len(batch)
    return {
        "foglio": sheet.title, "collezione": sheet.collection,
        "righe": written, "senza_id": skipped_without_id,
    }


async def sync_all(db, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    collections = await db.list_collection_names()
    workbook = await ensure_workbook(config, collections)
    definitions = workbook.pop("sheet_definitions")
    source_counts = {
        sheet.collection: await db[sheet.collection].count_documents({})
        for sheet in definitions
    }
    await asyncio.to_thread(
        _resize_all_sheets_sync, workbook["spreadsheet_id"], definitions, source_counts,
    )
    semaphore = asyncio.Semaphore(1)

    async def _sync_bounded(sheet: LedgerSheet) -> Dict[str, Any]:
        async with semaphore:
            return await sync_collection_streaming(db, sheet, workbook["spreadsheet_id"])

    results = await asyncio.gather(*(_sync_bounded(sheet) for sheet in definitions))
    return {**workbook, "schema_version": SCHEMA_VERSION, "fogli": results}


async def migration_audit(db, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Confronta Mongo sorgente e registro Drive senza modificare dati."""
    verification = await restore_all(db, config, apply=False)
    by_collection = {
        item["collezione"]: item for item in verification.get("fogli", [])
    }
    checks = []
    audited_definitions = sheet_definitions(
        item.get("collezione") for item in verification.get("fogli", [])
    )
    for sheet in audited_definitions:
        source_count = await db[sheet.collection].count_documents({})
        verified = by_collection.get(sheet.collection, {})
        sheet_count = int(verified.get("valide") or 0)
        errors = int(verified.get("numero_errori") or 0)
        checks.append({
            "foglio": sheet.title,
            "collezione": sheet.collection,
            "sorgente": source_count,
            "drive": sheet_count,
            "errori": errors,
            "completo": source_count == sheet_count and errors == 0,
        })

    migrated = {sheet.collection for sheet in audited_definitions}
    non_migrated = []
    for name in await db.list_collection_names():
        if name in migrated:
            continue
        count = await db[name].count_documents({})
        if count:
            non_migrated.append({"collezione": name, "righe": count})
    non_migrated.sort(key=lambda item: (-item["righe"], item["collezione"]))
    return {
        "pronto_cutover": all(item["completo"] for item in checks) and not non_migrated,
        "fogli": checks,
        "collezioni_non_migrate": non_migrated,
        "totale_non_migrate": sum(item["righe"] for item in non_migrated),
        "spreadsheet_id": verification.get("spreadsheet_id"),
    }


def sheet_manifest(collections: Iterable[str] = ()) -> List[Dict[str, str]]:
    return [
        {"foglio": item.title, "collezione": item.collection, "prefisso": item.prefix}
        for item in sheet_definitions(collections)
    ]


def _read_sheet_rows_sync(spreadsheet_id: str, sheet: LedgerSheet) -> List[List[Any]]:
    return _read_existing_sync(spreadsheet_id, sheet)


async def restore_all(
    db, config: Optional[Dict[str, Any]] = None, *, apply: bool = False,
) -> Dict[str, Any]:
    """Valida o ricostruisce le collezioni dal payload JSON dei fogli.

    Il default e' sempre dry-run. In modalita apply usa upsert sull'ID
    canonico e non cancella documenti presenti nel database.
    """
    workbook = await ensure_workbook(config)
    definitions = workbook.pop("sheet_definitions")
    results = []
    for sheet in definitions:
        rows = await asyncio.to_thread(
            _read_sheet_rows_sync, workbook["spreadsheet_id"], sheet,
        )
        valid = 0
        errors = []
        seen_progressive = set()
        seen_ids = set()
        for index, row in enumerate(rows, start=2):
            if len(row) < len(HEADERS):
                row = list(row) + [""] * (len(HEADERS) - len(row))
            progressive = str(row[0] or "").strip()
            key = str(row[1] or "").strip()
            try:
                payload = decode_payload("".join(str(part or "") for part in row[15:]))
            except (ValueError, json.JSONDecodeError, gzip.BadGzipFile, binascii.Error) as exc:
                errors.append({"riga": index, "errore": f"payload_json non valido: {exc}"})
                continue
            if not progressive or not key or not isinstance(payload, dict):
                errors.append({"riga": index, "errore": "progressivo, canonical_id o payload mancanti"})
                continue
            if progressive in seen_progressive or key in seen_ids:
                errors.append({"riga": index, "errore": "progressivo o canonical_id duplicato"})
                continue
            seen_progressive.add(progressive)
            seen_ids.add(key)
            if canonical_id(payload) != key:
                errors.append({"riga": index, "errore": "canonical_id diverso dal payload"})
                continue
            valid += 1
            if apply:
                await db[sheet.collection].replace_one(
                    canonical_filter(payload), payload, upsert=True,
                )
        results.append({
            "foglio": sheet.title, "collezione": sheet.collection,
            "prefisso": sheet.prefix,
            "valide": valid, "errori": errors[:100], "numero_errori": len(errors),
        })
    return {
        **workbook, "apply": apply, "schema_version": SCHEMA_VERSION,
        "fogli": results,
    }
