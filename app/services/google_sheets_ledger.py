"""Registro portabile del gestionale su un unico Google Spreadsheet.

Mongo resta temporaneamente il motore operativo, ma ogni tabella canonica puo'
essere sincronizzata e ricostruita da questo registro. Ogni foglio conserva un
progressivo proprio e il payload JSON completo, senza perdere campi futuri.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from app.config import settings


SCHEMA_VERSION = "1"
WORKBOOK_TITLE = "Ceraldi ERP - Registro dati"
LEDGER_FOLDER_TITLE = "Gestionale ERP - Registro dati"
HEADERS = [
    "progressivo", "canonical_id", "operation_id", "data", "anno", "tipo",
    "importo", "descrizione", "stato", "documento_id", "fattura_id",
    "movimento_bancario_id", "source", "file_hash", "updated_at", "payload_json",
]


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


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def canonical_id(document: Dict[str, Any]) -> str:
    return str(
        document.get("id") or document.get("invoice_id")
        or document.get("document_id") or document.get("cedolino_id")
        or document.get("movement_id") or document.get("bonifico_id")
        or document.get("quietanza_id") or document.get("estratto_id")
        or document.get("invoice_key") or document.get("transaction_id")
        or document.get("file_hash")
        or document.get("pdf_hash") or document.get("fingerprint") or ""
    ).strip()


def canonical_filter(document: Dict[str, Any]) -> Dict[str, Any]:
    for field in (
        "id", "invoice_id", "document_id", "cedolino_id", "movement_id",
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
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default),
    ]


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
    return str((config or {}).get(name) or getattr(settings, name, None) or "").strip() or None


def default_folder_id(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    return (
        _setting_value(config, "GOOGLE_SHEETS_LEDGER_FOLDER_ID")
        or str(getattr(settings, "GOOGLE_DRIVE_FATTURE_FOLDER_ID", None) or "").strip()
        or str(getattr(settings, "GOOGLE_DRIVE_ESTRATTI_FOLDER_ID", None) or "").strip()
        or None
    )


def _ensure_workbook_sync(config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    sheets, drive = _services()
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
                "sheets": [{"properties": {"title": item.title}} for item in SHEETS]
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
    missing = [item.title for item in SHEETS if item.title not in existing]
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
    for item in SHEETS:
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
        {"range": f"'{item.title}'!A1:P1", "values": [HEADERS]}
        for item in SHEETS
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
    }


async def ensure_workbook(config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    return await asyncio.to_thread(_ensure_workbook_sync, config)


def _read_existing_sync(spreadsheet_id: str, sheet: LedgerSheet):
    sheets, _ = _services()
    values = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{sheet.title}'!A2:P",
    ).execute().get("values", [])
    return values


def _write_rows_sync(spreadsheet_id: str, sheet: LedgerSheet, rows: List[List[Any]]) -> None:
    if not rows:
        return
    sheets, _ = _services()
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet.title}'!A2:P{len(rows) + 1}",
        valueInputOption="RAW", body={"values": rows},
    ).execute()


async def sync_collection(db, sheet: LedgerSheet, spreadsheet_id: str) -> Dict[str, Any]:
    documents = await db[sheet.collection].find({}, {"_id": 0}).to_list(100000)
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


async def sync_all(db, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    workbook = await ensure_workbook(config)
    results = await asyncio.gather(*(
        sync_collection(db, sheet, workbook["spreadsheet_id"])
        for sheet in SHEETS
    ))
    return {**workbook, "schema_version": SCHEMA_VERSION, "fogli": results}


def sheet_manifest() -> List[Dict[str, str]]:
    return [
        {"foglio": item.title, "collezione": item.collection, "prefisso": item.prefix}
        for item in SHEETS
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
    results = []
    for sheet in SHEETS:
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
                payload = json.loads(str(row[15] or "{}"))
            except json.JSONDecodeError as exc:
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
            "valide": valid, "errori": errors[:100], "numero_errori": len(errors),
        })
    return {
        **workbook, "apply": apply, "schema_version": SCHEMA_VERSION,
        "fogli": results,
    }
