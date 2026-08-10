"""Parser conservativo delle note di rettifica INPS (Mod. DMRA).

La nota genera un'obbligazione e puo' citare un F24 originario o le istruzioni
per un F24 futuro, ma non costituisce mai prova di pagamento.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any


PARSER_VERSION = "inps-dmra-v1"


def _extract_text(content: bytes) -> tuple[str, int]:
    import fitz

    with fitz.open(stream=content, filetype="pdf") as document:
        return "\n".join(page.get_text() or "" for page in document), len(document)


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _money(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return round(float(value.replace(".", "").replace(",", ".")), 2)
    except ValueError:
        return None


def _group(pattern: str, text: str, flags: int = re.IGNORECASE | re.DOTALL) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def parse_nota_rettifica_inps(content: bytes) -> dict[str, Any]:
    text, page_count = _extract_text(content)
    compact = re.sub(r"\s+", " ", text)
    if not re.search(r"NOTA\s+DI\s+RETTIFICA|Mod\.\s*DMRA", compact, re.IGNORECASE):
        return {
            "document_kind": "SCONOSCIUTO",
            "is_payment_evidence": False,
            "requires_review": True,
            "parser_version": PARSER_VERSION,
        }

    f24_instruction = re.search(
        r"Codice\s+Sede.*?Importo\s+(\d{4})\s+([A-Z0-9]{4})\s+(\d{8,12})\s+"
        r"(\d{2}/\d{4})\s+(?:€|EUR)?\s*([\d.]+,\d{2})",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    f24 = {}
    if f24_instruction:
        f24 = {
            "codice_sede": f24_instruction.group(1),
            "causale_contributo": f24_instruction.group(2).upper(),
            "matricola": f24_instruction.group(3),
            "periodo_riferimento": f24_instruction.group(4),
            "importo": _money(f24_instruction.group(5)),
        }

    matricola = _group(r"Matricola\s+azienda\s+(\d{8,12})", compact)
    codice_fiscale = _group(r"Codice\s+fiscale\s+(\d{11}|[A-Z0-9]{16})", compact)
    periodo = _group(r"competenza\s+(\d{2}/\d{4})", compact)
    data_scadenza = _iso_date(_group(r"Da\s+versare\s+entro\s+il\s+(\d{2}/\d{2}/\d{4})", compact))
    totale = _money(_group(r"Importo\s+totale\s+a\s+debito\s+dell['’]\s*azienda\s+(?:€|EUR)?\s*([\d.]+,\d{2})", compact))
    differenza = _money(_group(r"Differenze\s+contributive\s+a\s+debito\s+azienda\s+(?:€|EUR)?\s*([\d.]+,\d{2})", compact))
    sanzioni = _money(_group(r"Sanzioni\s+civili\s+(?:su|per)\s+differenze\s+contributive\s+(?:€|EUR)?\s*([\d.]+,\d{2})", compact))

    field_evidence = {}
    for field, value in {
        "periodo_competenza": periodo,
        "matricola_inps": matricola,
        "data_scadenza": data_scadenza,
        "differenze_contributive": differenza,
        "sanzioni_civili": sanzioni,
        "importo_totale": totale,
        "data_f24_originario": _iso_date(_group(r"Data\s+pagamento\s+F24\s+(\d{2}/\d{2}/\d{4})", compact)),
        "data_invio_uniemens": _iso_date(_group(r"Data\s+di\s+invio\s+flusso\s+UniEmens\s+(\d{2}/\d{2}/\d{4})", compact)),
    }.items():
        if value is None:
            continue
        field_evidence[field] = {
            "page": 1,
            "raw_text": str(value),
            "normalized_value": value,
            "parser_version": PARSER_VERSION,
            "confidence": 0.8,
        }
    try:
        import fitz

        with fitz.open(stream=content, filetype="pdf") as document:
            for item in field_evidence.values():
                candidates = [item["raw_text"]]
                if isinstance(item.get("normalized_value"), float):
                    candidates.append(
                        f"{item['normalized_value']:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                    )
                for page_number, page in enumerate(document, start=1):
                    rectangles = []
                    for candidate in candidates:
                        rectangles = page.search_for(str(candidate)) if candidate else []
                        if rectangles:
                            break
                    if rectangles:
                        rect = rectangles[0]
                        item.update({
                            "page": page_number,
                            "x0": round(rect.x0, 2), "y0": round(rect.y0, 2),
                            "x1": round(rect.x1, 2), "y1": round(rect.y1, 2),
                            "confidence": 1.0,
                        })
                        break
    except Exception:
        pass

    return {
        "document_kind": "NOTA_RETTIFICA_INPS",
        "is_payment_evidence": False,
        "obligation_status": "APERTO",
        "requires_review": False,
        "parser_version": PARSER_VERSION,
        "page_count": page_count,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "data_emissione": _iso_date(_group(r"emessa\s+il\s+(\d{2}/\d{2}/\d{4})", compact)),
        "data_scadenza": data_scadenza,
        "periodo_competenza": periodo,
        "matricola_inps": matricola,
        "codice_fiscale": codice_fiscale,
        "codice_statistico_contributivo": _group(r"Codice\s+statistico\s+contributivo\s+(\d+)", compact),
        "codici_autorizzazione": _group(r"Codici\s+autorizzazione\s+([A-Z0-9]+)", compact),
        "numero_dipendenti": int(_group(r"Numero\s+dipendenti\s+occupati\s+(\d+)", compact) or 0) or None,
        "data_f24_originario": _iso_date(_group(r"Data\s+pagamento\s+F24\s+(\d{2}/\d{2}/\d{4})", compact)),
        "data_invio_uniemens": _iso_date(_group(r"Data\s+di\s+invio\s+flusso\s+UniEmens\s+(\d{2}/\d{2}/\d{4})", compact)),
        "saldo_originario": _money(_group(r"competenza\s+\d{2}/\d{4}\s+con\s+saldo\s+di\s+(?:€|EUR)?\s*([\d.]+,\d{2})", compact)),
        "differenze_contributive": differenza,
        "sanzioni_civili": sanzioni,
        "importo_totale": totale,
        "giorni_sanzione": int(_group(r"n\.\s*giorni\s+(\d+)", compact) or 0) or None,
        "tasso_sanzione": _money(_group(r"tasso\s+([\d,]+)%", compact)),
        "istruzioni_f24": f24,
        "field_evidence": field_evidence,
        "relation_keys": {
            "matricola_inps": matricola,
            "periodo_competenza": periodo,
            "codice_fiscale": codice_fiscale,
            "data_f24_originario": _iso_date(_group(r"Data\s+pagamento\s+F24\s+(\d{2}/\d{2}/\d{4})", compact)),
        },
        "canonical_relations": {
            "rectification": {"status": "SOURCE_DOCUMENT"},
            "uniemens": {"date": _iso_date(_group(r"Data\s+di\s+invio\s+flusso\s+UniEmens\s+(\d{2}/\d{2}/\d{4})", compact)), "status": "CITED"},
            "original_f24": {"date": _iso_date(_group(r"Data\s+pagamento\s+F24\s+(\d{2}/\d{2}/\d{4})", compact)), "status": "CITED"},
            "obligation": {"status": "OPEN", "amount_cents": int(Decimal(str(totale)) * 100) if totale is not None else None},
            "corrective_f24": {"status": "TO_BE_LINKED"},
            "quietanza": {"status": "TO_BE_LINKED"},
            "bank_movement": {"status": "TO_BE_LINKED"},
        },
    }
