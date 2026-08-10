"""Registro evidence-bound delle cartelle fiscali e feed incrementale Drive.

La scoperta e' fail-closed: zero o piu' cartelle omonime non producono mai un
mapping attivo. Le rimozioni dalla fonte marcano la prova, non cancellano la
storia documentale del gestionale.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services import drive_cedolini_ingest as _drive
from app.services.drive_folder_registry import set_runtime_folders

logger = logging.getLogger(__name__)
FOLDER_MIME = "application/vnd.google-apps.folder"
STATE_KEY = "fiscal_documents"
TARGETS = {
    "avvisi_bonari": "Avvisi bonari",
    "cartelle_esattoriali": "Cartelle esattoriali",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def build_drive_service():
    creds, error = _drive._load_credentials_cedolini()
    if creds is None:
        raise RuntimeError(f"Credenziali Google Drive non disponibili: {error}")
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _discover_sync(service, root_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = service.files().get(
        fileId=root_id,
        fields="id,name,mimeType,parents,trashed,driveId",
        supportsAllDrives=True,
    ).execute()
    if root.get("trashed") or root.get("mimeType") != FOLDER_MIME:
        raise ValueError("La radice fiscale non e' una cartella Drive attiva")

    pending = [(root_id, str(root.get("name") or "Radice fiscale"))]
    visited: set[str] = set()
    found: list[dict[str, Any]] = []
    while pending:
        parent_id, parent_path = pending.pop(0)
        if parent_id in visited:
            continue
        visited.add(parent_id)
        for item in _drive._list_children(service, parent_id):
            if item.get("mimeType") != FOLDER_MIME:
                continue
            path = f"{parent_path}/{item.get('name', '')}"
            found.append({**item, "path": path, "parent_id": parent_id})
            pending.append((item["id"], path))

    entries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for area, expected_name in TARGETS.items():
        matches = [item for item in found if _norm(item.get("name")) == _norm(expected_name)]
        if len(matches) != 1:
            errors.append({"area": area, "matches": len(matches), "error": "cartella assente o ambigua"})
            continue
        item = matches[0]
        entries.append({
            "area": area,
            "label": expected_name,
            "folder_id": item["id"],
            "root_folder_id": root_id,
            "path": item["path"],
            "discovered_at": _now(),
            "source": "drive_api_verified",
        })
    return root, entries + errors


async def discover_fiscal_folders(db, service=None) -> dict[str, Any]:
    service = service or build_drive_service()
    root_id = settings.DRIVE_FISCAL_ROOT_FOLDER_ID.strip()
    root, results = await asyncio.to_thread(_discover_sync, service, root_id)
    entries = [item for item in results if "folder_id" in item]
    errors = [item for item in results if "error" in item]
    run_id = f"drive-discovery-{datetime.now(timezone.utc).timestamp()}"
    await db["drive_folder_discovery_runs"].insert_one({
        "id": run_id, "root_name": root.get("name"), "root_folder_id": root_id,
        "status": "ok" if not errors else "error", "entries": entries,
        "errors": errors, "created_at": _now(),
    })
    if errors:
        return {"status": "error", "configured": 0, "errors": errors, "run_id": run_id}
    for entry in entries:
        await db["drive_folder_registry"].update_one(
            {"area": entry["area"]}, {"$set": entry}, upsert=True,
        )
    set_runtime_folders(entries)
    return {"status": "ok", "configured": len(entries), "areas": [e["area"] for e in entries], "run_id": run_id}


async def load_persisted_registry(db) -> list[dict[str, Any]]:
    entries = await db["drive_folder_registry"].find(
        {"source": "drive_api_verified"}, {"_id": 0}
    ).to_list(length=50)
    set_runtime_folders(entries)
    return entries


def _get_start_token(service) -> str:
    return service.changes().getStartPageToken(supportsAllDrives=True).execute()["startPageToken"]


def _list_changes(service, token: str) -> tuple[list[dict[str, Any]], str]:
    changes: list[dict[str, Any]] = []
    page_token = token
    new_token = token
    while page_token:
        response = service.changes().list(
            pageToken=page_token,
            spaces="drive",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="nextPageToken,newStartPageToken,changes(fileId,removed,time,file(id,name,mimeType,parents,trashed))",
        ).execute()
        changes.extend(response.get("changes", []))
        page_token = response.get("nextPageToken")
        new_token = response.get("newStartPageToken") or new_token
    return changes, new_token


def _is_under_target(service, file: dict[str, Any], target_ids: set[str]) -> bool:
    """Verifica l'ascendenza anche per file in sottocartelle annidate."""
    pending = list(file.get("parents") or [])
    visited: set[str] = set()
    while pending:
        parent_id = pending.pop()
        if parent_id in target_ids:
            return True
        if parent_id in visited:
            continue
        visited.add(parent_id)
        parent = service.files().get(
            fileId=parent_id, fields="id,parents,trashed", supportsAllDrives=True,
        ).execute()
        if parent.get("trashed"):
            continue
        pending.extend(parent.get("parents") or [])
    return False


async def sync_incremental(db, service=None) -> dict[str, Any]:
    """Consuma Drive Changes; il primo avvio esegue una sola scansione piena."""
    service = service or build_drive_service()
    entries = await load_persisted_registry(db)
    if len(entries) != len(TARGETS):
        discovery = await discover_fiscal_folders(db, service)
        if discovery["status"] != "ok":
            return discovery
        entries = await load_persisted_registry(db)

    state = await db["drive_sync_state"].find_one({"key": STATE_KEY})
    if not state or not state.get("page_token"):
        from app.services import drive_documenti_ingest
        # Acquisire il cursore prima della scansione elimina la finestra in cui
        # una modifica concorrente potrebbe sfuggire tra scansione e token.
        token = await asyncio.to_thread(_get_start_token, service)
        full_result = await drive_documenti_ingest.sync_tutti(db)
        await db["drive_sync_state"].update_one(
            {"key": STATE_KEY}, {"$set": {"page_token": token, "initialized_at": _now(), "updated_at": _now()}}, upsert=True,
        )
        return {"status": "ok", "mode": "initial_full", "result": full_result}

    changes, new_token = await asyncio.to_thread(_list_changes, service, state["page_token"])
    target_ids = {entry["folder_id"] for entry in entries}
    relevant = []
    for change in changes:
        file = change.get("file") or {}
        if change.get("removed") or file.get("trashed"):
            await db["documents_inbox"].update_many(
                {"drive_file_id": change.get("fileId")},
                {"$set": {"source_deleted_at": change.get("time") or _now()}},
            )
        is_relevant = bool(change.get("removed"))
        if file and not is_relevant:
            is_relevant = await asyncio.to_thread(_is_under_target, service, file, target_ids)
        if is_relevant:
            relevant.append(change)

    ingest_result: dict[str, Any] = {"status": "no_changes"}
    if relevant:
        from app.services import drive_documenti_ingest
        ingest_result = await drive_documenti_ingest.sync_tutti(db)
    await db["drive_sync_state"].update_one(
        {"key": STATE_KEY}, {"$set": {"page_token": new_token, "updated_at": _now(), "last_changes": len(changes), "last_relevant": len(relevant)}}, upsert=True,
    )
    await db["drive_sync_runs"].insert_one({
        "id": f"drive-sync-{datetime.now(timezone.utc).timestamp()}", "mode": "changes",
        "changes": len(changes), "relevant": len(relevant), "result": ingest_result, "created_at": _now(),
    })
    return {"status": "ok", "mode": "changes", "changes": len(changes), "relevant": len(relevant), "result": ingest_result}
