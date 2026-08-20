"""Copia non distruttiva degli allegati email rilevanti nelle cartelle Drive."""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Any

from app.services.drive_folder_registry import get_folder_id, get_generic_documents_folder_id
from app.config import settings

logger = logging.getLogger(__name__)


_ROUTES: dict[str, tuple[str, str]] = {
    "f24": ("f24", "F24"),
    "quietanza": ("quietanze", "Quietanze F24"),
    "busta_paga": ("cedolini", "Cedolini"),
    "cedolino": ("cedolini", "Cedolini"),
    "cartella_esattoriale": ("cartelle_esattoriali", "Cartelle esattoriali"),
    "avviso_bonario": ("avvisi_bonari", "Avvisi bonari"),
    "verbale": ("verbali", "Verbali"),
    "dichiarazione_iva": ("dichiarazioni_iva", "Dichiarazioni IVA"),
    "estratto_conto": ("estratti_conto", "Estratti conto"),
    "bonifico": ("bonifici_dipendenti", "Bonifici"),
    "fattura": ("fatture", "Fatture"),
    "fattura_xml": ("fatture", "Fatture"),
    "fattura_estera_pdf": ("fatture", "Fatture estere"),
    "pagopa": ("pagopa", "PagoPA"),
    "contributi_inps": ("inps", "INPS"),
    "inps": ("inps", "INPS"),
    "inail": ("inail", "INAIL"),
    "certificazione_unica": ("certificazioni_uniche", "Certificazioni uniche"),
    "paypal": ("paypal", "PayPal"),
    "satispay": ("satispay", "Satispay"),
    "bolletta_energia": ("utenze_energia", "Bollette energia"),
    "partenopay": ("partenopay", "PARTENOPAY"),
}


def route_for_document_type(tipo: str) -> tuple[str, str] | None:
    return _ROUTES.get(str(tipo or "").strip().lower())


def _decode_content(doc: dict[str, Any]) -> bytes:
    content = doc.get("content")
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    encoded = doc.get("pdf_data")
    if encoded:
        return base64.b64decode(encoded)
    return b""


def _drive_service():
    # Il loader condiviso non dipende da una singola cartella e usa le stesse
    # credenziali gia' impiegate dagli ingest Drive del gestionale.
    from app.services.drive_cedolini_ingest import _load_credentials_cedolini
    creds, error = _load_credentials_cedolini()
    if creds is None:
        logger.warning("Archivio email Drive non disponibile: %s", error)
        return None
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _get_or_create_folder(service, parent_id: str, name: str) -> str:
    escaped = _escape_query(name)
    result = service.files().list(
        q=(f"name = '{escaped}' and '{parent_id}' in parents and "
           "mimeType = 'application/vnd.google-apps.folder' and trashed = false"),
        fields="files(id)", pageSize=2, supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = result.get("files", [])
    if files:
        return files[0]["id"]
    created = service.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        fields="id", supportsAllDrives=True,
    ).execute()
    return created["id"]


def _find_child_folder(service, parent_id: str, name: str) -> str | None:
    """Restituisce una sottocartella esistente senza modificare Drive."""
    escaped = _escape_query(name)
    result = service.files().list(
        q=(f"name = '{escaped}' and '{parent_id}' in parents and "
           "mimeType = 'application/vnd.google-apps.folder' and trashed = false"),
        fields="files(id)", pageSize=2, supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _already_archived(service, parent_id: str, filename: str, digest: str) -> bool:
    result = service.files().list(
        q=f"name = '{_escape_query(filename)}' and '{parent_id}' in parents and trashed = false",
        fields="files(id, appProperties, md5Checksum)", pageSize=20, supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return any(
        (item.get("appProperties") or {}).get("gestionale_hash") == digest
        or item.get("md5Checksum") == digest
        for item in result.get("files", [])
    )


def archive_document_copy(doc: dict[str, Any], tipo: str) -> dict[str, Any]:
    """Archivia una copia; non elimina e non sposta mai il documento nell'app."""
    route = route_for_document_type(tipo)
    if route is None:
        return {"status": "ignored", "reason": "tipo_non_rilevante"}
    area, label = route
    folder_id = get_folder_id(area)
    service = None
    if not folder_id:
        ledger_root = str(settings.GOOGLE_SHEETS_LEDGER_FOLDER_ID or "").strip()
        root_id = ledger_root or get_generic_documents_folder_id()
        if area != "partenopay":
            root_id = get_generic_documents_folder_id() or ledger_root
        if not root_id:
            return {"status": "not_configured", "area": area}
        service = _drive_service()
        if service is None:
            return {"status": "not_configured", "area": area}
        folder_id = _get_or_create_folder(service, root_id, label)

    content = _decode_content(doc)
    if not content:
        return {"status": "error", "area": area, "reason": "contenuto_mancante"}
    service = service or _drive_service()
    if service is None:
        return {"status": "not_configured", "area": area}

    # Le aree documentali possono adottare il ciclo Da elaborare/Elaborate/
    # Errori. Le copie gia' processate dall'app vanno in Elaborate; se la
    # sottocartella non esiste si mantiene la compatibilita' con la radice.
    folder_id = _find_child_folder(service, folder_id, "Elaborate") or folder_id

    filename = str(doc.get("filename") or f"documento-{doc.get('id', 'email')}.pdf").strip()
    digest = str(doc.get("file_hash") or hashlib.md5(content).hexdigest())
    if _already_archived(service, folder_id, filename, digest):
        return {"status": "duplicate", "area": area, "archived_at": datetime.now(timezone.utc).isoformat()}

    from googleapiclient.http import MediaIoBaseUpload
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    try:
        service.files().create(
            body={
                "name": filename,
                "parents": [folder_id],
                "appProperties": {"gestionale_hash": digest, "gestionale_source": "email"},
            },
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        status_code = getattr(getattr(exc, "resp", None), "status", None)
        message = str(exc).lower()
        if status_code == 403 and "storage quota" in message:
            return {"status": "blocked_owner_auth", "area": area,
                    "reason": "service_account_storage_quota"}
        if status_code == 403:
            return {"status": "blocked_owner_auth", "area": area,
                    "reason": "drive_permission_denied"}
        raise
    return {"status": "archived", "area": area, "archived_at": datetime.now(timezone.utc).isoformat()}
