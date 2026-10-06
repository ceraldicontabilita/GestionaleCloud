"""Accesso puntuale all'originale di un cedolino.

Il resolver mantiene compatibilità con i documenti storici incorporati e usa
Drive come archivio canonico per i nuovi import.
"""
from __future__ import annotations

import base64
from typing import Any, Dict


async def carica_originale(doc: Dict[str, Any]) -> bytes:
    if doc.get("drive_file_id"):
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
    return content
