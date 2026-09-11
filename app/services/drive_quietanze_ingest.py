"""Ingest quietanze F24 (PDF) da Google Drive.

Legge soltanto i PDF presenti nella ``DA ELABORARE`` canonica della cartella
Quietanze, li passa al motore unico F24 e li sposta nel lifecycle fratello
``ELABORATE`` o ``ERRORI``. I nomi lifecycle vengono risolti senza distinzione
di maiuscole, cosi' la struttura reale ``DA ELABORARE / ELABORATE / ERRORI``
non genera copie parallele ``Da elaborare / Elaborate / Errori``.
"""
import asyncio
import hashlib
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

_STATO_KEY = "drive_quietanze_last_sync"
_sync_lock = asyncio.Lock()
_bg_task: Optional[asyncio.Task] = None


def is_sync_running() -> bool:
    return _sync_lock.locked()


def start_background_sync(db) -> bool:
    global _bg_task
    if _sync_lock.locked():
        return False
    _bg_task = asyncio.create_task(sync(db))
    return True


def _folder_id() -> Optional[str]:
    return settings.GOOGLE_DRIVE_QUIETANZE_FOLDER_ID


def _load_credentials_quietanze():
    """Account dedicato quietanze se presente, altrimenti account condiviso."""
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES

            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE)
            return service_account.Credentials.from_service_account_info(
                info, scopes=_SCOPES
            ), None
        except Exception as exc:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE non valido: {exc}"
    return _load_credentials()


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_QUIETANZE_SYNC
        and _folder_id()
        and (
            settings.GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE
            or settings.GOOGLE_DRIVE_SA_FILE
            or settings.GOOGLE_DRIVE_SA_JSON
            or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
        )
    )


def is_quietanza_filename(name: str) -> bool:
    return bool(name) and name.lower().endswith(".pdf")


def _build_drive_service():
    if not is_configured():
        return None
    creds, err = _load_credentials_quietanze()
    if creds is None:
        logger.error("Drive quietanze: %s", err)
        return None
    try:
        from googleapiclient.discovery import build

        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.error("Drive quietanze: errore costruzione service: %s", exc)
        return None


