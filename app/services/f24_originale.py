"""Originale di un modello o di una quietanza F24: lo stesso lettore dei cedolini.

Era una copia di ``cedolino_originale`` (stessa logica, un messaggio diverso):
un lettore solo (DRV-04). Il parametro ``tipo`` resta per compatibilita' dei
chiamanti e non cambia il comportamento.
"""
from __future__ import annotations

from typing import Any, Dict
import hashlib

from app.services.cedolino_originale import carica_originale as _carica

__all__ = ["carica_originale"]


async def carica_originale(doc: Dict[str, Any], *, tipo: str = "f24") -> bytes:
    content = await _carica(doc)
    if content:
        return content
    # La stessa quietanza puo' essere arrivata da piu' canali. Se il primo
    # file Drive non esiste piu', usa solo una copia con la stessa impronta.
    expected = str(doc.get("pdf_hash") or doc.get("sha256") or "")
    if len(expected) != 64:
        return b""
    from app.services.drive_download import scarica_originale
    seen = {doc.get("drive_file_id")}
    refs = list(doc.get("source_occurrences") or [])
    payload = (doc.get("_drive_payloads") or {}).get("pdf_data") or {}
    if payload.get("drive_file_id"):
        refs.insert(0, {**payload, "sha256": expected})
    mismatch = False
    for ref in refs:
        ident = ref.get("drive_file_id")
        if not ident or ident in seen or ref.get("sha256") != expected:
            continue
        seen.add(ident)
        candidate = await scarica_originale(str(ident), md5=ref.get("md5"))
        if candidate and candidate.startswith(b"%PDF") and hashlib.sha256(candidate).hexdigest() == expected:
            return candidate
        mismatch = mismatch or bool(candidate)
    if mismatch:
        raise ValueError("Le copie disponibili non corrispondono all'impronta dell'originale")
    return b""
