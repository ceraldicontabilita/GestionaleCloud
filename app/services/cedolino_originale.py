"""Accesso puntuale all'originale di un cedolino.

Il resolver mantiene compatibilità con i documenti storici incorporati e usa
Drive come archivio canonico per i nuovi import.
"""
from __future__ import annotations

import base64
from typing import Any, Dict


async def carica_originale(doc: Dict[str, Any]) -> bytes:
    encoded = doc.get("pdf_data")
    if encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("PDF incorporato non decodificabile") from exc
    elif doc.get("drive_file_id"):
        from app.services.drive_cedolini_ingest import download_file_by_id

        content = await download_file_by_id(str(doc["drive_file_id"]))
    else:
        return b""
    if content and not content.startswith(b"%PDF"):
        raise ValueError("L'originale non è un PDF valido")
    return content
