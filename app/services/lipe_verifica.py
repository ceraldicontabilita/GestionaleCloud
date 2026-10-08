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


VP_FIELDS = tuple(f"VP{number}" for number in range(2, 15))
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


def _word_center(word: dict[str, Any], axis: str) -> float:
    return (float(word[f"{axis}0"]) + float(word[f"{axis}1"])) / 2


def _layout_row_words(
    words: list[dict[str, Any]], y: float, *, x0: float, x1: float
) -> list[dict[str, Any]]:
    return sorted(
        [
            word for word in words
            if x0 <= _word_center(word, "x") <= x1
            and abs(_word_center(word, "y") - y) <= 7
            and re.fullmatch(r"[\d.,]+", str(word.get("text") or "").strip())
        ],
        key=lambda word: float(word["x0"]),
    )


def _layout_amount(
    words: list[dict[str, Any]], field: str
) -> tuple[int | None, str | None, str | None]:
    label = next(
        (word for word in words if str(word.get("text") or "").strip().upper() == field),
        None,
    )
    if not label:
        return None, None, None
    y = _word_center(label, "y")
    field_zones = {
        "VP2": (("valore", 350.0, 430.0),),
        "VP3": (("valore", 490.0, 570.0),),
        "VP4": (("debito", 350.0, 430.0),),
        "VP5": (("credito", 490.0, 570.0),),
        "VP7": (("debito", 350.0, 430.0),),
        "VP8": (("credito", 490.0, 570.0),),
        "VP9": (("credito", 490.0, 570.0),),
        "VP10": (("credito", 490.0, 570.0),),
        "VP11": (("credito", 490.0, 570.0),),
        "VP12": (("debito", 350.0, 430.0),),
        # La cifra piccola nella colonna centrale di VP13 e' il metodo
        # dell'acconto, non un importo.
        "VP13": (("debito", 490.0, 570.0),),
    }
    zones = field_zones.get(
        field, (("debito", 350.0, 430.0), ("credito", 490.0, 570.0))
    )
    for side, x0, x1 in zones:
        row = _layout_row_words(words, y, x0=x0, x1=x1)
        if not row:
            continue
        raw = "".join(str(word["text"]).strip() for word in row)
        amount = _cents(raw)
        if amount is not None:
            return amount, f"{field} {side} {raw}", side
    return None, None, None


def _layout_month(words: list[dict[str, Any]]) -> int | None:
    label = next(
        (word for word in words if str(word.get("text") or "").strip().upper() == "VP1"),
        None,
    )
    if not label:
        return None
    row = _layout_row_words(words, _word_center(label, "y"), x0=140.0, x1=190.0)
    digits = "".join(str(word["text"]).strip() for word in row)
    return int(digits) if digits.isdigit() and 1 <= int(digits) <= 12 else None


def parse_lipe_page(
    text: str, *, layout_words: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Legge un singolo modulo VP; senza mese certo il risultato resta sospeso."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    normalized = " ".join(lines)
    month_match = (
        re.search(r"\bVP1\b.{0,100}?\bMese\s*[:.]?\s*(0?[1-9]|1[0-2])\b", normalized, re.I)
        or re.search(r"\bMese\s*[:.]?\s*(0?[1-9]|1[0-2])\b", normalized, re.I)
    )
    layout_month = _layout_month(layout_words or [])
    month = layout_month
    if month is None:
        month = int(month_match.group(1)) if month_match else None
    values: dict[str, int] = {}
    raw_evidence: dict[str, str] = {}
    value_sides: dict[str, str] = {}
    layout_fields = 0
    for field in VP_FIELDS:
        amount, raw, side = _layout_amount(layout_words or [], field)
        if amount is not None:
            layout_fields += 1
        # Con coordinate native una casella vuota resta vuota. Il fallback
        # lineare potrebbe catturare numeri presenti nella descrizione del
        # rigo (es. "25,82 euro" in VP7) e trasformarli in falsi importi.
        if amount is None and not layout_words:
            amount, raw = _field_amount(lines, field)
        if amount is None and layout_words and field in {"VP4", "VP5"} and any(
            str(word.get("text") or "").strip().upper() == field for word in layout_words
        ):
            # Nei modelli AdE una casella monetaria presente ma vuota vale
            # zero. La regola e' limitata a VP4/VP5, necessari alla prima
            # quadratura, e richiede l'etichetta nativa del campo.
            amount, raw = 0, f"{field} casella_vuota=0"
        if amount is not None:
            values[f"{field.lower()}_cents"] = amount
            raw_evidence[field] = raw or ""
            if side and field in {"VP6", "VP14"}:
                value_sides[f"{field.lower()}_side"] = side
    quadrature: dict[str, bool] = {}
    if "vp4_cents" in values and "vp5_cents" in values and "vp6_cents" in values:
        delta = values["vp4_cents"] - values["vp5_cents"]
        quadrature["vp6"] = (
            abs(delta) == values["vp6_cents"]
            and value_sides.get("vp6_side") == ("debito" if delta >= 0 else "credito")
        )
    if "vp6_cents" in values and "vp14_cents" in values and value_sides.get("vp6_side"):
        net = values["vp6_cents"] * (1 if value_sides["vp6_side"] == "debito" else -1)
        net += values.get("vp7_cents", 0)
        net -= sum(values.get(f"vp{number}_cents", 0) for number in range(8, 12))
        # VP12 (interessi) aumenta il dovuto; VP13 (acconto gia' dovuto)
        # riduce invece il saldo residuo esposto in VP14.
        net += values.get("vp12_cents", 0) - values.get("vp13_cents", 0)
        quadrature["vp14"] = (
            abs(net) == values["vp14_cents"]
            and value_sides.get("vp14_side") == ("debito" if net >= 0 else "credito")
        )
    complete = month and "vp4_cents" in values and "vp5_cents" in values
    confidence = 1.0 if complete else 0.6
    if quadrature and not all(quadrature.values()):
        confidence = min(confidence, 0.7)
    return {
        "month": month,
        "values": {**values, **value_sides},
        "raw_evidence": raw_evidence,
        "parse_method": "pdf_layout" if layout_month and layout_fields else "linear_text",
        "quadrature": quadrature,
        "confidence": confidence,
    }


def parse_lipe_modules(
    text: str, *, layout_words: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Una pagina può contenere più moduli VP: li mantiene separati."""
    if layout_words:
        parsed = parse_lipe_page(text, layout_words=layout_words)
        return [parsed] if parsed["month"] or parsed["values"] else []
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
            for parsed in parse_lipe_modules(
                page_text, layout_words=page.get("layout_words") or None
            ):
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
                    "parser_version": "lipe-vp-v3-layout-aware",
                    "parse_method": parsed.get("parse_method"),
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
