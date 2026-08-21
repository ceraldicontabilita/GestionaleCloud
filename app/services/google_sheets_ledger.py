"""Registro operativo del gestionale su Google Drive/Google Sheets.

Ogni archivio ha un foglio, un progressivo stabile, un identificativo canonico
e il payload JSON completo. Drive conserva gli originali; Sheets e' l'archivio
operativo interrogato dall'applicazione.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import gzip
import hashlib
import json
import re
import threading
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
    LedgerSheet("Codici tributo", "tax_code_registry", "CTR"),
    LedgerSheet("Import PartenoPay", "partenopay_import_runs", "PPR"),
    LedgerSheet("Email PartenoPay", "verbali_email_archive", "PPE"),
    LedgerSheet("Verbali PartenoPay", "verbali_noleggio", "PPV"),
    # Stato tecnico degli import Drive/Gmail e configurazione operativa. Non e'
    # Questo foglio e' la sorgente persistente per checkpoint e chiavi
    # idempotenti dei job automatici.
    LedgerSheet("Stato sistema", "sistema_stato", "SYS"),
)

# Sotto la radice indicata dall'amministratore il gestionale mantiene una
# tassonomia piccola e stabile. I documenti originali non vengono mai spostati
# automaticamente: gli ingest futuri li archiviano qui e l'indice conserva i
# percorsi storici gia' esistenti.
ARCHIVE_TREE_NAMES: tuple[str, ...] = (
    "REGISTRO DATI",
    "PARTENOPAY",
    "CODICI TRIBUTO",
    "QUIETANZE",
    "DICHIARAZIONI",
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
        document.get("id") or document.get("_record_id")
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
        "id", "_record_id", "invoice_id", "document_id", "cedolino_id", "movement_id",
        "bonifico_id", "quietanza_id", "estratto_id", "invoice_key",
        "transaction_id", "file_hash", "pdf_hash", "fingerprint",
    ):
        value = document.get(field)
        if value not in (None, ""):
            return {field: value}
    raise ValueError("Documento senza chiave canonica")


def portable_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """Copia serializzabile con identita portabile anche per record storici."""
    payload = dict(document)
    record_id = payload.pop("_id", None)
    if record_id is not None and not canonical_id(payload):
        payload["_record_id"] = str(record_id)
    return payload


def document_fingerprint(document: Dict[str, Any]) -> str:
    payload = portable_document(document)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=_json_default,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def collection_fingerprint(fingerprints: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(str(item) for item in fingerprints):
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


async def source_collection_snapshot(db, collection_name: str) -> Dict[str, Any]:
    """Conta e deduplica per identita, distinguendo copie esatte e conflitti."""
    raw_count = 0
    without_id = 0
    exact_duplicates = 0
    by_id: Dict[str, str] = {}
    conflicts: List[Dict[str, str]] = []
    async for raw in db[collection_name].find({}):
        raw_count += 1
        document = portable_document(raw)
        key = canonical_id(document)
        if not key:
            without_id += 1
            continue
        fingerprint = document_fingerprint(document)
        previous = by_id.get(key)
        if previous is None:
            by_id[key] = fingerprint
        elif previous == fingerprint:
            exact_duplicates += 1
        else:
            conflicts.append({"canonical_id": key, "motivo": "payload_diversi"})
    return {
        "righe_sorgente": raw_count,
        "identita_uniche": len(by_id),
        "duplicati_esatti": exact_duplicates,
        "senza_id": without_id,
        "conflitti": conflicts[:100],
        "numero_conflitti": len(conflicts),
        "digest": collection_fingerprint(by_id.values()),
    }


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
        # Necessario per l'audit ricorsivo, esclusivamente in lettura, delle
        # cartelle Drive indicate dall'amministratore. ``drive.file`` da solo
        # espone soltanto i file creati o gia' aperti dall'applicazione e puo'
        # quindi produrre un falso archivio vuoto.
        "https://www.googleapis.com/auth/drive.metadata.readonly",
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


_sheets_thread_local = threading.local()


def _sheets_service():
    """Crea solo il client Sheets per le operazioni che non usano Drive.

    Il runtime web legge il registro all'avvio. Costruire anche un client
    Drive per ogni foglio moltiplicava memoria e discovery document fino a
    superare il limite del servizio Render.
    """
    from googleapiclient.discovery import build

    service = getattr(_sheets_thread_local, "service", None)
    if service is None:
        service = build(
            "sheets", "v4", credentials=_credentials(), cache_discovery=False,
        )
        _sheets_thread_local.service = service
    return service


def _escape_drive_query(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _ensure_child_folder_sync(drive, parent_id: str, name: str) -> Dict[str, Any]:
    escaped = _escape_drive_query(name)
    found = drive.files().list(
        q=(f"name='{escaped}' and '{parent_id}' in parents and "
           "mimeType='application/vnd.google-apps.folder' and trashed=false"),
        fields="files(id,name,webViewLink,parents)", pageSize=3,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    if len(found) > 1:
        raise RuntimeError(f"Cartella Drive duplicata: {name}")
    if found:
        return found[0]
    return drive.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id,name,webViewLink,parents", supportsAllDrives=True,
    ).execute()


def _ensure_archive_tree_sync(drive, root_id: str) -> Dict[str, Dict[str, Any]]:
    root = drive.files().get(
        fileId=root_id, fields="id,name,mimeType,trashed,webViewLink",
        supportsAllDrives=True,
    ).execute()
    if root.get("trashed") or root.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("La radice Drive del gestionale non e' una cartella attiva")
    folders = {
        name: _ensure_child_folder_sync(drive, root_id, name)
        for name in ARCHIVE_TREE_NAMES
    }
    return {"RADICE": root, **folders}


def _drive_cleanup_service():
    """Client Drive con scrittura, usato solo dalla pulizia esplicita admin."""
    from app.services.drive_invoice_ingest import _parse_sa_json
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = (
        getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE", None)
        or getattr(settings, "GOOGLE_DRIVE_SA_JSON", None)
        or getattr(settings, "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", None)
    )
    scopes = ["https://www.googleapis.com/auth/drive"]
    if raw:
        credentials = service_account.Credentials.from_service_account_info(
            _parse_sa_json(raw), scopes=scopes,
        )
    else:
        path = getattr(settings, "GOOGLE_DRIVE_SA_FILE", None)
        if not path:
            raise RuntimeError("Credenziali Google Drive non configurate")
        credentials = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _setting_value(config: Optional[Dict[str, Any]], name: str) -> Optional[str]:
    if name == "GOOGLE_SHEETS_LEDGER_ID" and (config or {}).get("GOOGLE_SHEETS_LEDGER_FORCE_NEW"):
        return None
    return str((config or {}).get(name) or getattr(settings, name, None) or "").strip() or None


def default_folder_id(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return the explicit root of the operational ledger.

    Fatture ed estratti conto hanno cartelle documentali proprie: usarle come
    radice implicita del registro rendeva il risultato dipendente da una
    configurazione legacy e poteva creare alberi diversi fra ambienti.
    """
    return _setting_value(config, "GOOGLE_SHEETS_LEDGER_FOLDER_ID")


