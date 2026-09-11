"""Copia non distruttiva degli allegati nelle cartelle Drive canoniche.

La destinazione non dipende dal canale: Gmail e upload manuale usano lo stesso
registro documentale. Nessun ID Drive e' hardcoded qui.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Any, Iterable

from app.config import settings
from app.services.document_destination_registry import destination_for_document_type
from app.services.drive_folder_registry import get_folder_id, get_generic_documents_folder_id

logger = logging.getLogger(__name__)


def route_for_document_type(tipo: str):
    """Compatibilita' pubblica: restituisce la destinazione canonica."""
    return destination_for_document_type(tipo)


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
    # Loader condiviso: stesse credenziali degli ingest Drive del gestionale.
    from app.services.drive_cedolini_ingest import _load_credentials_cedolini

    creds, error = _load_credentials_cedolini()
    if creds is None:
        logger.warning("Archivio documentale Drive non disponibile: %s", error)
        return None
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _get_or_create_folder(service, parent_id: str, name: str) -> str:
    escaped = _escape_query(name)
    result = service.files().list(
        q=(
            f"name = '{escaped}' and '{parent_id}' in parents and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        ),
        fields="files(id)",
        pageSize=2,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = result.get("files", [])
    if files:
        return files[0]["id"]
    created = service.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def _find_child_folder(service, parent_id: str, names: Iterable[str]) -> str | None:
    """Restituisce una sottocartella esistente, senza crearla per supposizione."""
    for name in names:
        escaped = _escape_query(name)
        result = service.files().list(
            q=(
                f"name = '{escaped}' and '{parent_id}' in parents and "
                "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            ),
            fields="files(id)",
            pageSize=2,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = result.get("files", [])
        if files:
            return files[0]["id"]
    return None


def _find_sibling_folder(service, configured_folder_id: str, sibling_name: str) -> str | None:
    """Trova una cartella sorella usando il parent reale osservato su Drive.

    Esempio: partendo da VERBALI_AUTO trova PAGAMENTI_E_BOLLETTINI_VERBALI,
    senza conoscere o codificare l'ID di 09_VERBALI_PAGOPA.
    """
    metadata = service.files().get(
        fileId=configured_folder_id,
        fields="id,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    if metadata.get("trashed"):
        return None
    for parent_id in metadata.get("parents") or []:
        found = _find_child_folder(service, parent_id, (sibling_name,))
        if found:
            return found
    return None


def _already_archived(service, parent_id: str, filename: str, sha256: str) -> bool:
    result = service.files().list(
        q=f"name = '{_escape_query(filename)}' and '{parent_id}' in parents and trashed = false",
        fields="files(id,appProperties)",
        pageSize=20,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return any(
        (item.get("appProperties") or {}).get("gestionale_sha256") == sha256
        for item in result.get("files", [])
    )


def archive_document_copy(doc: dict[str, Any], tipo: str) -> dict[str, Any]:
    """Archivia una copia nell'unica destinazione Drive canonica.

    Non elimina, non sposta e non altera la sorgente. Le cartelle speciali
    sorelle vengono solo risolte se esistono gia'; in caso contrario il flusso
    fallisce chiuso con ``not_configured`` invece di inventare una struttura.
    """
    destination = destination_for_document_type(tipo)
    if destination is None:
        return {"status": "ignored", "reason": "tipo_non_rilevante"}

    folder_id = get_folder_id(destination.area)
    service = None
    if not folder_id:
        ledger_root = str(settings.GOOGLE_SHEETS_LEDGER_FOLDER_ID or "").strip()
        root_id = get_generic_documents_folder_id() or ledger_root
        if not root_id:
            return {"status": "not_configured", "area": destination.area}
        service = _drive_service()
        if service is None:
            return {"status": "not_configured", "area": destination.area}
        folder_id = _get_or_create_folder(service, root_id, destination.label)

    content = _decode_content(doc)
    if not content:
        return {"status": "error", "area": destination.area, "reason": "contenuto_mancante"}

    service = service or _drive_service()
    if service is None:
        return {"status": "not_configured", "area": destination.area}

    if destination.sibling_name:
        sibling = _find_sibling_folder(service, folder_id, destination.sibling_name)
        if not sibling:
            return {
                "status": "not_configured",
                "area": destination.area,
                "reason": f"cartella_sorella_non_trovata:{destination.sibling_name}",
            }
        folder_id = sibling

    if destination.processed_child:
        # Le strutture reali usano sia ELABORATE sia Elaborate. Non creiamo la
        # cartella in automatico: se non esiste archiviamo nella radice canonica.
        processed = _find_child_folder(
            service,
            folder_id,
            (destination.processed_child, destination.processed_child.title(), "Elaborate"),
        )
        if processed:
            folder_id = processed

    filename = str(doc.get("filename") or f"documento-{doc.get('id', 'ingest')}.pdf").strip()
    digest = str(doc.get("sha256") or "").strip().lower() or hashlib.sha256(content).hexdigest()
    if _already_archived(service, folder_id, filename, digest):
        return {
            "status": "duplicate",
            "area": destination.area,
            "sha256": digest,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }

    from googleapiclient.http import MediaIoBaseUpload

    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    source = str(doc.get("source") or doc.get("fonte") or "documenti").strip()[:120]
    try:
        created = service.files().create(
            body={
                "name": filename,
                "parents": [folder_id],
                "appProperties": {
                    "gestionale_sha256": digest,
                    "gestionale_source": source,
                },
            },
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        status_code = getattr(getattr(exc, "resp", None), "status", None)
        message = str(exc).lower()
        if status_code == 403 and "storage quota" in message:
            return {
                "status": "blocked_owner_auth",
                "area": destination.area,
                "reason": "service_account_storage_quota",
            }
        if status_code == 403:
            return {
                "status": "blocked_owner_auth",
                "area": destination.area,
                "reason": "drive_permission_denied",
            }
        raise

    return {
        "status": "archived",
        "area": destination.area,
        "drive_file_id": created.get("id"),
        "drive_url": created.get("webViewLink"),
        "sha256": digest,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
