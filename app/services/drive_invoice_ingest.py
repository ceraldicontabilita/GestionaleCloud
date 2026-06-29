"""
Ingest fatture XML da Google Drive.

Legge i file `.xml` da una cartella Drive configurata, li importa con la
pipeline CONDIVISA `process_xml_bytes` (riuso, niente duplicazione) e sposta i
file elaborati in una sottocartella `Elaborate`.

Configurazione (env / settings):
  GOOGLE_DRIVE_FATTURE_FOLDER_ID : id della cartella Drive sorgente
  GOOGLE_DRIVE_SA_FILE           : path al JSON del service account, oppure
  GOOGLE_DRIVE_SA_JSON           : il JSON del service account inline

Se non configurato, `get_status` lo segnala e `sync` è un no-op.
"""
import io
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_ELABORATE_FOLDER_NAME = "Elaborate"
_SYNC_STATE_COLLECTION = "drive_sync_state"
_SYNC_STATE_ID = "fatture_drive"


def is_configured() -> bool:
    return bool(
        settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID
        and (settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON)
    )


def _build_drive_service():
    """Costruisce il client Drive v3 da service account. None se non disponibile."""
    if not is_configured():
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        logger.error(f"Drive ingest: dipendenze google mancanti: {e}")
        return None
    try:
        if settings.GOOGLE_DRIVE_SA_JSON:
            info = json.loads(settings.GOOGLE_DRIVE_SA_JSON)
            creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        else:
            creds = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_DRIVE_SA_FILE, scopes=_SCOPES
            )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive ingest: errore costruzione service: {e}")
        return None


def _get_or_create_elaborate_folder(service, parent_id: str) -> Optional[str]:
    q = (
        f"name = '{_ELABORATE_FOLDER_NAME}' and '{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(
        q=q, fields="files(id)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": _ELABORATE_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return folder.get("id")


def _list_xml_files(service, parent_id: str) -> List[Dict[str, Any]]:
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.xml' or name contains '.XML')"
    )
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q, fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        for f in res.get("files", []):
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if f["name"].lower().endswith(".xml"):
                out.append(f)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def _download_bytes(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _move_to_elaborate(service, file_id: str, parent_id: str, elaborate_id: str):
    service.files().update(
        fileId=file_id, addParents=elaborate_id, removeParents=parent_id,
        fields="id, parents", supportsAllDrives=True,
    ).execute()


async def get_status(db) -> Dict[str, Any]:
    state = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
    return {
        "configured": is_configured(),
        "folder_id": settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID,
        "last_sync": state.get("last_sync"),
        "last_result": state.get("last_result"),
        "total_imported": state.get("total_imported", 0),
    }


async def sync(db) -> Dict[str, Any]:
    if not is_configured():
        return {
            "status": "not_configured",
            "message": "Imposta GOOGLE_DRIVE_FATTURE_FOLDER_ID e il service account "
                       "(GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile (credenziali?)."}

    # Import locale per evitare import circolari con il router.
    from app.routers.invoices.fatture_upload import process_xml_bytes

    parent_id = settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID
    result = {
        "status": "ok", "total": 0, "imported": 0, "duplicates": 0,
        "errors": 0, "moved": 0, "details": [],
    }
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        xml_files = _list_xml_files(service, parent_id)
        result["total"] = len(xml_files)
        for f in xml_files:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                res = await process_xml_bytes(db, content, fname, source="google_drive")
                st = res.get("status")
                if st == "imported":
                    result["imported"] += 1
                elif st == "duplicate":
                    result["duplicates"] += 1
                else:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": res.get("error")})
                    continue  # non spostare i file in errore: restano per il retry
                # Sposta in `Elaborate` i file processati (importati o duplicati noti).
                if elaborate_id:
                    _move_to_elaborate(service, fid, parent_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive ingest: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
    except Exception as e:
        logger.error(f"Drive ingest: errore sync: {e}")
        return {"status": "error", "message": str(e)}

    prev = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
    await db[_SYNC_STATE_COLLECTION].update_one(
        {"_id": _SYNC_STATE_ID},
        {"$set": {
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "last_result": {k: result[k] for k in ("total", "imported", "duplicates", "errors", "moved")},
            "total_imported": prev.get("total_imported", 0) + result["imported"],
        }},
        upsert=True,
    )
    return result