def _ensure_workbook_sync(
    config: Optional[Dict[str, Any]] = None,
    collections: Iterable[str] = (),
) -> Dict[str, Any]:
    sheets, drive = _services()
    requested_sheets = sheet_definitions(collections)
    spreadsheet_id = _setting_value(config, "GOOGLE_SHEETS_LEDGER_ID")
    folder_id = default_folder_id(config)
    archive_tree: Dict[str, Dict[str, Any]] = {}
    ledger_folder_id = folder_id
    if folder_id:
        archive_tree = _ensure_archive_tree_sync(drive, folder_id)
        ledger_folder_id = archive_tree["REGISTRO DATI"]["id"]
    if not spreadsheet_id and folder_id:
        escaped_title = _escape_drive_query(WORKBOOK_TITLE)
        found = []
        # Compatibilita': prima il file poteva essere creato direttamente
        # nella radice; i nuovi registri vivono in REGISTRO DATI.
        for parent_id in dict.fromkeys((ledger_folder_id, folder_id)):
            found.extend(drive.files().list(
                q=(f"name='{escaped_title}' and '{parent_id}' in parents and "
                   "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"),
                fields="files(id,name,webViewLink,parents)", pageSize=2,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute().get("files", []))
        found = list({item["id"]: item for item in found}.values())
        if len(found) > 1:
            raise RuntimeError("Piu registri con lo stesso nome nella cartella Drive")
        if found:
            spreadsheet_id = found[0]["id"]
    if not spreadsheet_id:
        if ledger_folder_id:
            # Un service account non dispone di quota Drive propria. Creare
            # prima il foglio nella sua radice con Sheets API fallisce con
            # PERMISSION_DENIED anche se la cartella aziendale e' condivisa.
            # Drive API crea invece il file direttamente nella cartella
            # autorizzata, mantenendo proprieta' e spazio sul Drive aziendale.
            created = drive.files().create(
                body={
                    "name": WORKBOOK_TITLE,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [ledger_folder_id],
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
        "ledger_folder_id": ledger_folder_id or "",
        "archive_tree": {
            name: {
                "id": item.get("id"), "name": item.get("name"),
                "url": item.get("webViewLink"),
            }
            for name, item in archive_tree.items()
        },
        "sheet_definitions": requested_sheets,
    }


async def ensure_workbook(
    config: Optional[Dict[str, Any]] = None,
    collections: Iterable[str] = (),
) -> Dict[str, Any]:
    return await asyncio.to_thread(_ensure_workbook_sync, config, tuple(collections))


def _ensure_collection_sheet_sync(
    spreadsheet_id: str, collection: str,
) -> LedgerSheet:
    """Crea in modo idempotente il foglio Drive per una collezione operativa.

    Il codice storico accede a collezioni tecniche e di dominio anche fuori dal
    manifest iniziale (alert, audit, partite aperte, magazzino). In backend
    In Sheets questi registri non devono bloccare un import: al primo tentativo
    di scrittura ricevono un foglio ``DB_*``.
    """
    sheet = dynamic_sheet(collection)
    sheets = _sheets_service()
    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties",
    ).execute()
    existing = {
        item["properties"]["title"]
        for item in metadata.get("sheets", [])
        if item.get("properties", {}).get("title")
    }
    if sheet.title not in existing:
        try:
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {
                    "title": sheet.title,
                    "gridProperties": {
                        "frozenRowCount": 1,
                        "columnCount": len(HEADERS),
                    },
                }}}]},
            ).execute()
        except Exception:
            # Due scritture concorrenti possono tentare lo stesso addSheet.
            # Accettiamo l'errore soltanto se il foglio ora esiste davvero.
            refreshed = sheets.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties.title",
            ).execute()
            refreshed_titles = {
                item["properties"]["title"]
                for item in refreshed.get("sheets", [])
                if item.get("properties", {}).get("title")
            }
            if sheet.title not in refreshed_titles:
                raise
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet.title}'!A1:{LAST_COLUMN}1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()
    return sheet


