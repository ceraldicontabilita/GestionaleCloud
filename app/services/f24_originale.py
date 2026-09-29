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
        from app.services.drive_download import scarica_originale

        content = await scarica_originale(str(doc["drive_file_id"]), md5=doc.get("drive_md5"))
    else:
        return b""
    if content and not content.startswith(b"%PDF"):
        raise ValueError("L'originale F24 non e' un PDF valido")
    return content
