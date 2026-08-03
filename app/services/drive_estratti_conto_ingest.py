"""Import automatico degli estratti conto CSV/XLSX dalla cartella Drive.

Usa esattamente l'endpoint/pipeline dell'import manuale, quindi deduplica,
riconciliazione, assegni e Prima Nota non possono divergere tra i due canali.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.drive_invoice_ingest import (
    _download_bytes,
    _get_or_create_inbox_folder,
    _get_or_create_elaborate_folder,
    _get_or_create_error_folder,
    _load_credentials,
    _move_to_folder,
    _move_to_elaborate,
)

logger = logging.getLogger(__name__)
_STATO_KEY = "drive_estratti_conto_last_sync"
_sync_lock = asyncio.Lock()


def _folder_id() -> Optional[str]:
    return (settings.GOOGLE_DRIVE_ESTRATTI_FOLDER_ID
            or settings.DRIVE_FOLDER_ESTRATTI_CONTO_ID
            or settings.DRIVE_ESTRATTI_CONTO_FOLDER_ID)


def _load_credentials_estratti():
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES
            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        except Exception as exc:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO non valido: {exc}"
    return _load_credentials()


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_ESTRATTI_CONTO_SYNC
        and _folder_id()
        and (settings.GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO
             or settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON
             or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON)
    )


def _build_drive_service():
    if not is_configured():
        return None
    creds, err = _load_credentials_estratti()
    if creds is None:
        logger.error("Drive estratti conto: %s", err)
        return None
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _list_files(service, parent_id: str) -> List[Dict[str, Any]]:
    query = f"'{parent_id}' in parents and trashed = false"
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        result = service.files().list(
            q=query, fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        for item in result.get("files", []):
            name = (item.get("name") or "").lower()
            if item.get("mimeType") != "application/vnd.google-apps.folder" and name.endswith((".csv", ".xlsx", ".xls", ".pdf")):
                out.append(item)
        page_token = result.get("nextPageToken")
        if not page_token:
            return out


class _UploadDrive:
    def __init__(self, name: str, content: bytes):
        self.filename = name
        self._content = content

    async def read(self) -> bytes:
        return self._content


async def sync(db) -> Dict[str, Any]:
    if _sync_lock.locked():
        return {"status": "running"}
    async with _sync_lock:
        if not is_configured():
            return {"status": "not_configured"}
        service = _build_drive_service()
        if service is None:
            return {"status": "error", "message": "Service Drive non disponibile"}

        from app.routers.bank.estratto_conto import import_estratto_conto

        parent_id = _folder_id()
        result: Dict[str, Any] = {
            "status": "ok", "total": 0, "processed": 0, "moved": 0,
            "new_movements": 0, "duplicates": 0, "cheques": 0, "errors": [],
        }
        inbox_id = _get_or_create_inbox_folder(service, parent_id)
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        error_id = _get_or_create_error_folder(service, parent_id)
        source_id = inbox_id or parent_id
        files = _list_files(service, source_id)
        result["total"] = len(files)
        for item in files:
            try:
                content = _download_bytes(service, item["id"])
                if not content:
                    raise ValueError("file vuoto")
                esito = await import_estratto_conto(_UploadDrive(item["name"], content))
                if isinstance(esito, dict) and (esito.get("error") or esito.get("detail")):
                    raise ValueError(esito.get("error") or esito.get("detail"))
                stats = (esito or {}).get("stats") or {}
                result["new_movements"] += int(stats.get("nuovi") or (esito or {}).get("movimenti_nuovi_importati") or 0)
                result["duplicates"] += int(stats.get("duplicati") or (esito or {}).get("duplicati_saltati") or 0)
                sync_assegni = (esito or {}).get("assegni_sync") or {}
                result["cheques"] += int(sync_assegni.get("assegni_creati") or 0)
                result["processed"] += 1
                if elaborate_id:
                    _move_to_elaborate(service, item["id"], source_id, elaborate_id)
                    result["moved"] += 1
            except Exception as exc:
                logger.exception("Drive estratti conto: errore su %s", item.get("name"))
                result["errors"].append({"file": item.get("name"), "error": str(exc)})
                if error_id:
                    try:
                        _move_to_folder(service, item["id"], source_id, error_id)
                    except Exception:
                        logger.exception("Drive estratti conto: impossibile spostare %s in Errori", item.get("name"))

        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_result": result, "updated_at": now}},
            upsert=True,
        )
        return result
