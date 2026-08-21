"""Estrazione probatoria dei valori mensili dalle comunicazioni LIPE.

Il parser non modifica i documenti e non associa automaticamente periodi
ambigui. Ogni valore restituito conserva documento, versione e pagina.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.config import settings
from app.db_collections import COLL_FISCAL_DOCUMENTS, COLL_FISCAL_PAGES


VP_FIELDS = ("VP4", "VP5", "VP6", "VP8", "VP9", "VP10", "VP11", "VP12", "VP13", "VP14")
_AMOUNT = re.compile(r"(?<![\d.,])([+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})|[+-]?\d+\.\d{2})(?![\d.,])")


def _cents(raw: str) -> int | None:
    value = raw.strip().replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _field_amount(lines: list[str], field: str) -> tuple[int | None, str | None]:
    for index, line in enumerate(lines):
        if not re.search(rf"\b{field}\b", line, re.I):
            continue
        window = " ".join(lines[index:index + 3])
        after_field = re.split(rf"\b{field}\b", window, maxsplit=1, flags=re.I)[-1]
        matches = _AMOUNT.findall(after_field)
        if matches:
            return _cents(matches[0]), window[:240]
    return None, None


def parse_lipe_page(text: str) -> dict[str, Any]:
    """Legge un singolo modulo VP; senza mese certo il risultato resta sospeso."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    normalized = " ".join(lines)
    month_match = (
        re.search(r"\bVP1\b.{0,100}?\bMese\s*[:.]?\s*(0?[1-9]|1[0-2])\b", normalized, re.I)
        or re.search(r"\bMese\s*[:.]?\s*(0?[1-9]|1[0-2])\b", normalized, re.I)
    )
    month = int(month_match.group(1)) if month_match else None
    values: dict[str, int] = {}
    raw_evidence: dict[str, str] = {}
    for field in VP_FIELDS:
        amount, raw = _field_amount(lines, field)
        if amount is not None:
            values[f"{field.lower()}_cents"] = amount
            raw_evidence[field] = raw or ""
    return {
        "month": month,
        "values": values,
        "raw_evidence": raw_evidence,
        "confidence": 1.0 if month and "vp4_cents" in values and "vp5_cents" in values else 0.6,
    }


def parse_lipe_modules(text: str) -> list[dict[str, Any]]:
    """Una pagina può contenere più moduli VP: li mantiene separati."""
    chunks = re.split(r"(?=\bVP1\b)", str(text or ""), flags=re.I)
    parsed = [parse_lipe_page(chunk) for chunk in chunks if chunk.strip()]
    return [item for item in parsed if item["month"] or item["values"]]


def _document_year(document: dict[str, Any], page_text: str) -> int | None:
    metadata = document.get("source_metadata") or {}
    for value in (
        metadata.get("tax_year"), metadata.get("filing_year"),
        document.get("tax_year"), document.get("filing_year"),
    ):
        if str(value or "").isdigit() and len(str(value)) == 4:
            return int(value)
    match = re.search(r"(?:19|20)\d{2}", f"{document.get('filename') or ''} {page_text[:500]}")
    return int(match.group()) if match else None


async def list_lipe_monthly_evidence(db, *, year: int, company_id: str | None = None) -> dict[int, dict[str, Any]]:
    company_id = company_id or settings.FISCAL_COMPANY_ID
    query: dict[str, Any] = {"document_type": "LIPE"}
    if company_id:
        query["company_id"] = company_id
    documents = await db[COLL_FISCAL_DOCUMENTS].find(query, {"_id": 0}).to_list(5000)
    candidates: dict[int, list[dict[str, Any]]] = {}
    for document in documents:
        pages = await db[COLL_FISCAL_PAGES].find(
            {"document_id": document.get("id")}, {"_id": 0}
        ).to_list(500)
        for page in pages:
            page_text = page.get("text") or ""
            declared_year = _document_year(document, page_text)
            if declared_year != year:
                continue
            for parsed in parse_lipe_modules(page_text):
                month = parsed["month"]
                if not month:
                    continue
                candidates.setdefault(month, []).append({
                    **parsed["values"],
                    "document_id": document.get("id"),
                    "version_id": page.get("version_id") or document.get("current_version_id"),
                    "page_number": page.get("page_number"),
                    "filename": document.get("filename"),
                    "confidence": min(
                        parsed["confidence"],
                        float(page.get("ocr_confidence") or 1.0),
                    ),
                    "text_source": page.get("text_source") or "pdf_text",
                    "ocr_used": bool(page.get("ocr_used")),
                    "parser_version": "lipe-vp-v2-ocr-aware",
                    "raw_evidence": parsed["raw_evidence"],
                })

    result: dict[int, dict[str, Any]] = {}
    for month in range(1, 13):
        items = candidates.get(month, [])
        if not items:
            result[month] = {"stato": "LIPE_NON_PRESENTE", "candidati": []}
        elif len(items) > 1:
            result[month] = {"stato": "LIPE_AMBIGUA", "candidati": items}
        elif items[0].get("confidence", 0) < 1:
            result[month] = {"stato": "LIPE_DA_VERIFICARE", "candidati": items, **items[0]}
        else:
            result[month] = {"stato": "LIPE_ESTRATTA", "candidati": items, **items[0]}
    return result
