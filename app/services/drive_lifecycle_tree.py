"""Discovery sicura delle cartelle lifecycle Drive annidate.

Le aree operative reali del Drive non hanno tutte gli stati al primo livello:
- fatture/corrispettivi: <radice>/<anno>/DA ELABORARE
- cedolini: <radice>/<dipendente>/DA ELABORARE

Questo modulo scopre solo cartelle di lifecycle con nome canonico esatto e con
profondita' limitata. Non esegue una scansione indiscriminata di archivi o
cartelle storiche e non crea/sposta/cancella nulla.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

_FOLDER_MIME = "application/vnd.google-apps.folder"
_STATE_ALIASES = {
    "inbox": "da elaborare",
    "elaborate": "elaborate",
    "error": "errori",
}


def _normalized_lifecycle_name(name: str) -> str:
    """Normalizza maiuscole/spazi/underscore senza accettare prefissi legacy."""
    return " ".join((name or "").replace("_", " ").split()).casefold()


def is_inbox_name(name: str) -> bool:
    return _normalized_lifecycle_name(name) == _STATE_ALIASES["inbox"]


def is_elaborate_name(name: str) -> bool:
    return _normalized_lifecycle_name(name) == _STATE_ALIASES["elaborate"]


def is_error_name(name: str) -> bool:
    return _normalized_lifecycle_name(name) == _STATE_ALIASES["error"]


def _state_for_name(name: str) -> str | None:
    normalized = _normalized_lifecycle_name(name)
    for state, expected in _STATE_ALIASES.items():
        if normalized == expected:
            return state
    return None


def _looks_like_legacy_lifecycle_container(name: str) -> bool:
    """Blocca vecchie cartelle sweep che incorporano il nome di uno stato.

    Esempi reali/storici come ``mutui__90 - DA ELABORARE`` o
    ``Cedolini Paga__99 - ELABORATE`` non sono inbox canoniche e non devono
    nemmeno essere attraversati: potrebbero contenere copie archiviate che
    verrebbero rimesse in lavorazione.
    """
    normalized = _normalized_lifecycle_name(name)
    return any(expected in normalized for expected in _STATE_ALIASES.values())


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


def discover_lifecycle_folders(
    service,
    root_id: str,
    *,
    max_depth: int = 2,
    states: Iterable[str] = ("inbox", "elaborate", "error"),
) -> List[Dict[str, Any]]:
    """Trova stati lifecycle entro ``max_depth`` livelli dalla radice.

    Ogni risultato contiene ``folder_id``, ``state``, ``lifecycle_parent_id``,
    ``relative_path`` e ``depth``. La ricerca non attraversa mai una cartella
    lifecycle, né una vecchia cartella sweep che ne incorpora il nome: un file
    già elaborato o archiviato non può rientrare accidentalmente nel flusso.
    """
    wanted = set(states)
    unknown = wanted.difference(_STATE_ALIASES)
    if unknown:
        raise ValueError(f"Stati lifecycle non riconosciuti: {sorted(unknown)}")
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
            state = _state_for_name(name)

            if state:
                if state in wanted:
                    found.append({
                        "folder_id": folder_id,
                        "state": state,
                        "lifecycle_parent_id": parent_id,
                        "relative_path": relative_path,
                        "depth": depth,
                    })
                continue

            # Una cartella legacy/sweep che CONTIENE il nome di uno stato non
            # è uno stato canonico, ma non va attraversata perché può contenere
            # copie storiche con sottocartelle omonime.
            if _looks_like_legacy_lifecycle_container(name):
                continue

            if depth < max_depth:
                queue.append((folder_id, relative_path, depth))

    unique: Dict[str, Dict[str, Any]] = {}
    for item in found:
        unique.setdefault(item["folder_id"], item)
    return sorted(
        unique.values(),
        key=lambda item: (item["relative_path"].casefold(), item["folder_id"]),
    )


def discover_inboxes(
    service,
    root_id: str,
    *,
    max_depth: int = 2,
) -> List[Dict[str, Any]]:
    """Trova le sole cartelle ``DA ELABORARE`` e usa nomi compatibili."""
    found = discover_lifecycle_folders(
        service, root_id, max_depth=max_depth, states=("inbox",),
    )
    return [
        {
            "inbox_id": item["folder_id"],
            "lifecycle_parent_id": item["lifecycle_parent_id"],
            "relative_path": item["relative_path"],
            "depth": item["depth"],
        }
        for item in found
    ]


def resolve_inboxes_or_legacy(
    service,
    root_id: str,
    create_legacy_inbox,
    *,
    max_depth: int = 2,
) -> List[Dict[str, Any]]:
    """Usa la struttura reale; crea la vecchia inbox root solo se non esiste.

    Se sotto la radice sono già presenti ``anno/DA ELABORARE`` o
    ``dipendente/DA ELABORARE``, NON viene creata una nuova inbox parallela al
    primo livello.
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
