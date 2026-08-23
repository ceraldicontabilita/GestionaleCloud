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
LIPE_PARSER_VERSION = "lipe-vp-v4-drive-layout"
IVA_PARSER_VERSION = "iva-vl-vx-v1-drive-layout"
CERTAIN = "ESTRATTO_CON_CERTEZZA"
REVIEW = "DA_VERIFICARE"
EXACT = "CONCORDANTE"
MISSING_F24 = "MANCANTE_F24"
AMBIGUOUS_F24 = "AMBIGUO_F24"
NOT_EXTRACTED = "NON_ESTRAIBILE_CON_CERTEZZA"
DISCORDANT = "DISCORDANTE"
MANAGEMENT_UNAVAILABLE = "GESTIONALE_NON_VERIFICABILE"

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


def _fitz_pages(content: bytes) -> list[tuple[int, str, list[dict[str, Any]]]]:
    """Restituisce testo e coordinate native senza OCR o ricostruzioni."""
    import fitz

    pages = []
    document = fitz.open(stream=content, filetype="pdf")
    try:
        for index, page in enumerate(document):
            words = [{
                "x0": word[0], "y0": word[1], "x1": word[2], "y1": word[3],
                "text": word[4],
            } for word in page.get_text("words", sort=True)]
            pages.append((index + 1, page.get_text("text", sort=True), words))
    finally:
        document.close()
    return pages


def _row_identity(document_id: str, page_number: int | None, ordinal: int, raw: str) -> str:
    identity = "|".join((document_id, str(page_number or ""), str(ordinal), raw))
    return f"declaration-tax-row:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def extract_lipe_fields(content: bytes, *, document_id: str, tax_year: int | None,
                        filename: str | None = None, sha256: str | None = None) -> dict[str, Any]:
    """Estrae moduli VP solo da coordinate native e quadrature complete."""
    from app.services.lipe_verifica import parse_lipe_page

    modules: list[dict[str, Any]] = []
    tax_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for page_number, text, words in _fitz_pages(content):
        if not any(str(word.get("text") or "").strip().upper() == "VP1" for word in words):
            continue
        parsed = parse_lipe_page(text, layout_words=words)
        values = parsed.get("values") or {}
        required = {"vp4_cents", "vp5_cents", "vp6_cents", "vp14_cents", "vp6_side", "vp14_side"}
        quadrature = parsed.get("quadrature") or {}
        certain = (
            parsed.get("parse_method") == "pdf_layout"
            and parsed.get("month") in range(1, 13)
            and required.issubset(values)
            and quadrature.get("vp6") is True
            and quadrature.get("vp14") is True
        )
        evidence = " | ".join(
            parsed.get("raw_evidence", {}).get(field, "")
            for field in ("VP1", "VP4", "VP5", "VP6", "VP8", "VP14")
            if parsed.get("raw_evidence", {}).get(field)
        )
        module = {
            "id": f"lipe-module:{document_id}:{page_number}",
            "document_id": document_id, "filename": filename, "sha256": sha256,
            "page_number": page_number, "tax_year": tax_year,
            "month": parsed.get("month"), "reference_period": (
                f"{tax_year}-{int(parsed['month']):02d}" if tax_year and parsed.get("month") else None
            ),
            "values": values, "raw_evidence": parsed.get("raw_evidence") or {},
            "source_text": evidence, "quadrature": quadrature,
            "parser_version": LIPE_PARSER_VERSION,
            "extraction_status": CERTAIN if certain else REVIEW,
            "certainty_reason": "coordinate_native_e_quadrature_vp6_vp14"
            if certain else "modulo_vp_non_completo_o_non_quadrato",
        }
        modules.append(module)
        if not certain:
            rejected.append(module)
            continue
        vp14_cents = int(values["vp14_cents"])
        if values["vp14_side"] != "debito" or vp14_cents <= 0:
            module["f24_expectation"] = "NESSUN_F24_A_DEBITO_ATTESO_CREDITO_LIPE"
            continue
        month = int(parsed["month"])
        raw = parsed.get("raw_evidence", {}).get("VP14") or evidence
        tax_rows.append({
            "id": _row_identity(document_id, page_number, month, raw),
            "document_id": document_id, "filename": filename, "sha256": sha256,
            "page_number": page_number, "source_text": raw,
            "parser_version": LIPE_PARSER_VERSION, "tax_code": str(6000 + month),
            "reference_period": f"{tax_year}-{month:02d}",
            "debit_amount": vp14_cents / 100, "credit_amount": 0.0,
            "extraction_status": CERTAIN,
            "certainty_reason": "vp14_debito_quadrato_con_coordinate_native",
        })
        module["f24_expectation"] = "F24_MENSILE_ATTESO"
    certain_modules = sum(module["extraction_status"] == CERTAIN for module in modules)
    return {
        "document_id": document_id, "document_type": "LIPE",
        "parser_version": LIPE_PARSER_VERSION, "tax_year": tax_year,
        "declared_fields": modules, "tax_rows": tax_rows, "rejected_rows": rejected,
        "extracted_with_certainty": certain_modules, "requires_review": len(rejected),
        "field_level_status": CERTAIN if modules and not rejected else REVIEW,
    }