async def ensure_collection_sheet(
    spreadsheet_id: str, collection: str,
) -> LedgerSheet:
    return await asyncio.to_thread(
        _ensure_collection_sheet_sync, spreadsheet_id, collection,
    )


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


def _drive_folder_duplicate_audit_sync(folder_ids: Iterable[str]) -> Dict[str, Any]:
    _, drive = _services()
    mime_folder = "application/vnd.google-apps.folder"
    queue = [(str(folder_id).strip(), str(folder_id).strip()) for folder_id in folder_ids if str(folder_id).strip()]
    visited = set()
    files: List[Dict[str, Any]] = []
    errors = []
    roots = []
    while queue:
        folder_id, root_id = queue.pop(0)
        if folder_id in visited:
            continue
        visited.add(folder_id)
        try:
            if folder_id == root_id:
                meta = drive.files().get(
                    fileId=folder_id, fields="id,name,mimeType,webViewLink",
                    supportsAllDrives=True,
                ).execute()
                roots.append(meta)
            page_token = None
            while True:
                response = drive.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,createdTime,modifiedTime,webViewLink,parents,capabilities(canTrash))",
                    pageSize=1000, pageToken=page_token,
                    supportsAllDrives=True, includeItemsFromAllDrives=True,
                ).execute()
                for item in response.get("files", []):
                    if item.get("mimeType") == mime_folder:
                        queue.append((item["id"], root_id))
                    else:
                        item["radice_id"] = root_id
                        item["cartella_id"] = folder_id
                        files.append(item)
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except Exception as exc:
            errors.append({"folder_id": folder_id, "radice_id": root_id, "errore": str(exc)})

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in files:
        checksum = str(item.get("md5Checksum") or "").strip()
        size = str(item.get("size") or "")
        method = "md5" if checksum else "nome_dimensione"
        key = f"hash:{checksum}" if checksum else f"name-size:{item.get('name', '').casefold()}:{size}"
        groups.setdefault(key, []).append({**item, "metodo": method})
    duplicates = [
        {"chiave": key, "metodo": items[0]["metodo"], "file": items}
        for key, items in groups.items() if len(items) > 1
    ]
    duplicates.sort(key=lambda group: (-len(group["file"]), group["chiave"]))
    return {
        "radici_richieste": len(set(str(value).strip() for value in folder_ids if str(value).strip())),
        "radici_accessibili": roots,
        "cartelle_visitate": len(visited),
        "totale_file": len(files),
        "gruppi_duplicati": len(duplicates),
        "file_duplicati_eccedenti": sum(len(group["file"]) - 1 for group in duplicates),
        "spazio_recuperabile_bytes": sum(
            int(item.get("size") or 0) for group in duplicates for item in group["file"][1:]
        ),
        "duplicati": duplicates,
        "errori": errors,
    }


