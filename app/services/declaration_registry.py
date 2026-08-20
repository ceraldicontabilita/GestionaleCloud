"""Vista dichiarazioni con collegamenti probatori verso F24, quietanze e banca."""

from __future__ import annotations

import re
from typing import Any

from app.db_collections import COLL_FISCAL_DOCUMENTS
from app.services.tax_payment_query import TaxPaymentQueryService


DECLARATION_TYPES = {
    "MODELLO_770", "DICHIARAZIONE_IVA", "LIPE", "REDDITI_SC",
    "DICHIARAZIONE_IRAP", "ELENCO_PERCIPIENTI",
}

TAX_CODES = {
    "MODELLO_770": {"1001", "1002", "1012", "1040", "1045", "1051", "1052", "1301", "1601", "1901", "1920", "3802", "3848"},
    "DICHIARAZIONE_IVA": {"6001", "6002", "6003", "6004", "6005", "6006", "6007", "6008", "6009", "6010", "6011", "6012", "6013", "6031", "6032", "6033", "6034", "6035", "6099"},
    "LIPE": {"6001", "6002", "6003", "6004", "6005", "6006", "6007", "6008", "6009", "6010", "6011", "6012", "6031", "6032", "6033", "6034"},
    "DICHIARAZIONE_IRAP": {"3800", "3812", "3813"},
    "REDDITI_SC": {"2001", "2002", "2003"},
}


def _year(value: Any) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group()) if match else None


def declaration_metadata(document: dict[str, Any]) -> dict[str, Any]:
    filename = str(document.get("filename") or "")
    source = document.get("source_metadata") or {}
    filing_year = _year(source.get("filing_year") or source.get("archive_relative_path") or filename)
    tax_match = re.search(r"imposta[_ -]?((?:19|20)\d{2})", filename, re.I)
    tax_year = int(tax_match.group(1)) if tax_match else _year(source.get("tax_year"))
    if tax_year is None and filing_year:
        tax_year = filing_year if document.get("document_type") == "LIPE" else filing_year - 1
    protocol_match = re.search(r"(?:^|[^A-Z0-9])(T\d{12,})(?!\d)", filename, re.I)
    return {
        **document,
        "filing_year": filing_year,
        "tax_year": tax_year,
        "protocol": source.get("protocol") or (protocol_match.group(1) if protocol_match else None),
    }


def _reference_year(row: dict[str, Any]) -> int | None:
    return _year(row.get("reference_period") or row.get("anno_riferimento") or row.get("anno"))


async def list_declaration_dossiers(db, *, company_id: str, year: int | None = None,
                                    declaration_type: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"company_id": company_id, "document_type": {"$in": sorted(DECLARATION_TYPES)}}
    if declaration_type:
        query["document_type"] = declaration_type
    documents = await db[COLL_FISCAL_DOCUMENTS].find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    f24_documents = await TaxPaymentQueryService(db).list_documents()
    dossiers = []
    for raw in documents:
        declaration = declaration_metadata(raw)
        if year and declaration["filing_year"] != year and declaration["tax_year"] != year:
            continue
        allowed = TAX_CODES.get(declaration["document_type"], set())
        candidates = []
        for f24 in f24_documents:
            rows = [row for row in f24.get("righe_tributo_normalizzate", [])
                    if row.get("tax_code") in allowed and (
                        declaration["tax_year"] is None or _reference_year(row) == declaration["tax_year"]
                    )]
            if not rows:
                continue
            chain = f24.get("payment_chain") or {}
            relations = chain.get("relations") or []
            declaration_id = str(declaration.get("id") or "")
            confirmed = any(
                relation.get("status") == "confirmed" and declaration_id in {
                    str((relation.get("source") or {}).get("id") or ""),
                    str((relation.get("target") or {}).get("id") or ""),
                } for relation in relations
            )
            candidates.append({
                "f24_id": f24.get("id"),
                "filename": f24.get("file_name") or f24.get("filename"),
                "tax_rows": rows,
                "link_status": "CONFIRMED" if confirmed else "CANDIDATE_TO_VERIFY",
                "quietanza": chain.get("receipt"),
                "quietanza_candidates": chain.get("receipt_candidates") or [],
                "bank_movement": chain.get("bank_movement"),
                "bank_status": (chain.get("axes") or {}).get("bank", "NON_VERIFICATA"),
                "documentary_payment_status": (chain.get("axes") or {}).get("document_evidence", "QUIETANZA_NON_PRESENTE"),
            })
        declaration["f24_links"] = candidates
        declaration["f24_confirmed_count"] = sum(item["link_status"] == "CONFIRMED" for item in candidates)
        declaration["f24_candidate_count"] = sum(item["link_status"] != "CONFIRMED" for item in candidates)
        dossiers.append(declaration)
    return dossiers
