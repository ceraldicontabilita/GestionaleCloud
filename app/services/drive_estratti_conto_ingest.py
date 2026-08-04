"""Import automatico ricorsivo dell'area Drive ``Estratti conto``.

Usa esattamente l'endpoint/pipeline dell'import manuale, quindi deduplica,
riconciliazione, assegni e Prima Nota non possono divergere tra i due canali.

La cartella reale contiene fonti diverse (BNL, BPM, carte e POS). Ogni fonte
mantiene il proprio ciclo ``Da elaborare``/``Elaborate``/``Errori``; gli
archivi non vengono mai risaliti dal job. I file POS sono instradati al
motore delle chiusure giornaliere e non diventano falsi movimenti bancari.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
_FOLDER_MIME = "application/vnd.google-apps.folder"
_LIFECYCLE_NAMES = {"da elaborare", "elaborate", "errori", "duplicati"}


def _folder_id() -> Optional[str]:
    ids = _folder_ids()
    return ids[0] if ids else None


def _split_folder_ids(raw: Optional[str]) -> List[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part for part in re.split(r"[\s,;]+", value) if part]


def _registry_folder_ids() -> List[str]:
    """Legge eventuali radici aggiuntive dal registro Drive senza esporle."""
    raw = str(settings.DRIVE_FOLDER_REGISTRY_JSON or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    entries = payload.get("folders", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    result: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        area = re.sub(r"[^a-z0-9]+", "_", str(entry.get("area") or "").lower()).strip("_")
        group = re.sub(r"[^a-z0-9]+", "_", str(entry.get("group") or entry.get("parent_area") or "").lower()).strip("_")
        if area == "estratti_conto" or area.startswith("estratti_conto_") or group == "estratti_conto":
            folder_id = str(entry.get("folder_id") or "").strip()
            if folder_id:
                result.append(folder_id)
    return result


def _folder_ids() -> List[str]:
    values: List[str] = []
    for raw in (
        settings.GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS,
        settings.DRIVE_FOLDER_ESTRATTI_CONTO_IDS,
        settings.DRIVE_ESTRATTI_CONTO_FOLDER_IDS,
    ):
        values.extend(_split_folder_ids(raw))
    values.extend(filter(None, (
        settings.GOOGLE_DRIVE_ESTRATTI_FOLDER_ID,
        settings.DRIVE_FOLDER_ESTRATTI_CONTO_ID,
        settings.DRIVE_ESTRATTI_CONTO_FOLDER_ID,
    )))
    values.extend(_registry_folder_ids())
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


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
        and _folder_ids()
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


def _list_children(service, parent_id: str) -> List[Dict[str, Any]]:
    query = f"'{parent_id}' in parents and trashed = false"
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        result = service.files().list(
            q=query, fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            return out


def _route_for_path(path: str, filename: str = "") -> Optional[str]:
    """Classifica la fonte senza usare dati contabili o importi."""
    source = f"{path}/{filename}".lower()
    if "mutuo acquisto" in source:
        return "mutuo"
    if "pos bpm" in source or "pos bnl" in source:
        return "pos"
    segments = {part.strip() for part in path.lower().split("/") if part.strip()}
    if (
        "carta di credito bnl" in source
        or "carta di credito bpm" in source
        or "bnl" in segments
        or "bpm" in segments
    ):
        return "bank"
    # File bancari lasciati direttamente nella radice storica.
    if not path and any(token in filename.lower() for token in (
        "estratto", "elencoentrateuscite", "movimenti_bnl_bpm",
    )):
        return "bank"
    return None


def _supported_file(route: Optional[str], filename: str) -> bool:
    lower = filename.lower()
    if route == "bank":
        return lower.endswith((".csv", ".xlsx", ".xls", ".pdf"))
    if route == "pos":
        return (
            lower.endswith((".csv", ".xlsx", ".xlsm"))
            and any(token in lower for token in (
                "export_mensile", "export_transazioni", "commissioni_",
            ))
        )
    if route == "mutuo":
        return lower.endswith(".pdf")
    return False


def _discover_work_items(
    service,
    root_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Scansiona le fonti supportate senza entrare negli archivi.

    Compatibilita' con la struttura esistente: durante la transizione legge
    sia i file storicamente messi direttamente nella cartella fonte, sia i
    nuovi file presenti in ``Da elaborare``. Dopo il primo passaggio i file
    diretti vengono spostati e resterà attivo soltanto l'inbox.
    """
    items: List[Dict[str, Any]] = []
    sources: Dict[str, Dict[str, str]] = {}

    def walk(folder_id: str, path: str, inherited_route: Optional[str], lifecycle_parent: Optional[str]):
        children = _list_children(service, folder_id)
        direct_files = [item for item in children if item.get("mimeType") != _FOLDER_MIME]
        folders = [item for item in children if item.get("mimeType") == _FOLDER_MIME]

        current_route = _route_for_path(path) or inherited_route
        current_lifecycle = lifecycle_parent
        if current_route != inherited_route and current_route:
            current_lifecycle = folder_id
        if current_route and current_lifecycle == folder_id:
            sources.setdefault(folder_id, {
                "id": folder_id,
                "path": path or "Estratti conto",
            })

        for item in direct_files:
            route = current_route or _route_for_path(path, item.get("name") or "")
            if not _supported_file(route, item.get("name") or ""):
                continue
            target_parent = current_lifecycle or folder_id
            sources[target_parent] = {"id": target_parent, "path": path or "Estratti conto"}
            items.append({
                **item,
                "route": route,
                "source_parent_id": folder_id,
                "lifecycle_parent_id": target_parent,
                "source_path": "/".join(part for part in (path, item.get("name") or "") if part),
            })

        for folder in folders:
            name = (folder.get("name") or "").strip()
            lower = name.lower()
            if lower in _LIFECYCLE_NAMES:
                if lower == "da elaborare" and current_route:
                    for item in _list_children(service, folder["id"]):
                        if item.get("mimeType") == _FOLDER_MIME or not _supported_file(current_route, item.get("name") or ""):
                            continue
                        target_parent = current_lifecycle or folder_id
                        sources[target_parent] = {"id": target_parent, "path": path or "Estratti conto"}
                        items.append({
                            **item,
                            "route": current_route,
                            "source_parent_id": folder["id"],
                            "lifecycle_parent_id": target_parent,
                            "source_path": "/".join(part for part in (path, "Da elaborare", item.get("name") or "") if part),
                        })
                continue
            child_path = "/".join(part for part in (path, name) if part)
            child_route = _route_for_path(child_path) or current_route
            child_lifecycle = current_lifecycle
            if child_route != current_route and child_route:
                child_lifecycle = folder["id"]
            walk(folder["id"], child_path, child_route, child_lifecycle)

    walk(root_id, "", None, None)
    return items, list(sources.values())


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
        from app.services.pos_terminal_import import importa_pos_terminal_file
        from app.services.pos_commissioni_import import importa_pos_commissioni_file
        from app.services.mutui_document_import import importa_documento_mutuo

        result: Dict[str, Any] = {
            "status": "ok", "total": 0, "processed": 0, "moved": 0,
            "new_movements": 0, "duplicates": 0, "cheques": 0,
            "pos_files": 0, "pos_days": 0, "roots": len(_folder_ids()),
            "pos_commission_files": 0, "pos_commission_days": 0,
            "mutuo_files": 0, "mutuo_duplicates": 0,
            "sources": [], "errors": [],
        }
        files_by_id: Dict[str, Dict[str, Any]] = {}
        sources_by_id: Dict[str, Dict[str, str]] = {}
        for root_id in _folder_ids():
            root_files, root_sources = _discover_work_items(service, root_id)
            for item in root_files:
                files_by_id.setdefault(item["id"], item)
            for source in root_sources:
                sources_by_id.setdefault(source["id"], source)
        files = list(files_by_id.values())
        sources = list(sources_by_id.values())
        result["sources"] = [source["path"] for source in sources]
        result["total"] = len(files)
        lifecycle: Dict[str, Dict[str, Optional[str]]] = {}
        for source in sources:
            source_id = source["id"]
            lifecycle[source_id] = {
                "inbox": _get_or_create_inbox_folder(service, source_id),
                "elaborate": _get_or_create_elaborate_folder(service, source_id),
                "error": _get_or_create_error_folder(service, source_id),
            }
        for item in files:
            source_id = item["source_parent_id"]
            target = lifecycle[item["lifecycle_parent_id"]]
            try:
                content = _download_bytes(service, item["id"])
                if not content:
                    raise ValueError("file vuoto")
                if item["route"] == "pos":
                    if "commissioni_" in item["name"].lower():
                        esito = await importa_pos_commissioni_file(
                            db, content, item["name"], drive_file_id=item["id"],
                        )
                        result["pos_commission_files"] += 1
                        result["pos_commission_days"] += int(esito.get("days") or 0)
                    else:
                        esito = await importa_pos_terminal_file(
                            db, content, item["name"], drive_file_id=item["id"],
                        )
                        result["pos_files"] += 1
                        result["pos_days"] += int(esito.get("days") or 0)
                elif item["route"] == "mutuo":
                    esito = await importa_documento_mutuo(
                        db, content, item["name"], drive_file_id=item["id"],
                    )
                    result["mutuo_files"] += 1
                    result["mutuo_duplicates"] += int(bool(esito.get("duplicate")))
                else:
                    esito = await import_estratto_conto(_UploadDrive(item["name"], content))
                    if isinstance(esito, dict) and (esito.get("error") or esito.get("detail")):
                        raise ValueError(esito.get("error") or esito.get("detail"))
                    stats = (esito or {}).get("stats") or {}
                    result["new_movements"] += int(stats.get("nuovi") or (esito or {}).get("movimenti_nuovi_importati") or 0)
                    result["duplicates"] += int(stats.get("duplicati") or (esito or {}).get("duplicati_saltati") or 0)
                    sync_assegni = (esito or {}).get("assegni_sync") or {}
                    result["cheques"] += int(sync_assegni.get("assegni_creati") or 0)
                result["processed"] += 1
                if target["elaborate"]:
                    _move_to_elaborate(service, item["id"], source_id, target["elaborate"])
                    result["moved"] += 1
            except Exception as exc:
                logger.exception("Drive estratti conto: errore su %s", item.get("source_path"))
                result["errors"].append({"file": item.get("source_path"), "error": str(exc)})
                if target["error"]:
                    try:
                        _move_to_folder(service, item["id"], source_id, target["error"])
                    except Exception:
                        logger.exception("Drive estratti conto: impossibile spostare %s in Errori", item.get("name"))

        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_result": result, "updated_at": now}},
            upsert=True,
        )
        return result
