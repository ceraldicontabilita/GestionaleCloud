"""Archivio canonico Supabase Storage delle immagini ricette."""

from __future__ import annotations

import hashlib
import re
import uuid

from app.menu.supabase_client import supabase


BUCKET = "menu-images"
PREFIX = "lotti/ricette"


def _estensione(mime: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(str(mime or "").split(";", 1)[0].casefold(), "img")


def carica(*, ricetta_id: str, contenuto: bytes, mime: str, filename: str | None = None) -> dict:
    if not str(mime or "").casefold().startswith("image/"):
        raise ValueError("File non è un'immagine")
    digest = hashlib.sha256(contenuto).hexdigest()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(ricetta_id)).strip("._") or "ricetta"
    foto_id = f"{safe}_{uuid.uuid4().hex}"
    percorso = f"{PREFIX}/{foto_id}.{_estensione(mime)}"
    supabase.storage.from_(BUCKET).upload(
        percorso,
        contenuto,
        {"content-type": mime, "upsert": "false"},
    )
    return {
        "id": foto_id,
        "bucket": BUCKET,
        "path": percorso,
        "sha256": digest,
        "filename": filename,
    }


def leggi(percorso: str) -> bytes:
    return bytes(supabase.storage.from_(BUCKET).download(percorso))


def elimina(percorso: str) -> None:
    supabase.storage.from_(BUCKET).remove([percorso])


def url_pubblico(percorso: str) -> str:
    return supabase.storage.from_(BUCKET).get_public_url(percorso)
