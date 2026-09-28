"""Foto dell'assegno: stessa scelta di archiviazione delle foto ricette
(Supabase Storage, bucket condiviso ``menu-images``), un prefisso diverso.
Una foto sola per assegno, non una galleria: un nuovo upload sostituisce i
campi sull'assegno, l'oggetto precedente non si cancella da solo.
"""

from __future__ import annotations

import hashlib
import re
import uuid

from app.menu.supabase_client import supabase

BUCKET = "menu-images"
PREFIX = "bank/assegni"


def _estensione(mime: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(str(mime or "").split(";", 1)[0].casefold(), "img")


def carica(*, assegno_id: str, contenuto: bytes, mime: str, filename: str | None = None) -> dict:
    if not str(mime or "").casefold().startswith("image/"):
        raise ValueError("File non è un'immagine")
    digest = hashlib.sha256(contenuto).hexdigest()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(assegno_id)).strip("._") or "assegno"
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