def _layout_form_amount(words: list[dict[str, Any]], field: str) -> tuple[int | None, str]:
    label = next((word for word in words if str(word.get("text") or "").strip().upper() == field), None)
    if not label:
        return None, ""
    center = (float(label["y0"]) + float(label["y1"])) / 2
    row = sorted([
        word for word in words
        if float(word["x0"]) >= 430
        and abs(((float(word["y0"]) + float(word["y1"])) / 2) - center) <= 4
        and re.fullmatch(r"[\d.,]+", str(word.get("text") or "").strip())
    ], key=lambda word: float(word["x0"]))
    raw = "".join(str(word["text"]).strip() for word in row)
    if not raw:
        return None, ""
    if raw.startswith(","):
        raw = f"0{raw}"
    try:
        return int((_decimal(raw) * 100).quantize(Decimal("1"))), f"{field} {raw}"
    except InvalidOperation:
        return None, f"{field} {raw}"


def extract_annual_iva_fields(content: bytes, *, document_id: str, tax_year: int | None,
                              filename: str | None = None, sha256: str | None = None) -> dict[str, Any]:
    """Estrae i saldi annuali VL/VX solo se le ripetizioni del modello quadrano."""
    found: dict[str, dict[str, Any]] = {}
    for page_number, _text, words in _fitz_pages(content):
        for field in ("VL32", "VL33", "VL38", "VL39", "VX1", "VX2"):
            amount, raw = _layout_form_amount(words, field)
            if amount is not None:
                found[field] = {"cents": amount, "page_number": page_number, "source_text": raw}
    debit_pair = all(field in found for field in ("VL32", "VL38")) and found["VL32"]["cents"] == found["VL38"]["cents"]
    credit_pair = all(field in found for field in ("VL33", "VL39")) and found["VL33"]["cents"] == found["VL39"]["cents"]
    vx_debit_ok = "VX1" not in found or (debit_pair and found["VX1"]["cents"] == found["VL38"]["cents"])
    vx_credit_ok = "VX2" not in found or (credit_pair and found["VX2"]["cents"] == found["VL39"]["cents"])
    certain = debit_pair and credit_pair and vx_debit_ok and vx_credit_ok
    fields = [{
        "id": f"iva-field:{document_id}:{field}", "field": field,
        "value_cents": item["cents"], "value": item["cents"] / 100,
        "page_number": item["page_number"], "source_text": item["source_text"],
        "document_id": document_id, "filename": filename, "sha256": sha256,
        "tax_year": tax_year, "parser_version": IVA_PARSER_VERSION,
        "extraction_status": CERTAIN if certain else REVIEW,
    } for field, item in sorted(found.items())]
    tax_rows: list[dict[str, Any]] = []
    # Il debito F24 annuale nasce da VX1. VL38 da solo non basta: il quadro
    # VX puo' applicare ripartizioni che cambiano l'importo effettivo.
    annual_debit = found.get("VX1", {}).get("cents") if certain else None
    if annual_debit:
        source = found["VX1"]
        tax_rows.append({
            "id": _row_identity(document_id, source["page_number"], 6099, source["source_text"]),
            "document_id": document_id, "filename": filename, "sha256": sha256,
            "page_number": source["page_number"], "source_text": source["source_text"],
            "parser_version": IVA_PARSER_VERSION, "tax_code": "6099",
            "reference_period": str(tax_year or ""), "debit_amount": annual_debit / 100,
            "credit_amount": 0.0, "extraction_status": CERTAIN,
            "certainty_reason": "vx1_vl38_quadrati",
        })
    return {
        "document_id": document_id, "document_type": "DICHIARAZIONE_IVA",
        "parser_version": IVA_PARSER_VERSION, "tax_year": tax_year,
        "declared_fields": fields, "tax_rows": tax_rows,
        "rejected_rows": [] if certain else fields,
        "extracted_with_certainty": len(fields) if certain else 0,
        "requires_review": 0 if certain else 1,
        "field_level_status": CERTAIN if certain else REVIEW,
        "quadrature": {"vl_debit": debit_pair, "vl_credit": credit_pair, "vx_debit": vx_debit_ok, "vx_credit": vx_credit_ok},
        "f24_expectation": "F24_6099_ATTESO" if annual_debit else (
            "NESSUN_F24_6099_A_DEBITO_ATTESO" if found.get("VX1", {}).get("cents") == 0
            else "F24_6099_NON_DETERMINABILE_SENZA_VX1"
        ),
    }


