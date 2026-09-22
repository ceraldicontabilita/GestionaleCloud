"""Archivio canonico Drive delle immagini ricette.

Supabase conserva il record operativo della ricetta e il ``foto_drive_id``;
i byte dell'immagine restano su Google Drive. Ogni lettura verifica che il file
appartenga alla cartella configurata, così un ID arbitrario non diventa un
proxy verso l'intero Drive aziendale.
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import PurePath
from typing import Any

from app.config import settings


def build_drive_service():
    # Import locale: il servizio immagini non deve trascinare il catalogo Excel
    # documentale (openpyxl) nei processi/test che gestiscono solo fotografie.
    from app.services.drive_cedolini_ingest import _load_credentials_cedolini
    creds, error = _load_credentials_cedolini()
    if creds is None:
        raise RuntimeError(f"Credenziali Google Drive non disponibili: {error}")
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


async def risolvi_folder_id(db: Any) -> str:
    """Risolve la cartella canonica senza rendere Render un secondo archivio.

    La variabile d'ambiente resta compatibile, ma il registro persistito in
    Supabase e' la fonte operativa quando e' presente. La voce deve avere
    provenienza verificata: un ID privo di fonte non abilita accessi Drive.
    """
    value = str(settings.GOOGLE_DRIVE_RICETTE_IMAGES_FOLDER_ID or "").strip()
    if value:
        return value
    doc = await db["drive_folder_registry"].find_one(
        {
            "area": "ricette_immagini",
            "source": {"$in": ["drive_api_verified", "manual_owner_verified"]},
        },
        {"_id": 0, "folder_id": 1},
    )
    value = str((doc or {}).get("folder_id") or "").strip()
    if not value:
        raise RuntimeError("Cartella Drive ricette non configurata nel registro canonico")
    return value


def _estensione(mime: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(str(mime or "").split(";", 1)[0].lower(), ".img")


def _nome_file(ricetta_id: str, digest: str, mime: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", PurePath(ricetta_id).name).strip("._")
    return f"{safe or 'ricetta'}_{digest[:16]}{_estensione(mime)}"


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
    service = service or build_drive_service()
    metadata = _metadata(service, file_id, folder_id=folder_id)
    from googleapiclient.http import MediaIoBaseDownload

    out = io.BytesIO()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(out, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return out.getvalue(), metadata.get("mimeType") or "application/octet-stream", metadata


def carica(
    *, ricetta_id: str, contenuto: bytes, mime: str, filename: str | None = None,
    folder_id: str, service: Any = None,
) -> dict:
    if not str(mime or "").lower().startswith("image/"):
        raise ValueError("File non è un'immagine")
    service = service or build_drive_service()
    digest = hashlib.sha256(contenuto).hexdigest()
    nome = _nome_file(ricetta_id, digest, mime)
    from googleapiclient.http import MediaIoBaseUpload

    created = service.files().create(
        body={
            "name": nome,
            "parents": [folder_id],
            "description": f"Ricetta {ricetta_id}; origine {filename or nome}; sha256 {digest}",
        },
        media_body=MediaIoBaseUpload(io.BytesIO(contenuto), mimetype=mime, resumable=False),
        fields="id,name,mimeType,size,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    verified = _metadata(service, created["id"], folder_id=folder_id)
    if int(verified.get("size") or -1) != len(contenuto):
        raise RuntimeError("Dimensione immagine Drive diversa dai byte caricati")
    return {**verified, "sha256": digest, "filename": filename or nome}


def cestina(file_id: str, *, folder_id: str, service: Any = None) -> dict:
    """Sposta nel cestino Drive una foto canonica, dopo averne verificato la cartella."""
    service = service or build_drive_service()
    _metadata(service, file_id, folder_id=folder_id)
    service.files().update(
        fileId=file_id,
        body={"trashed": True},
        fields="id,name,mimeType,size,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    return {"id": file_id, "trashed": True}
