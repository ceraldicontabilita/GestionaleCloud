"""Anteprima non mutante per l'ingresso unico ``Documenti``.

Il token di conferma e' stateless: lega hash SHA-256, classificazione e
scadenza alla SECRET_KEY applicativa. Nessun record viene creato durante la
preview e lo stesso token non puo' autorizzare un file o un tipo diverso.
"""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import time
from pathlib import Path
from typing import Any

from app.config import settings


PARSER_VERSION = "document-import-preview-v1"
TOKEN_TTL_SECONDS = 30 * 60


def create_confirmation_token(sha256: str, document_type: str) -> str:
    issued_at = int(time.time())
    message = f"{issued_at}:{sha256}:{document_type}".encode("utf-8")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return f"{issued_at}.{signature}"


def verify_confirmation_token(token: str, sha256: str, document_type: str) -> bool:
    try:
        issued_raw, supplied = token.split(".", 1)
        issued_at = int(issued_raw)
    except (AttributeError, TypeError, ValueError):
        return False
    age = int(time.time()) - issued_at
    if age < 0 or age > TOKEN_TTL_SECONDS:
        return False
    message = f"{issued_at}:{sha256}:{document_type}".encode("utf-8")
    expected = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(supplied, expected)


def _pdf_page_count(content: bytes) -> int | None:
    if not content.startswith(b"%PDF"):
        return None
    try:
        import fitz

        with fitz.open(stream=content, filetype="pdf") as document:
            return document.page_count
    except Exception:
        return None


async def _duplicate_sources(db, sha256: str, md5: str) -> list[dict[str, Any]]:
    checks = (
        ("documents_inbox", {"$or": [{"sha256": sha256}, {"file_hash": sha256}, {"file_hash": md5}]}),
        ("f24_unificato", {"$or": [{"pdf_hash": sha256}, {"sha256": sha256}]}),
        ("quietanze_f24", {"$or": [{"pdf_hash": sha256}, {"sha256": sha256}]}),
        ("ricevute_pagopa", {"$or": [{"pdf_hash": sha256}, {"sha256": sha256}]}),
    )
    found: list[dict[str, Any]] = []
    for collection, query in checks:
        existing = await db[collection].find_one(
            query, {"_id": 0, "id": 1, "filename": 1, "file_name": 1}
        )
        if existing:
            found.append({"collection": collection, **existing})
    return found


def _f24_preview(content: bytes, document_kind: str) -> dict[str, Any]:
    from app.services.f24_fiscal_evidence import (
        PARSER_KIND_MODELLO,
        PARSER_KIND_QUIETANZA,
        normalize_f24_evidence_rows,
        parse_f24_evidence,
    )

    kind = PARSER_KIND_QUIETANZA if document_kind == "quietanza_f24" else PARSER_KIND_MODELLO
    parsed = parse_f24_evidence(content, document_kind=kind)
    rows = normalize_f24_evidence_rows(parsed)
    from app.services.fiscal_accounting_policy import build_journal_proposal

    proposal = build_journal_proposal(
        parsed,
        document_type="F24_QUIETANZA" if kind == PARSER_KIND_QUIETANZA else "F24_MODELLO",
    )
    return {
        "dati_generali": parsed.get("dati_generali") or {},
        "totali": parsed.get("totali") or {},
        "validazione": parsed.get("validazione") or {},
        "righe_tributo": len(rows),
        "righe_credito": sum(1 for row in rows if row.get("credit_amount", 0) > 0),
        "field_evidence": parsed.get("field_evidence") or {},
        "journal_proposal": proposal,
    }


