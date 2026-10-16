"""Vista verificabile dei piani rateali AdeR.

Il piano, il modulo F24 predisposto e la prova del pagamento sono documenti
distinti.  Questa vista collega soltanto riferimenti espliciti gia' registrati:
non abbina mai per importo, data o somiglianza del nome file.
"""

from __future__ import annotations

import re
from typing import Any

from app.db_collections import COLL_ADER_POSITION_SNAPSHOTS, COLL_FISCAL_DOCUMENTS


_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _first(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _email_provenance(document: dict[str, Any] | None, fallback_filename: str | None) -> dict[str, Any]:
    document = document or {}
    candidates = [document, document.get("source_metadata") or {}]
    candidates.extend(document.get("source_occurrences") or [])
    sources: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        account = _first(item, "email_account", "mailbox", "account", "email_user")
        if account and not _EMAIL.search(str(account)):
            account = None
        source = {
            "email_account": account,
            "email_from": _first(item, "email_from", "from", "sender", "mittente"),
            "email_to": _first(item, "email_to", "to", "recipient"),
            "email_subject": _first(item, "email_subject", "subject"),
            "email_date": _first(item, "email_date", "date"),
            "email_message_id": _first(item, "email_message_id", "gmail_message_id", "message_id"),
        }
        source = {key: value for key, value in source.items() if value not in (None, "")}
        if not source:
            continue
        marker = tuple(source.get(key) for key in sorted(source))
        if marker not in seen:
            seen.add(marker)
            sources.append(source)

    filename = document.get("filename") or fallback_filename
    filename_emails = list(dict.fromkeys(_EMAIL.findall(str(filename or ""))))
    return {
        "status": "RECORDED" if sources else ("FILENAME_ONLY" if filename_emails else "NOT_RECORDED"),
        "source_filename": filename,
        "source_channel": document.get("source"),
        "email_sources": sources,
        # E' un indizio letterale, non viene promosso a mittente o casella.
        "filename_email_hints": filename_emails,
    }


def _module_key(module: dict[str, Any]) -> tuple[Any, ...]:
    if module.get("document_number"):
        return ("document_number", module.get("document_number"),
                tuple(module.get("installment_numbers") or []))
    return ("source_document", module.get("source_document_id"),
            tuple(module.get("installment_numbers") or []))


async def enrich_rate_plans(db, *, company_id: str, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggiunge provenienza, cartelle/tributi e stato F24 ai piani letti."""
    source_ids: set[str] = set()
    document_numbers: set[str] = set()
    for plan in plans:
        if plan.get("source_document_id"):
            source_ids.add(plan["source_document_id"])
        for module in plan.get("payment_modules") or []:
            if module.get("source_document_id"):
                source_ids.add(module["source_document_id"])
        for reference in plan.get("document_references") or []:
            if reference.get("document_number"):
                document_numbers.add(reference["document_number"])

    fiscal_documents = await db[COLL_FISCAL_DOCUMENTS].find(
        {"company_id": company_id, "id": {"$in": list(source_ids)}},
        {"_id": 0, "id": 1, "filename": 1, "source": 1, "source_metadata": 1,
         "source_occurrences": 1},
    ).to_list(max(1, len(source_ids))) if source_ids else []
    documents_by_id = {item["id"]: item for item in fiscal_documents if item.get("id")}

    snapshots = await db[COLL_ADER_POSITION_SNAPSHOTS].find(
        {"company_id": company_id, "document_number": {"$in": list(document_numbers)}},
        {"_id": 0},
    ).to_list(max(1, len(document_numbers) * 20)) if document_numbers else []
    snapshots_by_number: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        snapshots_by_number.setdefault(snapshot.get("document_number") or "", []).append(snapshot)

    result: list[dict[str, Any]] = []
    for original in plans:
        plan = dict(original)
        plan["source_provenance"] = _email_provenance(
            documents_by_id.get(plan.get("source_document_id")), plan.get("source_filename"),
        )

        amount_by_reference = {
            item.get("printed_reference"): item.get("amount_cents")
            for item in plan.get("documents") or []
        }
        related_claims: list[dict[str, Any]] = []
        for reference in plan.get("document_references") or []:
            printed = reference.get("printed_reference")
            number = reference.get("document_number")
            candidates = snapshots_by_number.get(number or "", [])
            latest = max(candidates, key=lambda row: (str(row.get("snapshot_date") or ""),
                                                       str(row.get("created_at") or "")), default=None)
            detailed = max((row for row in candidates if row.get("lines")),
                           key=lambda row: (str(row.get("snapshot_date") or ""),
                                            str(row.get("created_at") or "")), default=None)
            lines = (detailed or {}).get("lines") or []
            related_claims.append({
                "printed_reference": printed,
                "document_number": number,
                "plan_amount_cents": amount_by_reference.get(printed),
                "link_status": (
                    "UNRESOLVED_REFERENCE" if not number
                    else ("CONFIRMED_WITH_TAX_DETAIL" if detailed else "REFERENCE_RESOLVED_DETAIL_NOT_FOUND")
                ),
                "document_type": (detailed or latest or {}).get("document_type"),
                "creditor": (detailed or latest or {}).get("creditor"),
                "notification_date": (detailed or latest or {}).get("notification_date"),
                "current_business_status": (latest or {}).get("calculated_business_status"),
                "current_snapshot_date": (latest or {}).get("snapshot_date"),
                "tax_detail_source_document_id": (detailed or {}).get("source_document_id"),
                "tribute_status": "AVAILABLE" if lines else "NOT_AVAILABLE",
                "tributes": [{
                    "tax_code": line.get("codice_tributo"),
                    "description": line.get("descrizione"),
                    "year": line.get("anno"),
                    "creditor": line.get("ente_impositore"),
                    "rateized": line.get("rateizzato"),
                    "initial_cents": line.get("iniziale_cents"),
                    "residual_cents": line.get("residuo_cents"),
                } for line in lines],
            })
        plan["related_claims"] = related_claims

        modules: list[dict[str, Any]] = []
        seen_modules: set[tuple[Any, ...]] = set()
        for original_module in plan.get("payment_modules") or []:
            module = dict(original_module)
            marker = _module_key(module)
            if marker in seen_modules:
                continue
            seen_modules.add(marker)
            module["link_basis"] = "EXACT_PLAN_REFERENCE"
            module["document_kind"] = "F24_PIANO_RATEALE"
            module["payment_evidence"] = False
            module["source_provenance"] = _email_provenance(
                documents_by_id.get(module.get("source_document_id")), module.get("source_filename"),
            )
            modules.append(module)
        plan["payment_modules"] = modules
        plan["f24_link_status"] = (
            "CONFIRMED_BY_EXACT_PLAN_REFERENCE" if modules else "NOT_FOUND_WITH_EXACT_PLAN_REFERENCE"
        )
        result.append(plan)
    return result
