"""Import F24/quietanza rows into the fiscal evidence ledger.

The source PDF remains the fact.  A quietanza is payment evidence, while an
F24 printable form with bank details is kept as a distinct, weaker evidence
type.  Neither creates an accounting cost or a synthetic ``f24_unificato``.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.db_collections import (
    COLL_TAX_ALLOCATIONS,
    COLL_TAX_CREDIT_MOVEMENTS,
    COLL_TAX_PAYMENTS,
)
from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
from app.services.fiscal_evidence import (
    link_evidence,
    normalize_evidence,
    now_iso,
    stable_id,
)


PARSER_KIND_QUIETANZA = "QUIETANZA_AE"
PARSER_KIND_PRINTABLE = "F24_STAMPABILE_CON_ESTREMI"
_SECTIONS = (
    ("ERARIO", "sezione_erario"),
    ("INPS", "sezione_inps"),
    ("REGIONI", "sezione_regioni"),
    ("TRIB.LOCALI", "sezione_tributi_locali"),
    ("INAIL", "sezione_inail"),
    ("IMU", "sezione_imu"),
)


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value).strip().replace("€", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return round(float(text), 2)
    except (TypeError, ValueError):
        return 0.0


def normalize_reference_period(source: dict[str, Any]) -> str | None:
    """Normalizza il periodo della singola riga in ``YYYY-MM`` quando noto."""
    raw = str(
        source.get("periodo_riferimento")
        or source.get("riferimento")
        or source.get("mese_riferimento")
        or source.get("mese")
        or source.get("periodo_da")
        or ""
    ).strip()
    year = str(source.get("anno_riferimento") or source.get("anno") or "").strip()
    digits = re.sub(r"\D", "", raw)
    year_digits = re.sub(r"\D", "", year)
    if len(digits) >= 6:
        if digits[:4].startswith(("19", "20")):
            year_digits, digits = digits[:4], digits[4:6]
        else:
            year_digits, digits = digits[-4:], digits[:2]
    elif len(digits) == 4 and not year_digits and digits.startswith(("19", "20")):
        return None
    elif len(digits) == 4:
        first, last = digits[:2], digits[-2:]
        digits = first if 1 <= int(first or 0) <= 12 else last
    elif len(digits) > 2:
        digits = digits[:2]
    if len(year_digits) >= 4 and digits:
        month = int(digits[:2])
        if 1 <= month <= 12:
            return f"{year_digits[:4]}-{month:02d}"
    return None


def _section_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("righe", "tributi", "dettaglio", "items"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
        if value.get("codice") or value.get("codice_tributo") or value.get("causale"):
            return [value]
    return []


def _year_from_value(value: Any) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _tax_family(code: str) -> str:
    normalized = str(code or "").strip().upper()
    return "IVA" if normalized == "6099" or normalized.startswith("60") else "ALTRO"


def parse_f24_evidence(content: bytes, *, document_kind: str) -> dict[str, Any]:
    if document_kind == PARSER_KIND_QUIETANZA:
        from app.services.f24_parser import parse_quietanza_f24

        parsed = parse_quietanza_f24(pdf_content=content)
    elif document_kind == PARSER_KIND_PRINTABLE:
        from app.services.parser_f24 import parse_f24_commercialista

        parsed = parse_f24_commercialista(pdf_content=content)
    else:
        raise ValueError(f"Tipo documento F24 non supportato: {document_kind}")
    if not parsed or parsed.get("error"):
        raise ValueError((parsed or {}).get("error") or "Parsing F24 fallito")
    validation = parsed.get("validazione") or {}
    if not validation.get("saldo_quadrato"):
        raise ValueError(
            "F24 non quadrato: importazione fiscale sospesa "
            f"(differenza {validation.get('differenza_saldo')})"
        )
    return parsed


def normalize_f24_evidence_rows(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one row per PDF line; equal rows in different PDFs stay distinct."""
    rows: list[dict[str, Any]] = []
    ordinal = 0
    sources = list(_SECTIONS) + [
        ("TRIBUTI", "tributi"),
        ("RIGHE", "righe"),
        ("DETTAGLIO", "dettaglio_tributi"),
    ]
    for section, field in sources:
        for source in _section_rows(parsed.get(field)):
            ordinal += 1
            debit = _number(source.get("importo_debito") or source.get("debito") or source.get("importo"))
            credit = _number(source.get("importo_credito") or source.get("credito"))
            code = (
                source.get("codice_tributo")
                or source.get("codice")
                or source.get("causale")
                or ("INAIL" if section == "INAIL" else "")
            )
            entity = (
                source.get("codice_regione")
                or source.get("codice_comune")
                or source.get("codice_ente")
                or source.get("codice_sede")
                or ""
            )
            rows.append({
                "ordinal": ordinal,
                "section": section,
                "tax_code": str(code).strip().upper(),
                "reference_period": normalize_reference_period(source),
                "reference_period_raw": source.get("periodo_raw") or "",
                "entity_code": str(entity).strip().upper(),
                "debit_amount": debit,
                "credit_amount": credit,
                "row_kind": "CREDIT_OFFSET_USE" if credit > 0 else "DEBIT_SETTLEMENT",
                "description": source.get("descrizione") or "",
                "is_accounting_cost": False,
                "source_fields": source,
            })
    return rows