async def drive_folder_duplicate_audit(folder_ids: Iterable[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_drive_folder_duplicate_audit_sync, tuple(folder_ids))


def _canonical_duplicate_key(item: Dict[str, Any]) -> tuple:
    """Preferisce un nome originale, poi la copia creata per prima."""
    import re
    name = str(item.get("name") or "")
    stem = name.rsplit(".", 1)[0]
    copy_marker = bool(re.search(r"(?:\bcopia\b|\bcopy\b|\(\d+\)\s*$)", stem, re.IGNORECASE))
    return (copy_marker, len(name), str(item.get("createdTime") or "9999"), str(item.get("id") or ""))


def _trash_exact_duplicates_sync(folder_ids: Iterable[str], apply: bool = False) -> Dict[str, Any]:
    audit = _drive_folder_duplicate_audit_sync(tuple(folder_ids))
    drive = _drive_cleanup_service() if apply else None
    selected = []
    skipped_no_permission = []
    groups_processed = 0
    for group in audit.get("duplicati", []):
        if group.get("metodo") != "md5":
            continue
        files = sorted(group.get("file") or [], key=_canonical_duplicate_key)
        if len(files) < 2:
            continue
        groups_processed += 1
        canonical = files[0]
        for duplicate in files[1:]:
            row = {
                "file_id": duplicate.get("id"),
                "nome": duplicate.get("name"),
                "radice_id": duplicate.get("radice_id"),
                "cartella_id": duplicate.get("cartella_id"),
                "canonical_id": canonical.get("id"),
                "canonical_nome": canonical.get("name"),
                "md5": duplicate.get("md5Checksum"),
            }
            if not duplicate.get("capabilities", {}).get("canTrash"):
                skipped_no_permission.append(row)
                continue
            if apply:
                drive.files().update(
                    fileId=duplicate["id"], body={"trashed": True},
                    supportsAllDrives=True, fields="id,trashed",
                ).execute()
            selected.append(row)
    return {
        "applicato": apply,
        "radici_richieste": audit.get("radici_richieste", 0),
        "gruppi_md5": groups_processed,
        "copie_selezionate": len(selected),
        "copie_senza_permesso": len(skipped_no_permission),
        "spostate_nel_cestino": len(selected) if apply else 0,
        "anteprima": selected[:100],
        "senza_permesso": skipped_no_permission[:100],
    }


async def trash_exact_duplicates(folder_ids: Iterable[str], apply: bool = False) -> Dict[str, Any]:
    return await asyncio.to_thread(_trash_exact_duplicates_sync, tuple(folder_ids), apply)


def _read_existing_sync(spreadsheet_id: str, sheet: LedgerSheet):
    sheets = _sheets_service()
    values = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{sheet.title}'!A2:{LAST_COLUMN}",
    ).execute().get("values", [])
    return values


def _read_identities_sync(spreadsheet_id: str, sheet: LedgerSheet):
    sheets = _sheets_service()
    return sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{sheet.title}'!A2:B",
    ).execute().get("values", [])


