"""Originale di un modello o di una quietanza F24: lo stesso lettore dei cedolini.

Era una copia di ``cedolino_originale`` (stessa logica, un messaggio diverso):
un lettore solo (DRV-04). Il parametro ``tipo`` resta per compatibilita' dei
chiamanti e non cambia il comportamento.
"""
from __future__ import annotations

from typing import Any, Dict
import hashlib
import logging

from app.services.cedolino_originale import carica_originale as _carica

__all__ = ["carica_originale"]
logger = logging.getLogger(__name__)


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


def _stessa_quietanza(doc: Dict[str, Any], content: bytes) -> bool:
    """Una ristampa puo' avere byte diversi, ma deve provare la stessa delega."""
    from app.services.f24_parser import parse_quietanza_f24
    from app.services.dilazioni_inps import _firma_delega_pagata

    parsed = parse_quietanza_f24(pdf_content=content)
    if not parsed or (parsed.get("validazione") or {}).get("saldo_quadrato") is not True:
        return False
    g = parsed.get("dati_generali") or {}
    originale_protocollo = doc.get("protocollo_telematico") or (doc.get("dati_generali") or {}).get("protocollo_telematico")
    if originale_protocollo and g.get("protocollo_telematico") and originale_protocollo != g["protocollo_telematico"]:
        return False
    copia = {**parsed, "codice_fiscale": g.get("codice_fiscale"),
             "data_pagamento": g.get("data_pagamento"), "saldo": g.get("saldo_delega")}
    firma = _firma_delega_pagata(doc)
    return bool(firma and firma == _firma_delega_pagata(copia))


async def recupera_copia_quietanza(db, doc: Dict[str, Any]) -> Dict[str, Any] | None:
    """Recupera solo fonti gia' associate, verificando byte e contenuto fiscale.

    Gli upload duplicati possono essere nell'archivio degli originali senza
    un nuovo drive_file_id sulla quietanza. La copia viene aperta senza
    modificare il pagamento, il protocollo o la provenienza iniziale.
    """
    from app.services import drive_cartella_unica as cu
    from app.services.drive_download import scarica_originale

    expected = doc.get("pdf_hash") or doc.get("sha256")
    refs = [{"sha256": expected}, *reversed(doc.get("source_occurrences") or [])]
    seen = set()
    for ref in refs:
        sha = str(ref.get("sha256") or "")
        if len(sha) != 64 or sha in seen:
            continue
        seen.add(sha)
        try:
            archiviato = await cu.originale(db, sha256=sha)
        except RuntimeError as exc:
            logger.warning("Copia quietanza non recuperata dall'archivio (%s)", type(exc).__name__)
            archiviato = None
        content = (archiviato or {}).get("contenuto")
        if not content and ref.get("drive_file_id"):
            content = await scarica_originale(str(ref["drive_file_id"]), md5=ref.get("md5"))
        if not content or not content.startswith(b"%PDF") or hashlib.sha256(content).hexdigest() != sha:
            continue
        if sha == expected or _stessa_quietanza(doc, content):
            return {"contenuto": content, "nome": (archiviato or {}).get("nome")}
    return None
