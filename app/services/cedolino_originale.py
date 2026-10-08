"""Accesso puntuale all'originale di un cedolino.

Il resolver mantiene compatibilità con i documenti storici incorporati e usa
Drive come archivio canonico per i nuovi import.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any, Dict


async def conserva_originale(db, content: bytes) -> str:
    """Un originale per impronta nel deposito protetto già usato dal gestionale."""
    from app.services.blob_store import blob_store_per_runtime

    store = blob_store_per_runtime(db)
    if not store.persistent:
        raise ValueError("Archivio persistente non disponibile: il PDF non è stato acquisito")
    key = "cedolino-originale:" + hashlib.sha256(content).hexdigest()
    if await store.get(key) is None:
        await store.put(key, base64.b64encode(content).decode("ascii"))
    return key


async def carica_originale(doc: Dict[str, Any]) -> bytes:
    if doc.get("blob_key"):
        from app.database import Database
        from app.services.blob_store import blob_store_per_runtime

        encoded = await blob_store_per_runtime(Database.get_db()).get(doc["blob_key"])
        content = base64.b64decode(encoded, validate=True) if encoded else b""
    elif doc.get("drive_file_id"):
        from app.services.drive_download import scarica_originale

        content = await scarica_originale(str(doc["drive_file_id"]), md5=doc.get("drive_md5"))
    else:
        ref = (doc.get("_drive_payloads") or {}).get("pdf_data") or {}
        if ref.get("drive_file_id"):
            from app.services.drive_download import scarica_originale

            content = await scarica_originale(str(ref["drive_file_id"]), md5=ref.get("md5"))
        else:
            content = b""
    encoded = doc.get("pdf_data")
    if not content and encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("PDF incorporato non decodificabile") from exc
    if not content:
        return b""
    if content and not content.startswith(b"%PDF"):
        raise ValueError("L'originale non è un PDF valido")
    if doc.get("pdf_source_scope") == "document":
        # Il Libro Unico resta un solo originale su Drive. Il download della
        # busta espone soltanto le pagine riconosciute per quella persona.
        import fitz

        try:
            start = int(doc["source_page_start"])
            end = int(doc["source_page_end"])
            expected = int(doc["source_document_pages"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Collegamento alle pagine del cedolino incompleto") from exc
        with fitz.open(stream=content, filetype="pdf") as original:
            if len(original) != expected or not 1 <= start <= end <= len(original):
                raise ValueError("Pagine del cedolino non corrispondenti all'originale")
            if start != 1 or end != len(original):
                with fitz.open() as selected:
                    selected.insert_pdf(original, from_page=start - 1, to_page=end - 1)
                    content = selected.tobytes(garbage=4, deflate=True)
    return content