def _upsert_documents_sync(
    spreadsheet_id: str, sheet: LedgerSheet, documents: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggiorna soltanto le righe mutate senza riscrivere l'intero foglio.

    Il vecchio write-through rileggeva e riscriveva tutta la collezione a ogni
    singola insert/update. Durante l'import XML una fattura genera piu'
    mutazioni collegate e il processo Render da 512 MiB poteva essere
    riavviato. Qui si legge soltanto l'indice A:B e si scrivono le righe
    effettivamente cambiate.
    """
    identities = _read_identities_sync(spreadsheet_id, sheet)
    rows_by_id: Dict[str, tuple[str, int]] = {}
    progressives: List[str] = []
    for row_number, row in enumerate(identities, start=2):
        progressive = str(row[0] if row else "").strip()
        key = str(row[1] if len(row) > 1 else "").strip()
        if not progressive and not key:
            continue
        if not progressive or not key:
            raise RuntimeError(f"Progressivo o canonical_id mancante nel foglio {sheet.title}")
        if key in rows_by_id:
            raise RuntimeError(f"canonical_id duplicato nel foglio {sheet.title}: {key}")
        rows_by_id[key] = (progressive, row_number)
        progressives.append(progressive)

    sequence = next_progressive(sheet.prefix, progressives)
    pending: Dict[str, Dict[str, Any]] = {}
    fingerprints: Dict[str, str] = {}
    for raw in documents:
        document = portable_document(raw)
        key = canonical_id(document)
        if not key:
            raise ValueError(f"Documento senza chiave canonica per {sheet.collection}")
        fingerprint = document_fingerprint(document)
        previous = fingerprints.get(key)
        if previous is not None and previous != fingerprint:
            raise RuntimeError(
                f"Identita canonica in conflitto in {sheet.collection}: {key}"
            )
        fingerprints[key] = fingerprint
        pending[key] = document

    sheets = _sheets_service()
    updates = []
    appended = []
    for key, document in pending.items():
        current = rows_by_id.get(key)
        if current:
            progressive, row_number = current
            updates.append({
                "range": f"'{sheet.title}'!A{row_number}:{LAST_COLUMN}{row_number}",
                "values": [row_for_document(document, progressive)],
            })
            continue
        progressive = format_progressive(sheet.prefix, sequence)
        sequence += 1
        appended.append(row_for_document(document, progressive))

    # Un export POS mensile contiene migliaia di operazioni. Il flush resta
    # atomico dal punto di vista della cache locale, ma le richieste HTTP a
    # Sheets devono restare abbastanza piccole da non saturare Render/proxy.
    write_batch_rows = 500
    for offset in range(0, len(updates), write_batch_rows):
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": updates[offset:offset + write_batch_rows],
            },
        ).execute()
    for offset in range(0, len(appended), write_batch_rows):
        sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet.title}'!A:{LAST_COLUMN}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": appended[offset:offset + write_batch_rows]},
        ).execute()
    return {
        "foglio": sheet.title,
        "collezione": sheet.collection,
        "aggiornate": len(updates),
        "aggiunte": len(appended),
    }


async def upsert_documents(
    sheet: LedgerSheet, spreadsheet_id: str, documents: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    portable = [portable_document(document) for document in documents]
    if not portable:
        return {
            "foglio": sheet.title, "collezione": sheet.collection,
            "aggiornate": 0, "aggiunte": 0,
        }
    return await asyncio.to_thread(
        _upsert_documents_sync, spreadsheet_id, sheet, portable,
    )


def _remove_documents_sync(
    spreadsheet_id: str, sheet: LedgerSheet, canonical_ids: Iterable[str],
) -> Dict[str, Any]:
    targets = {str(value).strip() for value in canonical_ids if str(value).strip()}
    if not targets:
        return {"foglio": sheet.title, "collezione": sheet.collection, "rimosse": 0}
    identities = _read_identities_sync(spreadsheet_id, sheet)
    ranges = [
        f"'{sheet.title}'!A{row_number}:{LAST_COLUMN}{row_number}"
        for row_number, row in enumerate(identities, start=2)
        if len(row) > 1 and str(row[1]).strip() in targets
    ]
    if ranges:
        _sheets_service().spreadsheets().values().batchClear(
            spreadsheetId=spreadsheet_id, body={"ranges": ranges},
        ).execute()
    return {
        "foglio": sheet.title,
        "collezione": sheet.collection,
        "rimosse": len(ranges),
    }


async def remove_documents(
    sheet: LedgerSheet, spreadsheet_id: str, canonical_ids: Iterable[str],
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _remove_documents_sync, spreadsheet_id, sheet, tuple(canonical_ids),
    )


def _clear_rows_sync(spreadsheet_id: str, sheet: LedgerSheet) -> None:
    sheets = _sheets_service()
    sheets.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet.title}'!A2:{LAST_COLUMN}", body={},
    ).execute()


def _ensure_row_capacity_sync(
    spreadsheet_id: str, sheet: LedgerSheet, required_rows: int,
) -> None:
    sheets = _sheets_service()
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
    sheets = _sheets_service()
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
    sheets = _sheets_service()
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
    sheets = _sheets_service()
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
    documents = [portable_document(document) for document in documents]
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
    exact_duplicates = 0
    source_fingerprints: Dict[str, str] = {}
    for document in documents:
        key = canonical_id(document)
        if not key:
            skipped_without_id += 1
            continue
        fingerprint = document_fingerprint(document)
        previous = source_fingerprints.get(key)
        if previous is not None:
            if previous == fingerprint:
                exact_duplicates += 1
                continue
            raise RuntimeError(
                f"Identita canonica in conflitto in {sheet.collection}: {key}"
            )
        source_fingerprints[key] = fingerprint
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
        "duplicati_esatti": exact_duplicates,
        "digest": collection_fingerprint(source_fingerprints.values()),
    }


async def sync_collection_streaming(db, sheet: LedgerSheet, spreadsheet_id: str) -> Dict[str, Any]:
    """Riscrive lo snapshot canonico, deduplicato e verificabile del foglio."""
    snapshot = await source_collection_snapshot(db, sheet.collection)
    if snapshot["numero_conflitti"]:
        conflict = snapshot["conflitti"][0]["canonical_id"]
        raise RuntimeError(
            f"Migrazione bloccata: {sheet.collection} contiene payload diversi "
            f"con lo stesso canonical_id {conflict}"
        )
    if snapshot["senza_id"]:
        raise RuntimeError(
            f"Migrazione bloccata: {sheet.collection} contiene "
            f"{snapshot['senza_id']} righe prive di identita"
        )
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
    await asyncio.to_thread(
        _ensure_row_capacity_sync, spreadsheet_id, sheet,
        max(snapshot["identita_uniche"] + 1, 2),
    )
    await asyncio.to_thread(_clear_rows_sync, spreadsheet_id, sheet)
    batch: List[List[Any]] = []
    written = 0
    seen: set[str] = set()
    cursor = db[sheet.collection].find({})
    async for raw in cursor:
        document = portable_document(raw)
        key = canonical_id(document)
        if not key or key in seen:
            continue
        seen.add(key)
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
        "righe": written,
        "righe_sorgente": snapshot["righe_sorgente"],
        "duplicati_esatti": snapshot["duplicati_esatti"],
        "senza_id": snapshot["senza_id"],
        "digest": snapshot["digest"],
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


async def registry_audit(db, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Confronta la cache ricostruita e il registro Drive senza modifiche."""
    verification = await restore_all(db, config, apply=False)
    by_collection = {
        item["collezione"]: item for item in verification.get("fogli", [])
    }
    checks = []
    audited_definitions = sheet_definitions(
        item.get("collezione") for item in verification.get("fogli", [])
    )
    for sheet in audited_definitions:
        source = await source_collection_snapshot(db, sheet.collection)
        verified = by_collection.get(sheet.collection, {})
        sheet_count = int(verified.get("valide") or 0)
        errors = int(verified.get("numero_errori") or 0)
        digest_equal = str(source.get("digest")) == str(verified.get("digest"))
        complete = (
            source["identita_uniche"] == sheet_count
            and errors == 0
            and source["numero_conflitti"] == 0
            and source["senza_id"] == 0
            and digest_equal
        )
        checks.append({
            "foglio": sheet.title,
            "collezione": sheet.collection,
            "sorgente": source["righe_sorgente"],
            "sorgente_unica": source["identita_uniche"],
            "drive": sheet_count,
            "errori": errors,
            "duplicati_esatti_sorgente": source["duplicati_esatti"],
            "conflitti_sorgente": source["numero_conflitti"],
            "senza_id_sorgente": source["senza_id"],
            "digest_sorgente": source["digest"],
            "digest_drive": verified.get("digest"),
            "digest_coincidente": digest_equal,
            "completo": complete,
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


def _execute_read_request(request_factory, *, max_attempts: int = 6):
    """Riprova le sole letture temporaneamente limitate da Google Sheets.

    Un riavvio non deve fallire per una finestra quota gia' consumata da un
    deploy precedente. Le scritture non passano da qui, quindi il retry non
    puo' duplicare dati.
    """
    delays = (2, 4, 8, 16, 30)
    for attempt in range(max_attempts):
        try:
            return request_factory().execute()
        except Exception as exc:
            status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
            if status not in {429, 500, 502, 503, 504} or attempt >= max_attempts - 1:
                raise
            time.sleep(delays[min(attempt, len(delays) - 1)])


def _existing_workbook_sync(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Valida un registro esistente senza creare cartelle, fogli o formati."""
    spreadsheet_id = _setting_value(config, "GOOGLE_SHEETS_LEDGER_ID")
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID non configurato")

    sheets = _sheets_service()
    metadata = _execute_read_request(lambda: sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="spreadsheetId,spreadsheetUrl,sheets.properties",
    ))
    titles = {
        item["properties"]["title"]
        for item in metadata.get("sheets", [])
        if item.get("properties", {}).get("title")
    }
    missing = [item.title for item in SHEETS if item.title not in titles]
    if missing:
        raise RuntimeError(
            "Registro Sheets incompleto; fogli mancanti: " + ", ".join(missing)
        )
    dynamic = [
        dynamic_sheet(title[3:]) for title in titles if title.startswith("DB_")
    ]
    definitions = sheet_definitions(
        [item.collection for item in SHEETS]
        + [item.collection for item in dynamic]
    )
    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": metadata.get("spreadsheetUrl")
        or f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        "folder_id": default_folder_id(config) or "",
        "ledger_folder_id": "",
        "archive_tree": {},
        "sheet_definitions": definitions,
    }


def _read_sheet_rows_batch_sync(
    spreadsheet_id: str, definitions: Iterable[LedgerSheet],
) -> List[List[List[Any]]]:
    """Legge tutti i fogli con un solo client e una sola richiesta HTTP."""
    definitions = tuple(definitions)
    sheets = _sheets_service()
    response = _execute_read_request(
        lambda: sheets.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=[f"'{sheet.title}'!A2:{LAST_COLUMN}" for sheet in definitions],
        ),
    )
    value_ranges = response.get("valueRanges", [])
    if len(value_ranges) != len(definitions):
        raise RuntimeError("Risposta Sheets incompleta durante l'idratazione")
    return [item.get("values", []) for item in value_ranges]


def _sheet_last_row_sync(spreadsheet_id: str, sheet: LedgerSheet) -> int:
    """Restituisce l'ultima riga usata leggendo soltanto l'indice A:B."""
    service = _sheets_service()
    response = _execute_read_request(
        lambda: service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet.title}'!A2:B",
        ),
    )
    rows = response.get("values", [])
    return len(rows) + 1


def _read_sheet_row_chunk_sync(
    spreadsheet_id: str,
    sheet: LedgerSheet,
    start_row: int,
    end_row: int,
) -> List[List[Any]]:
    service = _sheets_service()
    return _execute_read_request(
        lambda: service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet.title}'!A{start_row}:{LAST_COLUMN}{end_row}",
        ),
    ).get("values", [])


async def restore_all(
    db, config: Optional[Dict[str, Any]] = None, *, apply: bool = False,
    provision: bool = True,
) -> Dict[str, Any]:
    """Valida o ricostruisce le collezioni dal payload JSON dei fogli.

    Il default e' sempre dry-run. In modalita apply usa upsert sull'ID
    canonico e non cancella documenti presenti nel database.
    """
    if provision:
        workbook = await ensure_workbook(config)
    else:
        workbook = await asyncio.to_thread(_existing_workbook_sync, config)
    definitions = workbook.pop("sheet_definitions")
    results = []
    for sheet in definitions:
        # Il registro POS e' idratato direttamente nella cache SQLite: un
        # blocco piu' ampio resta a memoria limitata e mantiene l'intero avvio
        # sotto la quota Sheets di 60 letture al minuto.
        restore_chunk_rows = (
            2500 if sheet.collection == "pos_terminal_transactions" else 500
        )
        valid = 0
        errors: List[Dict[str, Any]] = []
        error_count = 0
        seen_progressive = set()
        seen_ids = set()
        fingerprints: List[str] = []
        table = db[sheet.collection] if apply else None
        can_bulk_hydrate = bool(
            apply
            and getattr(db, "loading", False)
            and hasattr(table, "hydrate_documents")
            and await table.estimated_document_count() == 0
        )

        def add_error(row_number: int, message: str) -> None:
            nonlocal error_count
            error_count += 1
            if len(errors) < 100:
                errors.append({"riga": row_number, "errore": message})

        async def process_rows(start_row: int, rows: List[List[Any]]) -> None:
            """Valida e idrata un solo blocco, poi ne consente il rilascio."""
            nonlocal valid
            pending_documents: List[tuple[Dict[str, Any], Dict[str, Any]]] = []
            for offset, row in enumerate(rows):
                index = start_row + offset
                if len(row) < len(HEADERS):
                    row = list(row) + [""] * (len(HEADERS) - len(row))
                progressive = str(row[0] or "").strip()
                key = str(row[1] or "").strip()
                try:
                    payload = decode_payload("".join(str(part or "") for part in row[15:]))
                except (ValueError, json.JSONDecodeError, gzip.BadGzipFile, binascii.Error) as exc:
                    add_error(index, f"payload_json non valido: {exc}")
                    continue
                if not progressive or not key or not isinstance(payload, dict):
                    add_error(index, "progressivo, canonical_id o payload mancanti")
                    continue
                if progressive in seen_progressive or key in seen_ids:
                    add_error(index, "progressivo o canonical_id duplicato")
                    continue
                seen_progressive.add(progressive)
                seen_ids.add(key)
                if canonical_id(payload) != key:
                    add_error(index, "canonical_id diverso dal payload")
                    continue
                valid += 1
                fingerprints.append(document_fingerprint(payload))
                if apply:
                    storage_payload = dict(payload)
                    record_id = storage_payload.pop("_record_id", None)
                    if record_id not in (None, ""):
                        storage_payload["_id"] = str(record_id)
                        identity_filter = {"_id": str(record_id)}
                    else:
                        identity_filter = canonical_filter(storage_payload)
                    pending_documents.append((identity_filter, storage_payload))
            if apply and pending_documents:
                if can_bulk_hydrate:
                    await table.hydrate_documents(
                        (payload for _identity, payload in pending_documents),
                        copy_documents=False,
                        append=True,
                    )
                else:
                    for identity_filter, storage_payload in pending_documents:
                        await table.replace_one(
                            identity_filter, storage_payload, upsert=True,
                        )

        if provision:
            rows = await asyncio.to_thread(
                _read_sheet_rows_sync, workbook["spreadsheet_id"], sheet,
            )
            await process_rows(2, rows)
        else:
            # Legge solo l'indice per trovare il limite, poi idrata a blocchi.
            # Il registro POS usa blocchi maggiori sulla cache SQLite; gli
            # altri fogli mantengono blocchi piccoli nella cache Python.
            last_row = await asyncio.to_thread(
                _sheet_last_row_sync, workbook["spreadsheet_id"], sheet,
            )
            for start_row in range(2, last_row + 1, restore_chunk_rows):
                end_row = min(last_row, start_row + restore_chunk_rows - 1)
                rows = await asyncio.to_thread(
                    _read_sheet_row_chunk_sync,
                    workbook["spreadsheet_id"], sheet, start_row, end_row,
                )
                await process_rows(start_row, rows)
        results.append({
            "foglio": sheet.title, "collezione": sheet.collection,
            "prefisso": sheet.prefix,
            "valide": valid, "errori": errors, "numero_errori": error_count,
            "digest": collection_fingerprint(fingerprints),
        })
    return {
        **workbook, "apply": apply, "schema_version": SCHEMA_VERSION,
        "fogli": results,
    }
