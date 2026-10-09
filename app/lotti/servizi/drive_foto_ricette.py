"""Lettura delle foto ricette rimaste su Google Drive.

Le foto nuove vanno su Supabase Storage (``supabase_foto_ricette``): qui si
leggono e si cestinano soltanto quelle gia' collegate a Drive, nella cartella
scritta sul record della ricetta (``foto_drive_folder_id``). Ogni lettura
verifica che il file appartenga a quella cartella, cosi' un ID arbitrario non
diventa un proxy verso l'intero Drive aziendale.
"""

from __future__ import annotations

import io
from typing import Any


def build_drive_service(folder_id: str):
    # La credenziale si sceglie provando l'accesso alla cartella delle foto,
    # non a quella di un altro canale: sparita la cartella cedolini, il loader
    # dei cedolini falliva e con lui ogni foto, anche se leggibile.
    from app.services.drive_credential_probe import load_credentials_for_folder
    creds, error = load_credentials_for_folder(folder_id)
    if creds is None:
        raise RuntimeError(f"Credenziali Google Drive non disponibili: {error}")
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _metadata(service: Any, file_id: str, *, folder_id: str) -> dict:
    data = service.files().get(
        fileId=file_id,
        fields="id,name,mimeType,size,md5Checksum,sha256Checksum,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    if data.get("trashed") or folder_id not in (data.get("parents") or []):
        raise FileNotFoundError("Immagine ricetta assente dalla cartella Drive canonica")
    return data


def leggi(file_id: str, *, folder_id: str, service: Any = None) -> tuple[bytes, str, dict]:
    service = service or build_drive_service(folder_id)
    metadata = _metadata(service, file_id, folder_id=folder_id)
    from googleapiclient.http import MediaIoBaseDownload

    out = io.BytesIO()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(out, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return out.getvalue(), metadata.get("mimeType") or "application/octet-stream", metadata


def cestina(file_id: str, *, folder_id: str, service: Any = None) -> dict:
    """Sposta nel cestino Drive una foto canonica, dopo averne verificato la cartella."""
    service = service or build_drive_service(folder_id)
    _metadata(service, file_id, folder_id=folder_id)
    service.files().update(
        fileId=file_id,
        body={"trashed": True},
        fields="id,name,mimeType,size,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    return {"id": file_id, "trashed": True}
