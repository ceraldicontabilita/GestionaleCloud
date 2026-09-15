"""Accesso puntuale agli originali di modelli e quietanze F24.

Drive e' l'archivio canonico; ``pdf_data`` resta soltanto come compatibilita'
temporanea per gli upload storici non ancora collegati a Drive.
"""
from __future__ import annotations

import base64
from typing import Any, Dict


async def carica_originale(doc: Dict[str, Any], *, tipo: str = "f24") -> bytes:
    encoded = doc.get("pdf_data")
    if encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("PDF F24 incorporato non decodificabile") from exc
    elif doc.get("drive_file_id"):
        if tipo == "quietanza":
            from app.services.drive_quietanze_ingest import download_file_by_id
        else:
            from app.services.drive_f24_ingest import download_file_by_id
        content = await download_file_by_id(str(doc["drive_file_id"]))
    else:
        return b""
    if content and not content.startswith(b"%PDF"):
        raise ValueError("L'originale F24 non e' un PDF valido")
    return content
