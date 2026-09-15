"""Regole comuni per leggere il registro documentale senza allegati pesanti.

I documenti completi restano autorevoli in Supabase.  Liste, dashboard e
riconciliazioni lavorano sui soli metadati; dettaglio e download richiedono
invece esplicitamente i campi originali.  Tenere questa mappa in un unico
punto evita che ogni router inventi una proiezione diversa.
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
    COLL_DOCUMENTS_INBOX: ("pdf_data",),
    COLL_CEDOLINI: ("pdf_data",),
    COLL_QUIETANZE_F24: ("pdf_data",),
    COLL_BONIFICI_TRANSFERS: ("pdf_data",),
    COLL_F24_UNIFICATO: ("pdf_data",),
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
