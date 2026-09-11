"""Ingest dei MODELLI F24 dalla cartella Drive canonica.

Adattatore sottile verso ``f24_canonico.importa_modello_bytes``: nessun parser
parallelo e nessuna prova di pagamento inventata. Un modello acquisito resta
``da_pagare`` / non riconciliato finche' non esiste evidenza di pagamento.

Struttura Drive supportata e verificata:
    F24/
      DA ELABORARE/
      ELABORATE/
      ERRORI/

Le cartelle laterali (es. modelli da confermare o da verificare) non vengono
scandite automaticamente.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.drive_invoice_ingest import (
    _close_drive_service,
    _download_bytes,
    _get_or_create_elaborate_folder,
    _get_or_create_error_folder,
    _get_or_create_inbox_folder,
    _load_credentials,
    _move_to_folder,
    _move_to_elaborate,
)
from app.services.drive_lifecycle_tree import (
    discover_lifecycle_folders,
    resolve_inboxes_or_legacy,
)

logger = logging.getLogger(__name__)

_STATO_KEY = "drive_f24_last_sync"
_sync_lock = asyncio.Lock()
_bg_task: Optional[asyncio.Task] = None


def _folder_id() -> Optional[str]:
    return settings.DRIVE_F24_FOLDER_ID


def is_configured() -> bool:
    return bool(
        _folder_id()
        and (
            settings.GOOGLE_DRIVE_SA_FILE
            or settings.GOOGLE_DRIVE_SA_JSON
            or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
        )
    )


def is_sync_running() -> bool:
    return _sync_lock.locked()


def start_background_sync(db) -> bool:
    global _bg_task
    if _sync_lock.locked():
        return False
    _bg_task = asyncio.create_task(sync(db))
    return True


def is_f24_filename(name: str) -> bool:
    return bool(name) and name.lower().endswith(".pdf")


def _build_drive_service():
    if not is_configured():
        return None
    creds, error = _load_credentials()
    if creds is None:
        logger.error("Drive F24: %s", error)
        return None
    try:
        from googleapiclient.discovery import build

        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.error("Drive F24: errore costruzione service: %s", exc)
        return None


def _list_pdf_files(service, parent_id: str) -> List[Dict[str, Any]]:
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.pdf' or name contains '.PDF')"
    )
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        response = service.files().list(
            q=q,
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for item in response.get("files", []):
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if is_f24_filename(item.get("name") or ""):
                out.append(item)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return out


def _resolve_state_folder(service, parent_id: str, state: str) -> Optional[str]:
    existing = discover_lifecycle_folders(
        service, parent_id, max_depth=1, states=(state,)
    )
    for item in existing:
        if item.get("lifecycle_parent_id") == parent_id:
            return item.get("folder_id")
    if state == "elaborate":
        return _get_or_create_elaborate_folder(service, parent_id)
    if state == "error":
        return _get_or_create_error_folder(service, parent_id)
    raise ValueError(f"Stato lifecycle non supportato: {state}")


async def get_status(db) -> Dict[str, Any]:
    state = await db["sistema_stato"].find_one(
        {"chiave": _STATO_KEY}, {"_id": 0}
    ) or {}
    return {
        "configured": is_configured(),
        "folder_id": _folder_id(),
        "sync_running": is_sync_running(),
        "last_sync": state.get("valore"),
        "last_result": state.get("last_result"),
        "last_error": state.get("last_error"),
        "total_imported": state.get("total_imported", 0),
    }


async def sync(db) -> Dict[str, Any]:
    if _sync_lock.locked():
        return {"status": "running", "message": "Sincronizzazione gia' in corso"}
    async with _sync_lock:
        return await _do_sync(db)


async def _do_sync(db) -> Dict[str, Any]:
    if not is_configured():
        return {
            "status": "not_configured",
            "message": "Imposta DRIVE_F24_FOLDER_ID e il service account Drive.",
        }
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    from app.services.f24_canonico import importa_modello_bytes

    result: Dict[str, Any] = {
        "status": "ok",
        "total": 0,
        "imported": 0,
        "duplicates": 0,
        "errors": 0,
        "moved": 0,
        "inboxes": 0,
        "details": [],
    }
    root_id = _folder_id()
    try:
        inboxes = resolve_inboxes_or_legacy(
            service,
            root_id,
            _get_or_create_inbox_folder,
            max_depth=1,
        )
        result["inboxes"] = len(inboxes)

        for inbox in inboxes:
            source_id = inbox["inbox_id"]
            lifecycle_parent_id = inbox["lifecycle_parent_id"]
            relative_inbox = inbox.get("relative_path") or "DA ELABORARE"
            elaborate_id = _resolve_state_folder(
                service, lifecycle_parent_id, "elaborate"
            )
            error_id = _resolve_state_folder(service, lifecycle_parent_id, "error")
            pdf_files = _list_pdf_files(service, source_id)
            result["total"] += len(pdf_files)

            for file_info in pdf_files:
                fid = file_info["id"]
                fname = file_info["name"]
                source_path = f"{relative_inbox}/{fname}"
                try:
                    content = _download_bytes(service, fid)
                    if not content:
                        raise ValueError("file vuoto")

                    outcome = await importa_modello_bytes(
                        db,
                        content,
                        fname,
                        source="drive_f24",
                    )
                    if not outcome.get("success"):
                        result["errors"] += 1
                        result["details"].append({
                            "source_path": source_path,
                            "error": outcome.get("error") or "Import F24 fallito",
                            "validazione": outcome.get("validazione"),
                        })
                        if error_id:
                            _move_to_folder(service, fid, source_id, error_id)
                        continue

                    if outcome.get("duplicate"):
                        result["duplicates"] += 1
                    else:
                        result["imported"] += 1
                        try:
                            from app.services.event_bus import EventTypes, propagate_event

                            await propagate_event(
                                EventTypes.DOCUMENTO_ACQUISITO,
                                {
                                    "documento_id": outcome.get("f24_id"),
                                    "filename": fname,
                                    "origine": "drive_f24",
                                    "mime_type": "application/pdf",
                                    "category": "f24",
                                },
                                db,
                                source_module="drive_f24_ingest",
                            )
                        except Exception:
                            logger.exception(
                                "Drive F24: errore propagazione evento documento.acquisito"
                            )

                    if elaborate_id:
                        _move_to_elaborate(service, fid, source_id, elaborate_id)
                        result["moved"] += 1
                except Exception as exc:
                    logger.error("Drive F24: errore su %s: %s", source_path, exc)
                    result["errors"] += 1
                    result["details"].append({
                        "source_path": source_path,
                        "error": str(exc),
                    })
                    if error_id:
                        try:
                            _move_to_folder(service, fid, source_id, error_id)
                        except Exception:
                            logger.exception(
                                "Drive F24: impossibile spostare %s in Errori",
                                source_path,
                            )
    except Exception as exc:
        logger.exception("Drive F24: errore sync")
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_error": str(exc), "updated_at": now}},
            upsert=True,
        )
        return {"status": "error", "message": str(exc)}
    finally:
        _close_drive_service(service)

    previous = await db["sistema_stato"].find_one(
        {"chiave": _STATO_KEY}, {"_id": 0}
    ) or {}
    now = datetime.now(timezone.utc).isoformat()
    compact = {
        key: result[key]
        for key in (
            "total", "imported", "duplicates", "errors", "moved", "inboxes"
        )
    }
    compact["details"] = result["details"][:5]
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {
            "$set": {
                "valore": now,
                "last_result": compact,
                "last_error": None,
                "total_imported": previous.get("total_imported", 0)
                + result["imported"],
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return result


async def verifica_quadratura_elaborate(db) -> Dict[str, Any]:
    """Verifica che ogni PDF in ELABORATE esista nel registro canonico F24."""
    if not is_configured():
        return {"status": "not_configured"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    from app.services.f24_canonico import importa_modello_bytes

    result: Dict[str, Any] = {
        "status": "ok",
        "controllati": 0,
        "quadrati": 0,
        "recuperati": 0,
        "errori": 0,
        "details": [],
    }
    try:
        folders = discover_lifecycle_folders(
            service,
            _folder_id(),
            max_depth=1,
            states=("elaborate",),
        )
        if not folders:
            return {"status": "ok", "message": "Nessuna cartella Elaborate", **result}

        for folder in folders:
            for file_info in _list_pdf_files(service, folder["folder_id"]):
                result["controllati"] += 1
                try:
                    content = _download_bytes(service, file_info["id"])
                    outcome = await importa_modello_bytes(
                        db,
                        content,
                        file_info["name"],
                        source="drive_f24_quadratura",
                    )
                    if not outcome.get("success"):
                        result["errori"] += 1
                        result["details"].append({
                            "file": file_info["name"],
                            "error": outcome.get("error"),
                        })
                    elif outcome.get("duplicate"):
                        result["quadrati"] += 1
                    else:
                        result["recuperati"] += 1
                        result["details"].append({
                            "file": file_info["name"],
                            "recuperato": True,
                        })
                except Exception as exc:
                    result["errori"] += 1
                    result["details"].append({
                        "file": file_info["name"],
                        "error": str(exc),
                    })
        return result
    finally:
        _close_drive_service(service)