async def ingest_f24_evidence(
    db,
    *,
    content: bytes,
    filename: str,
    document_kind: str,
    company_id: str,
    source: str,
    source_metadata: dict[str, Any] | None = None,
    expected_sha256: str | None = None,
    actor: str = "f24-evidence-import",
) -> dict[str, Any]:
    """Validate first, then persist document, payment evidence and line ledger."""
    parsed = parse_f24_evidence(content, document_kind=document_kind)
    rows = normalize_f24_evidence_rows(parsed)
    if not rows:
        raise ValueError("Nessuna riga F24 estratta")

    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise ValueError("SHA-256 non coincide con il manifest")
    metadata = dict(source_metadata or {})
    metadata.update({"f24_document_kind": document_kind, "parser_validation": parsed["validazione"]})
    registered = await FiscalDocumentIngestionService(db, company_id=company_id).ingest(
        content=content,
        filename=filename,
        source=source,
        source_metadata=metadata,
        expected_sha256=digest,
        category_hint="quietanza_f24" if document_kind == PARSER_KIND_QUIETANZA else "f24_stampabile",
    )
    document_id = registered["document_id"]
    version_id = registered["version_id"]
    general = parsed.get("dati_generali") or {}
    totals = parsed.get("totali") or {}
    protocol = general.get("protocollo_telematico") or metadata.get("protocollo_telematico") or ""
    payment_date = (
        general.get("data_pagamento")
        or general.get("data_versamento")
        or metadata.get("data_versamento")
    )
    payment_id = stable_id("taxpayment", company_id, document_id, version_id)
    now = now_iso()
    payment = {
        "id": payment_id,
        "company_id": company_id,
        "source_kind": "F24_DOCUMENT_EVIDENCE",
        "evidence_type": document_kind,
        "document_id": document_id,
        "version_id": version_id,
        "filename": filename,
        "sha256": digest,
        "protocol": protocol,
        "payment_date": payment_date,
        "payment_year": _year_from_value(payment_date),
        "total_debit": round(float(totals.get("totale_debito") or 0), 2),
        "total_credit": round(float(totals.get("totale_credito") or 0), 2),
        "net_amount": round(float(totals.get("saldo_netto") or 0), 2),
        "payment_status": (
            "QUIETANZA_PRESENTE_DA_VERIFICARE_BANCA"
            if document_kind == PARSER_KIND_QUIETANZA
            else "F24_PRESENTE_DA_VERIFICARE_QUIETANZA_E_BANCA"
        ),
        "bank_evidence_id": None,
        "is_accounting_cost": False,
        "parser_validation": parsed["validazione"],
        "updated_at": now,
    }
    await db[COLL_TAX_PAYMENTS].update_one(
        {"company_id": company_id, "id": payment_id},
        {"$set": payment, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    allocation_ids: list[str] = []
    credit_movement_ids: list[str] = []
    for row in rows:
        allocation_id = stable_id("taxallocation", company_id, version_id, row["ordinal"])
        evidence = normalize_evidence(
            document_id=document_id,
            version_id=version_id,
            page_number=1,
            field="f24_row",
            raw_value=row["source_fields"],
            normalized_value={key: value for key, value in row.items() if key != "source_fields"},
            confidence=1.0,
            parser_version=parsed["validazione"]["parser_version"],
            reason="riga_documentale_quadrata",
        )
        allocation = {
            **{key: value for key, value in row.items() if key != "source_fields"},
            "id": allocation_id,
            "company_id": company_id,
            "source_kind": "F24_DOCUMENT_EVIDENCE",
            "payment_id": payment_id,
            "obligation_id": None,
            "document_id": document_id,
            "version_id": version_id,
            "filename": filename,
            "protocol": protocol,
            "payment_date": payment["payment_date"],
            "payment_year": payment["payment_year"],
            "evidence_type": document_kind,
            "evidence_ids": [evidence["id"]],
            "reconciliation_status": "UNMATCHED_OBLIGATION",
            "updated_at": now,
        }
        await db[COLL_TAX_ALLOCATIONS].update_one(
            {"company_id": company_id, "id": allocation_id},
            {"$set": allocation, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        await link_evidence(
            db,
            company_id=company_id,
            entity_type="tax_allocation",
            entity_id=allocation_id,
            relation_type="source_f24_pdf",
            evidence=[evidence],
            actor=actor,
        )
        allocation_ids.append(allocation_id)

        if row["credit_amount"] > 0:
            movement_id = stable_id("taxcreditmove", company_id, version_id, row["ordinal"])
            movement = {
                "id": movement_id,
                "company_id": company_id,
                "movement_type": "F24_OFFSET_USE",
                "tax_code": row["tax_code"],
                "tax_family": _tax_family(row["tax_code"]),
                "reference_period": row["reference_period"],
                "year": _year_from_value(row["reference_period"]) or payment["payment_year"],
                "effective_at": payment["payment_date"],
                "amount": row["credit_amount"],
                "credit_origin_id": None,
                "origin_status": "UNRESOLVED",
                "allocation_id": allocation_id,
                "document_id": document_id,
                "version_id": version_id,
                "evidence_ids": [evidence["id"]],
                "updated_at": now,
            }
            await db[COLL_TAX_CREDIT_MOVEMENTS].update_one(
                {"company_id": company_id, "id": movement_id},
                {"$set": movement, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            credit_movement_ids.append(movement_id)

    return {
        "duplicate_document": registered["status"] == "duplicate",
        "document_id": document_id,
        "version_id": version_id,
        "payment_id": payment_id,
        "allocation_ids": allocation_ids,
        "credit_movement_ids": credit_movement_ids,
        "rows": len(rows),
        "credits": len(credit_movement_ids),
        "validation": parsed["validazione"],
    }
