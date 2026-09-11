"""Discovery sicura delle inbox Drive annidate.

Le aree operative reali del Drive non hanno tutte una inbox al primo livello:
- fatture/corrispettivi: <radice>/<anno>/DA ELABORARE
- cedolini: <radice>/<dipendente>/DA ELABORARE

Questo modulo scopre solo cartelle di lifecycle con nome canonico esatto e con
profondita' limitata. Non esegue una scansione indiscriminata di archivi o
cartelle storiche e non crea/sposta/cancella nulla.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

_FOLDER_MIME = "application/vnd.google-apps.folder"


def _normalized_lifecycle_name(name: str) -> str:
    """Normalizza maiuscole/spazi/underscore senza accettare prefissi legacy."""
    return " ".join((name or "").replace("_", " ").split()).casefold()


def is_inbox_name(name: str) -> bool:
    return _normalized_lifecycle_name(name) == "da elaborare"


def is_elaborate_name(name: str) -> bool:
    return _normalized_lifecycle_name(name) == "elaborate"


def is_error_name(name: str) -> bool:
    return _normalized_lifecycle_name(name) == "errori"


def _list_child_folders(service, parent_id: str) -> List[Dict[str, Any]]:
    """Elenca solo le sottocartelle dirette, con paginazione Drive."""
    q = (
        f"'{parent_id}' in parents and trashed = false "
        f"and mimeType = '{_FOLDER_MIME}'"
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
        out.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def discover_inboxes(
    service,
    root_id: str,
    *,
    max_depth: int = 2,
) -> List[Dict[str, Any]]:
    """Trova inbox ``DA ELABORARE`` entro ``max_depth`` livelli dalla radice.

    Ritorna record con:
      - inbox_id: cartella DA ELABORARE
      - lifecycle_parent_id: padre dove creare/trovare Elaborate ed Errori
      - relative_path: percorso leggibile dalla radice
      - depth: profondita' dell'inbox (1 = figlia diretta della radice)

    La ricerca scende solo in cartelle normali. Se incontra una cartella di
    lifecycle (Da elaborare/Elaborate/Errori) non la attraversa ulteriormente,
    cosi' i documenti gia' elaborati non possono rientrare nel flusso.
    """
    if not root_id or max_depth < 1:
        return []

    queue: List[Tuple[str, str, int]] = [(root_id, "", 0)]
    visited = set()
    found: List[Dict[str, Any]] = []

    while queue:
        parent_id, prefix, parent_depth = queue.pop(0)
        if parent_id in visited:
            continue
        visited.add(parent_id)

        for folder in _list_child_folders(service, parent_id):
            folder_id = folder.get("id")
            name = folder.get("name") or ""
            if not folder_id:
                continue
            depth = parent_depth + 1
            relative_path = f"{prefix}/{name}" if prefix else name

            if is_inbox_name(name):
                found.append({
                    "inbox_id": folder_id,
                    "lifecycle_parent_id": parent_id,
                    "relative_path": relative_path,
                    "depth": depth,
                })
                continue

            # Non attraversare stati terminali e non superare il limite.
            if is_elaborate_name(name) or is_error_name(name):
                continue
            if depth < max_depth:
                queue.append((folder_id, relative_path, depth))

    # Ordine stabile per log/test e dedup difensiva per ID Drive.
    unique: Dict[str, Dict[str, Any]] = {}
    for item in found:
        unique.setdefault(item["inbox_id"], item)
    return sorted(unique.values(), key=lambda item: (item["relative_path"].casefold(), item["inbox_id"]))


def resolve_inboxes_or_legacy(
    service,
    root_id: str,
    create_legacy_inbox,
    *,
    max_depth: int = 2,
) -> List[Dict[str, Any]]:
    """Usa la struttura reale; crea la vecchia inbox root solo se non esiste.

    Questo e' il punto chiave anti-regressione: se sotto la radice sono gia'
    presenti ``anno/DA ELABORARE`` o ``dipendente/DA ELABORARE``, NON viene
    creata una nuova inbox parallela al primo livello.
    """
    inboxes = discover_inboxes(service, root_id, max_depth=max_depth)
    if inboxes:
        return inboxes

    inbox_id = create_legacy_inbox(service, root_id)
    if not inbox_id:
        return []
    return [{
        "inbox_id": inbox_id,
        "lifecycle_parent_id": root_id,
        "relative_path": "Da elaborare",
        "depth": 1,
        "legacy_fallback": True,
    }]
