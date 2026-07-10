"""
Ingest corrispettivi RT (XML) da Google Drive.

Legge i file XML del registratore telematico dalla cartella Drive
configurata e li processa con la pipeline UNICA dei corrispettivi
(CorrispettiviService.process_xml: parsing, dedup per hash contenuto e
per data, prima nota). I file elaborati (importati o duplicati noti)
vengono spostati nella sottocartella Drive `Elaborate`.

Prima questo canale esisteva solo sulla carta (LOGICA §2 lo dichiarava
attivo ma nessun codice leggeva la cartella): i corrispettivi entravano
solo da import manuale.

Configurazione (env / settings):
  GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID : id della cartella Drive
  GOOGLE_DRIVE_SA_FILE / GOOGLE_DRIVE_SA_JSON : service account (condiviso)

Helper Drive riusati da drive_invoice_ingest (stesso service account,
stessa gestione Elaborate). Stato sync in sistema_stato, chiave dedicata.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.config import settings
from app.services.drive_invoice_ingest import (
    _load_credentials,
    _get_or_create_elaborate_folder,
    _download_bytes,
    _move_to_elaborate,
)

logger = logging.getLogger(__name__)

_STATO_KEY = "drive_corrispettivi_last_sync"

_sync_lock = asyncio.Lock()
_bg_task: Optional[asyncio.Task] = None


def is_sync_running() -> bool:
    return _sync_lock.locked()


def start_background_sync(db) -> bool:
    """Avvia un sync in background. Ritorna False se ce n'è già uno in corso."""
    global _bg_task
    if _sync_lock.locked():
        return False
    _bg_task = asyncio.create_task(sync(db))
    return True


def is_configured() -> bool:
    return bool(
        settings.GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID
        and (settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON)
    )


def is_corrispettivo_filename(name: str) -> bool:
    """Nella cartella corrispettivi si lavorano solo gli XML del RT."""
    return bool(name) and name.lower().endswith(".xml")


def _build_drive_service():
    if not is_configured():
        return None
    creds, err = _load_credentials()
    if creds is None:
        logger.error(f"Drive corrispettivi: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive corrispettivi: errore costruzione service: {e}")
        return None


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
            if is_corrispettivo_filename(f["name"]):
                out.append(f)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


async def get_status(db) -> Dict[str, Any]:
    state = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials()
    return {
        "configured": is_configured(),
        "credenziali_ok": is_configured() and credenziali_errore is None,
        "credenziali_errore": credenziali_errore,
        "folder_id": settings.GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID,
        "sync_running": is_sync_running(),
        "last_sync": state.get("valore"),
        "last_result": state.get("last_result"),
        "last_error": state.get("last_error"),
        "total_imported": state.get("total_imported", 0),
    }


async def sync(db) -> Dict[str, Any]:
    """Esegue un ciclo di import. Se un sync è già in corso, non fa nulla."""
    if _sync_lock.locked():
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    async with _sync_lock:
        return await _do_sync(db)


async def _do_sync(db) -> Dict[str, Any]:
    if not is_configured():
        return {
            "status": "not_configured",
            "message": "Imposta GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID e il service "
                       "account (GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile."}

    from app.services.corrispettivi_service import get_corrispettivi_service
    corr_service = get_corrispettivi_service()

    parent_id = settings.GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID
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
                if not content:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": "file vuoto"})
                    continue  # non spostare: resta per il retry
                # Pipeline UNICA corrispettivi: dedup per hash e per data
                # sono già dentro process_xml — nessun doppione possibile.
                esito = await corr_service.process_xml(content, fname)
                stato = esito.get("status")
                if stato == "duplicate":
                    result["duplicates"] += 1
                elif stato == "error":
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": esito.get("message")})
                    continue  # file in errore: resta per il retry, non si sposta
                else:
                    result["imported"] += 1
                    logger.info(f"Drive corrispettivi: importato {fname}")
                # Sposta in `Elaborate` i file processati (importati/duplicati)
                if elaborate_id:
                    _move_to_elaborate(service, fid, parent_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive corrispettivi: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
    except Exception as e:
        logger.error(f"Drive corrispettivi: errore sync: {e}")
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_error": str(e), "updated_at": now}},
            upsert=True,
        )
        return {"status": "error", "message": str(e)}

    prev = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    last_result = {k: result[k] for k in ("total", "imported", "duplicates", "errors", "moved")}
    last_result["details"] = result["details"][:5]
    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {"$set": {
            "valore": now,
            "last_result": last_result,
            "last_error": None,
            "total_imported": prev.get("total_imported", 0) + result["imported"],
            "updated_at": now,
        }},
        upsert=True,
    )
    return result