def _specialist_preview(content: bytes, filename: str, document_type: str) -> dict[str, Any]:
    if document_type in {"f24", "quietanza_f24"}:
        return _f24_preview(content, document_type)
    if document_type in {
        "avviso_pagopa", "ricevuta_pagopa", "ricevuta_cbill", "ricevuta_mav",
        "ricevuta_rav", "ricevuta_bollettino_postale", "esito_pagopa_negativo",
    }:
        from app.services.pagopa_receipts import parse_receipt_pdf
        from app.services.fiscal_accounting_policy import build_journal_proposal

        parsed = parse_receipt_pdf(content, filename=filename)
        return {
            **parsed,
            "journal_proposal": build_journal_proposal(
                parsed,
                document_type="AVVISO_PAGOPA"
                if document_type == "avviso_pagopa"
                else document_type.upper(),
            ),
        }
    if document_type == "nota_rettifica_inps":
        from app.services.inps_adjustment_parser import parse_nota_rettifica_inps
        from app.services.fiscal_accounting_policy import build_journal_proposal

        parsed = parse_nota_rettifica_inps(content)
        return {
            **parsed,
            "journal_proposal": build_journal_proposal(
                parsed, document_type="NOTA_RETTIFICA_INPS"
            ),
        }
    if document_type == "pos_terminal":
        if "commissioni_" in filename.lower():
            from app.services.pos_commissioni_import import parse_pos_commissioni_file

            parsed = parse_pos_commissioni_file(content, filename)
            return {
                "giorni": parsed.get("rows", 0),
                "righe_non_valide": parsed.get("invalid", 0),
                "operation_identity": "pos_numia_commissioni_data",
            }
        from app.services.pos_terminal_import import parse_pos_terminal_file

        parsed = parse_pos_terminal_file(content, filename)
        return {
            "operazioni": parsed.get("rows", 0),
            "righe_sorgente": parsed.get("source_rows", 0),
            "duplicati_nel_file": parsed.get("duplicates", 0),
            "approvate": parsed.get("approved", 0),
            "giorni": len(parsed.get("daily_totals") or {}),
            "terminali": parsed.get("terminali") or [],
            "operation_identity": "pos_numia_v2",
        }
    if document_type in {
        "tari_avviso", "tari_istanza_compensazione", "visura_camerale",
        "documento_identita", "ader_sospensione", "ader_definizione_agevolata",
        "dimissioni_telematiche",
    }:
        from app.services.administrative_document_parser import extract_administrative_metadata

        return extract_administrative_metadata(
            content=content, filename=filename, document_type=document_type
        )
    return {}


async def build_import_preview(
    db, *, content: bytes, filename: str, document_type: str
) -> dict[str, Any]:
    sha256 = hashlib.sha256(content).hexdigest()
    md5 = hashlib.md5(content).hexdigest()
    parsed = _specialist_preview(content, filename, document_type)
    parser_error = parsed.get("error") if isinstance(parsed, dict) else None
    validation = (parsed.get("validazione") or {}) if isinstance(parsed, dict) else {}
    blocking_errors: list[str] = []
    if parser_error:
        blocking_errors.append(str(parser_error))
    if document_type in {"f24", "quietanza_f24"} and validation.get("saldo_quadrato") is not True:
        blocking_errors.append("F24 non quadrato o non validato")
    duplicates = await _duplicate_sources(db, sha256, md5)
    return {
        "success": not blocking_errors,
        "preview_only": True,
        "filename": filename,
        "document_type": document_type,
        "tipo_rilevato": document_type,
        "classification": {
            "document_type": document_type,
            "confidence": 1.0 if document_type != "auto" else 0.0,
            "reason": "classificatore_deterministico_upload_auto",
            "classifier_version": PARSER_VERSION,
        },
        "file": {
            "sha256": sha256,
            "size_bytes": len(content),
            "extension": Path(filename).suffix.lower(),
            "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "page_count": _pdf_page_count(content),
        },
        "duplicate": bool(duplicates),
        "duplicate_sources": duplicates,
        "parsed": parsed,
        "validation": validation,
        "blocking_errors": blocking_errors,
        "confirmation_required": True,
        "confirmation_token": (
            None if blocking_errors else create_confirmation_token(sha256, document_type)
        ),
        "token_expires_in_seconds": TOKEN_TTL_SECONDS,
    }
