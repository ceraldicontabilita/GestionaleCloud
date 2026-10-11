"""Accesso puntuale all'originale di un cedolino.

Il resolver mantiene compatibilità con i documenti storici incorporati e usa
Drive come archivio canonico per i nuovi import.
"""
from __future__ import annotations

import base64
import asyncio
from typing import Any, Dict


def _pagine_della_busta(content: bytes, doc: Dict[str, Any]) -> bytes:
    total = doc.get("source_document_pages")
    start, end = doc.get("source_page_start"), doc.get("source_page_end")
    if total is None and start is None and end is None:
        return content
    try:
        total, start, end = int(total), int(start), int(end)
        if not 1 <= start <= end <= total:
            raise ValueError("Intervallo pagine non valido")
        import fitz

        with fitz.open(stream=content, filetype="pdf") as original:
            if len(original) == total:
                with fitz.open() as selected:
                    selected.insert_pdf(original, from_page=start - 1, to_page=end - 1)
                    return selected.tobytes()
            if len(original) == end - start + 1:
                return content  # Copia della busta gia' separata dal fascicolo.
            raise ValueError("Numero di pagine diverso dal fascicolo registrato")
    except (TypeError, ValueError) as exc:
        raise ValueError("Impossibile individuare le pagine del cedolino nell'originale") from exc


async def carica_originale(doc: Dict[str, Any]) -> bytes:
    if (doc.get("drive_file_id") and doc.get("gestionale_cedolino_id")
            and not doc.get("source_document_pages")):
        # Le copie HR precedenti non conservavano le pagine. Il collegamento
        # per id e lo stesso file Drive permettono di recuperarle senza una
        # nuova importazione e senza modificare importi o anagrafiche.
        from app.database import Database

        source = await Database.get_db()["cedolini"].find_one(
            {"id": doc["gestionale_cedolino_id"], "drive_file_id": doc["drive_file_id"]},
            {"_id": 0, "source_page_start": 1, "source_page_end": 1, "source_document_pages": 1},
        )
        if source and source.get("source_document_pages"):
            doc = {**doc, **source}
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
    return await asyncio.to_thread(_pagine_della_busta, content, doc)