def _list_pdf_files(service, parent_id: str) -> List[Dict[str, Any]]:
    """PDF figli diretti della cartella lifecycle indicata."""
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.pdf' or name contains '.PDF')"
    )
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q,
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for item in res.get("files", []):
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if is_quietanza_filename(item.get("name") or ""):
                out.append(item)
        page_token = res.get("nextPageToken")
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
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials_quietanze()
    return {
        "configured": is_configured(),
        "credenziali_ok": is_configured() and credenziali_errore is None,
        "credenziali_errore": credenziali_errore,
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
            "message": (
                "Imposta GOOGLE_DRIVE_QUIETANZE_FOLDER_ID e il service account "
                "(GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON)."
            ),
        }
    creds, cred_err = _load_credentials_quietanze()
    if creds is None:
        return {
            "status": "error",
            "message": f"Credenziali Google Drive non valide: {cred_err}",
        }
    service = _build_drive_service()
    if service is None:
        return {
            "status": "error",
            "message": "Service Drive non disponibile (errore costruzione client).",
        }

    from app.services.f24_canonico import importa_quietanza

    parent_id = _folder_id()
    result: Dict[str, Any] = {
        "status": "ok",
        "total": 0,
        "imported": 0,
        "duplicates": 0,
        "matchati": 0,
        "senza_match": 0,
        "errors": 0,
        "moved": 0,
        "inboxes": 0,
        "details": [],
    }
    try:
        inboxes = resolve_inboxes_or_legacy(
            service,
            parent_id,
            _get_or_create_inbox_folder,
            max_depth=1,
        )
        result["inboxes"] = len(inboxes)

        for inbox in inboxes:
            source_id = inbox["inbox_id"]
            lifecycle_parent_id = inbox["lifecycle_parent_id"]
            elaborate_id = _resolve_state_folder(
                service, lifecycle_parent_id, "elaborate"
            )
            error_id = _resolve_state_folder(service, lifecycle_parent_id, "error")
            relative_inbox = inbox.get("relative_path") or "DA ELABORARE"
            pdf_files = _list_pdf_files(service, source_id)
            result["total"] += len(pdf_files)

            for file_info in pdf_files:
                fid = file_info["id"]
                fname = file_info["name"]
                source_path = f"{relative_inbox}/{fname}"
                try:
                    content = _download_bytes(service, fid)
                    if not content:
                        result["errors"] += 1
                        result["details"].append(
                            {"source_path": source_path, "error": "file vuoto"}
                        )
                        if error_id:
                            _move_to_folder(service, fid, source_id, error_id)
                        continue

                    esito = await importa_quietanza(
                        db, content, fname, source="drive_quietanze"
                    )
                    if not esito.get("success"):
                        result["errors"] += 1
                        result["details"].append(
                            {"source_path": source_path, "error": esito.get("error")}
                        )
                        if error_id:
                            _move_to_folder(service, fid, source_id, error_id)
                        continue

                    if esito.get("duplicate"):
                        result["duplicates"] += 1
                    else:
                        result["imported"] += 1
                        if esito.get("f24_matchati"):
                            result["matchati"] += 1
                        else:
                            result["senza_match"] += 1
                        logger.info("Drive quietanze: importata %s", source_path)
                        try:
                            from app.services.event_bus import propagate_event, EventTypes

                            await propagate_event(
                                EventTypes.DOCUMENTO_ACQUISITO,
                                {
                                    "documento_id": esito.get("quietanza_id"),
                                    "filename": fname,
                                    "origine": "drive_quietanze",
                                    "mime_type": "application/pdf",
                                    "hash_file": hashlib.md5(content).hexdigest(),
                                    "category": "quietanza_f24",
                                },
                                db,
                                source_module="drive_quietanze_ingest",
                            )
                        except Exception:
                            logger.exception(
                                "Drive quietanze: errore propagazione evento documento.acquisito"
                            )

                    if elaborate_id:
                        _move_to_elaborate(service, fid, source_id, elaborate_id)
                        result["moved"] += 1
                except Exception as exc:
                    logger.error("Drive quietanze: errore su %s: %s", source_path, exc)
                    result["errors"] += 1
                    result["details"].append(
                        {"source_path": source_path, "error": str(exc)}
                    )
                    if error_id:
                        try:
                            _move_to_folder(service, fid, source_id, error_id)
                        except Exception:
                            logger.exception(
                                "Drive quietanze: impossibile spostare %s in Errori",
                                source_path,
                            )
    except Exception as exc:
        logger.error("Drive quietanze: errore sync: %s", exc)
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {
                "$set": {
                    "valore": now,
                    "last_error": str(exc),
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        return {"status": "error", "message": str(exc)}
    finally:
        _close_drive_service(service)

    prev = await db["sistema_stato"].find_one(
        {"chiave": _STATO_KEY}, {"_id": 0}
    ) or {}
    last_result = {
        key: result[key]
        for key in (
            "total",
            "imported",
            "duplicates",
            "matchati",
            "senza_match",
            "errors",
            "moved",
            "inboxes",
        )
    }
    last_result["details"] = result["details"][:5]
    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {
            "$set": {
                "valore": now,
                "last_result": last_result,
                "last_error": None,
                "total_imported": prev.get("total_imported", 0)
                + result["imported"],
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return result


async def verifica_quadratura_elaborate(db) -> Dict[str, Any]:
    """Controlla tutte le ELABORATE reali senza crearne di nuove."""
    if not is_configured():
        return {"status": "not_configured"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    from app.services.f24_canonico import COLL_QUIETANZE, importa_quietanza

    parent_id = _folder_id()
    esito: Dict[str, Any] = {
        "status": "ok",
        "controllati": 0,
        "quadrati": 0,
        "recuperati": 0,
        "errori": 0,
        "details": [],
    }
    try:
        elaborate_folders = discover_lifecycle_folders(
            service, parent_id, max_depth=1, states=("elaborate",)
        )
        if not elaborate_folders:
            return {
                "status": "ok",
                "message": "Nessuna cartella Elaborate",
                **esito,
            }

        for folder in elaborate_folders:
            elaborate_id = folder["folder_id"]
            for file_info in _list_pdf_files(service, elaborate_id):
                esito["controllati"] += 1
                try:
                    content = _download_bytes(service, file_info["id"])
                    if not content:
                        esito["errori"] += 1
                        continue
                    content_hash = hashlib.md5(content).hexdigest()
                    existing = await db[COLL_QUIETANZE].find_one(
                        {"pdf_hash": content_hash}, {"_id": 0, "id": 1}
                    )
                    if existing:
                        esito["quadrati"] += 1
                        continue
                    res = await importa_quietanza(
                        db,
                        content,
                        file_info["name"],
                        source="drive_quietanze_quadratura",
                    )
                    if res.get("success") and not res.get("duplicate"):
                        esito["recuperati"] += 1
                        esito["details"].append(
                            {"file": file_info["name"], "recuperato": True}
                        )
                        logger.warning(
                            "Quadratura quietanze: recuperato buco %s",
                            file_info["name"],
                        )
                    elif not res.get("success"):
                        esito["errori"] += 1
                        esito["details"].append(
                            {"file": file_info["name"], "error": res.get("error")}
                        )
                    else:
                        esito["quadrati"] += 1
                except Exception as exc:
                    esito["errori"] += 1
                    esito["details"].append(
                        {"file": file_info["name"], "error": str(exc)}
                    )
    except Exception as exc:
        return {"status": "error", "message": str(exc), **esito}
    finally:
        _close_drive_service(service)

    if esito["recuperati"] or esito["errori"]:
        try:
            from app.services.alert_engine import genera_alert

            await genera_alert(
                "DOC_QUADRATURA_DRIVE",
                "quadratura_quietanze",
                "quietanze_f24",
                f"Quadratura Drive quietanze: {esito['recuperati']} recuperate, "
                f"{esito['errori']} errori su {esito['controllati']} file in Elaborate",
                db,
            )
        except Exception:
            logger.exception("Alert quadratura quietanze non generato")

    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {
            "$set": {
                "last_quadratura": {
                    "quando": now,
                    **{
                        key: esito[key]
                        for key in (
                            "controllati",
                            "quadrati",
                            "recuperati",
                            "errori",
                        )
                    },
                }
            }
        },
        upsert=True,
    )
    return esito
