"""Regole comuni per leggere il registro documentale senza allegati pesanti.

Gli originali PDF restano autorevoli su Drive; Supabase conserva metadati e
riferimenti verificabili. Liste e dashboard lavorano sui soli metadati, mentre
il runtime ricostruisce temporaneamente il payload soltanto per i lettori che
lo chiedono esplicitamente.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.db_collections import (
    COLL_BONIFICI_TRANSFERS,
    COLL_CEDOLINI,
    COLL_DOCUMENTS_INBOX,
    COLL_F24_UNIFICATO,
    COLL_INVOICES,
    COLL_QUIETANZE_F24,
)


DOCUMENT_PAYLOAD_FIELDS: Mapping[str, tuple[str, ...]] = {
    "protocollo_personale": ("testo_ocr",),
    # PDF originale del verbale (AV3-09: ~346 KB in base64 su 141 righe, circa 49 MB):
    # una lista di verbali non lo porta, si legge per id.
    "verbali_noleggio": ("pdf_data", "pdf_quietanza", "quietanza_pdf"),
    COLL_DOCUMENTS_INBOX: ("pdf_data",),
    COLL_CEDOLINI: ("pdf_data",),
    COLL_QUIETANZE_F24: ("pdf_data",),
    COLL_BONIFICI_TRANSFERS: ("pdf_data",),
    COLL_F24_UNIFICATO: ("pdf_data",),
    "verbali_email_attachments": ("pdf_data",),
    "f24_email_attachments": ("pdf_data",),
    "ricevute_pagopa": ("pdf_data",),
    "documenti_non_associati": ("pdf_data",),
    "estratto_conto_nexi": ("pdf_data",),
    "schede_tecniche_email_attachments": ("pdf_data",),
    "bonifici_email_attachments": ("pdf_data",),
    "dichiarazioni_iva_email_attachments": ("pdf_data",),
    "cartelle_email_attachments": ("pdf_data",),
    "atti_giudiziari": ("contenuto_b64",),
    "cartelle_pagamento": ("contenuto_b64",),
    "estratti_conto_originali": ("contenuto_b64",),
    COLL_INVOICES: (
        "fattura_allegata",
        "document_original_ref",
        "xml_raw",
        "foto",
    ),
}


def metadata_projection(
    collection: str,
    projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Proiezione Mongo-compatibile per una lettura priva di payload binari.

    Accetta soltanto proiezioni di esclusione. Una proiezione di inclusione
    seleziona gia' i campi necessari e viene restituita invariata.
    """
    result = dict(projection or {"_id": 0})
    included = [key for key, value in result.items() if key != "_id" and value]
    if included:
        return result
    result.setdefault("_id", 0)
    for field in DOCUMENT_PAYLOAD_FIELDS.get(collection, ()):
        result[field] = 0
    return result
