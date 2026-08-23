"""Estrazione e confronto probatorio dei campi delle dichiarazioni fiscali.

Il parser e' deliberatamente conservativo: una sequenza di numeri non diventa
un dato fiscale finche' la struttura del modello e le relazioni aritmetiche non
ne rendono univoca la semantica. Ogni valore conserva pagina e testo sorgente.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


PARSER_VERSION = "770-st-sv-v1"
CERTAIN = "ESTRATTO_CON_CERTEZZA"
REVIEW = "DA_VERIFICARE"
EXACT = "CONCORDANTE"
MISSING_F24 = "MANCANTE_F24"
AMBIGUOUS_F24 = "AMBIGUO_F24"
NOT_EXTRACTED = "NON_ESTRAIBILE_CON_CERTEZZA"

_PAGE_RE = re.compile(r"\[PAGINA\s+(\d+)\]\s*", re.I)
_ROW_RE = re.compile(
    r"(?m)^\s*(?P<month>0[1-9]|1[0-2])\s+(?P<year>20\d{2})\s+"
    r"(?P<amounts>\d[\d.]*,\d{2}(?:\s+\d[\d.]*,\d{2}){0,5})\s*\r?\n"
    r"(?P<flags>(?:[A-Z]\s+)*)?(?P<tax_code>\d{4})\s+"
    r"(?P<day>0[1-9]|[12]\d|3[01])\s+(?P<payment_month>0[1-9]|1[0-2])\s+"
    r"(?P<payment_year>20\d{2})\s*$"
)


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _cents(value: Any) -> int:
    try:
        return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _period(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"(?:(0[1-9]|1[0-2])\D*(20\d{2})|(20\d{2})\D*(0[1-9]|1[0-2]))", text)
    if match:
        month = match.group(1) or match.group(4)
        year = match.group(2) or match.group(3)
        return f"{year}-{month}"
    year = re.search(r"20\d{2}", text)
    return year.group() if year else text.upper()


def _page_sections(text: str) -> list[tuple[int | None, str]]:
    matches = list(_PAGE_RE.finditer(text or ""))
    if not matches:
        return [(None, text or "")]
    return [
        (int(match.group(1)), text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)])
        for index, match in enumerate(matches)
    ]


def _certain_770_amounts(amounts: list[Decimal], flags: str) -> tuple[bool, dict[str, Decimal], str]:
    """Assegna significato solo quando il modello si auto-verifica al centesimo."""
    ravvedimento = "X" in flags.upper().split()
    if not ravvedimento and len(amounts) == 1:
        return True, {"withholding": amounts[0], "paid": amounts[0], "interest": Decimal("0")}, "versamento_ordinario_unico"
    if not ravvedimento and len(amounts) == 2 and amounts[0] == amounts[1]:
        return True, {"withholding": amounts[0], "paid": amounts[1], "interest": Decimal("0")}, "versamento_ordinario_importi_uguali"
    if ravvedimento and len(amounts) == 3 and amounts[1] - amounts[0] == amounts[2]:
        return True, {"withholding": amounts[0], "paid": amounts[1], "interest": amounts[2]}, "ravvedimento_quadrato_al_centesimo"
    return False, {}, "colonne_o_aritmetica_non_univoche"


def extract_770_tax_rows(text: str, *, document_id: str, filename: str | None = None,
                         sha256: str | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for page_number, page_text in _page_sections(text):
        # La stessa forma numerica puo' comparire in altri quadri: il contesto
        # ST/SV e' parte obbligatoria della prova semantica.
        if not re.search(r"\bQUADRO\s+(?:ST|SV)\b", page_text, re.I):
            continue
        for ordinal, match in enumerate(_ROW_RE.finditer(page_text), start=1):
            raw = match.group(0).strip()
            amounts = [_decimal(value) for value in re.findall(r"\d[\d.]*,\d{2}", match.group("amounts"))]
            certain, semantics, reason = _certain_770_amounts(amounts, match.group("flags") or "")
            base = {
                "document_id": document_id,
                "filename": filename,
                "sha256": sha256,
                "page_number": page_number,
                "source_text": raw,
                "parser_version": PARSER_VERSION,
                "tax_code": match.group("tax_code"),
                "reference_period": f"{match.group('year')}-{match.group('month')}",
                "payment_date": f"{match.group('payment_year')}-{match.group('payment_month')}-{match.group('day')}",
                "flags": " ".join((match.group("flags") or "").split()),
                "raw_amounts": [_money(value) for value in amounts],
                "certainty_reason": reason,
            }
            identity = "|".join((document_id, str(page_number or ""), str(ordinal), raw))
            base["id"] = f"declaration-tax-row:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
            if not certain:
                rejected.append({**base, "extraction_status": REVIEW})
                continue
            paid = semantics["paid"]
            rows.append({
                **base,
                "extraction_status": CERTAIN,
                "withholding_amount": _money(semantics["withholding"]),
                "paid_amount": _money(paid),
                "interest_amount": _money(semantics["interest"]),
                "debit_amount": _money(paid),
                "credit_amount": 0.0,
            })
    return {
        "document_id": document_id,
        "document_type": "MODELLO_770",
        "parser_version": PARSER_VERSION,
        "tax_rows": rows,
        "rejected_rows": rejected,
        "extracted_with_certainty": len(rows),
        "requires_review": len(rejected),
        "field_level_status": CERTAIN if rows and not rejected else REVIEW,
    }


def extract_declaration_fields(content: bytes, *, document_type: str, document_id: str,
                               filename: str | None = None, sha256: str | None = None) -> dict[str, Any]:
    from app.services.pdf_text_extraction import extract_pdf_text

    digest = hashlib.sha256(content).hexdigest()
    if sha256 and digest.casefold() != str(sha256).casefold():
        return {
            "document_id": document_id, "document_type": document_type,
            "tax_rows": [], "rejected_rows": [], "extracted_with_certainty": 0,
            "requires_review": 1, "field_level_status": "HASH_DOCUMENTO_NON_COINCIDENTE",
            "expected_sha256": sha256, "actual_sha256": digest,
        }
    text = extract_pdf_text(content, max_pages=None)
    if document_type == "MODELLO_770":
        return extract_770_tax_rows(text, document_id=document_id, filename=filename, sha256=digest)
    return {
        "document_id": document_id, "document_type": document_type,
        "tax_rows": [], "rejected_rows": [], "extracted_with_certainty": 0,
        "requires_review": 1, "field_level_status": NOT_EXTRACTED,
        "parser_version": None,
    }


def reconcile_declaration_tax_rows(extraction: dict[str, Any],
                                   f24_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_signature: dict[tuple[str, str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in f24_rows:
        signature = (
            str(row.get("tax_code") or row.get("Codice tributo") or "").strip(),
            _period(row.get("reference_period") or row.get("Periodo tributo")),
            _cents(row.get("debit_amount") if "debit_amount" in row else row.get("Debito")),
            _cents(row.get("credit_amount") if "credit_amount" in row else row.get("Credito")),
        )
        by_signature[signature].append(row)

    items = []
    for row in extraction.get("tax_rows") or []:
        signature = (
            str(row.get("tax_code") or ""), _period(row.get("reference_period")),
            _cents(row.get("debit_amount")), _cents(row.get("credit_amount")),
        )
        candidates = by_signature.get(signature, [])
        status = EXACT if len(candidates) == 1 else AMBIGUOUS_F24 if candidates else MISSING_F24
        items.append({
            "id": f"declaration-match:{row['id']}",
            "status": status,
            "requires_review": status != EXACT,
            "declaration_row": row,
            "f24_row": candidates[0] if len(candidates) == 1 else None,
            "candidate_count": len(candidates),
            "rule": "codice_tributo+periodo+debito_cents+credito_cents",
        })
    for row in extraction.get("rejected_rows") or []:
        items.append({
            "id": f"declaration-match:{row['id']}", "status": NOT_EXTRACTED,
            "requires_review": True, "declaration_row": row, "f24_row": None,
            "candidate_count": 0, "rule": "semantica_colonne_e_aritmetica_prima_del_match",
        })
    counts = Counter(item["status"] for item in items)
    return {
        "items": items,
        "counts": dict(sorted(counts.items())),
        "certain": counts[EXACT],
        "requires_review": sum(item["requires_review"] for item in items),
        "all_certain": bool(items) and all(not item["requires_review"] for item in items),
        "semantics": {
            "amount_only_match_allowed": False,
            "source_page_required": True,
            "source_text_required": True,
            "exact_cents": True,
            "bank_payment_proven": False,
        },
    }