def reconcile_lipe_management(extraction: dict[str, Any],
                              snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Confronta VP4/VP5 con vendite e acquisti del gestionale al centesimo."""
    items: list[dict[str, Any]] = []
    for module in extraction.get("declared_fields") or []:
        period = str(module.get("reference_period") or "")
        snapshot = snapshots.get(period) or {}
        source_status = str(snapshot.get("stato_calcolo") or "")
        source_reliable = source_status not in {"", "NON_CALCOLATO", "NON_VERIFICABILE"}
        pairs = (
            ("VP4", module.get("values", {}).get("vp4_cents"), snapshot.get("iva_vendite_cents")),
            ("VP5", module.get("values", {}).get("vp5_cents"), snapshot.get("iva_acquisti_competenza_cents")),
        )
        for field, declared, management in pairs:
            if module.get("extraction_status") != CERTAIN or not source_reliable or declared is None or management is None:
                status = MANAGEMENT_UNAVAILABLE
            else:
                status = EXACT if int(declared) == int(management) else DISCORDANT
            items.append({
                "id": f"lipe-management:{module['id']}:{field}",
                "period": period, "field": field, "status": status,
                "requires_review": status != EXACT,
                "declared_cents": declared, "management_cents": management,
                "difference_cents": int(management) - int(declared)
                if declared is not None and management is not None else None,
                "page_number": module.get("page_number"),
                "source_text": module.get("raw_evidence", {}).get(field),
                "management_source": snapshot.get("fonte"),
                "management_source_version": snapshot.get("fonte_calcolo"),
                "management_status": source_status or None,
                "rule": "VP4=iva_vendite_cents;VP5=iva_acquisti_competenza_cents",
            })
    counts = Counter(item["status"] for item in items)
    return {
        "items": items, "counts": dict(sorted(counts.items())),
        "certain": counts[EXACT],
        "requires_review": sum(item["requires_review"] for item in items),
        "all_certain": bool(items) and all(not item["requires_review"] for item in items),
        "semantics": {
            "exact_cents": True, "period_required": True,
            "vp4_source": "gestionale_iva_vendite",
            "vp5_source": "gestionale_iva_acquisti_competenza",
            "zero_or_missing_is_not_assumed": True,
        },
    }


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
                               filename: str | None = None, sha256: str | None = None,
                               tax_year: int | None = None) -> dict[str, Any]:
    digest = hashlib.sha256(content).hexdigest()
    if sha256 and digest.casefold() != str(sha256).casefold():
        return {
            "document_id": document_id, "document_type": document_type,
            "tax_rows": [], "rejected_rows": [], "extracted_with_certainty": 0,
            "requires_review": 1, "field_level_status": "HASH_DOCUMENTO_NON_COINCIDENTE",
            "expected_sha256": sha256, "actual_sha256": digest,
        }
    if document_type == "MODELLO_770":
        from app.services.pdf_text_extraction import extract_pdf_text
        text = extract_pdf_text(content, max_pages=None)
        return extract_770_tax_rows(text, document_id=document_id, filename=filename, sha256=digest)
    if document_type == "LIPE":
        return extract_lipe_fields(
            content, document_id=document_id, filename=filename, sha256=digest, tax_year=tax_year,
        )
    if document_type == "DICHIARAZIONE_IVA":
        return extract_annual_iva_fields(
            content, document_id=document_id, filename=filename, sha256=digest, tax_year=tax_year,
        )
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
