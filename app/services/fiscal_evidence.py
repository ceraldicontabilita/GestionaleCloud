"""Catena documentale fiscale immutabile e interrogabile in entrambe le direzioni."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from app.db_collections import (
    COLL_FISCAL_DOCUMENTS,
    COLL_FISCAL_DOCUMENT_VERSIONS,
    COLL_FISCAL_EVIDENCE,
    COLL_FISCAL_LINKS,
    COLL_FISCAL_PAGES,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def normalize_evidence(
    *, document_id: str, version_id: str, page_number: int,
    field: str, raw_value: Any, normalized_value: Any = None,
    confidence: float = 1.0, parser_version: str = "manual-v1",
    reason: str = "document_source",
) -> dict[str, Any]:
    if not document_id or not version_id or page_number < 1 or not field:
        raise ValueError("document_id, version_id, page_number e field sono obbligatori")
    confidence = max(0.0, min(float(confidence), 1.0))
    evidence_id = stable_id(
        "ev", document_id, version_id, page_number, field,
        raw_value, normalized_value, parser_version,
    )
    return {
        "id": evidence_id,
        "document_id": document_id,
        "version_id": version_id,
        "page_number": int(page_number),
        "field": field,
        "raw_value": raw_value,
        "normalized_value": raw_value if normalized_value is None else normalized_value,
        "confidence": confidence,
        "parser_version": parser_version,
        "reason": reason,
    }


async def register_document(
    db, *, company_id: str, content: bytes, filename: str, source: str,
    source_ref: str | None = None, category: str = "altro",
    page_count: int = 1, metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Registra documento/versione/pagine per SHA-256, senza inferire fatti fiscali."""
    if not company_id or not content:
        raise ValueError("company_id e content sono obbligatori")
    sha256 = hashlib.sha256(content).hexdigest()
    existing = await db[COLL_FISCAL_DOCUMENT_VERSIONS].find_one(
        {"company_id": company_id, "sha256": sha256}, {"_id": 0}
    )
    if existing:
        return {"duplicate": True, **existing}

    document_id = stable_id("fdoc", company_id, source, source_ref or sha256)
    version_id = stable_id("fver", company_id, document_id, sha256)
    now = now_iso()
    await db[COLL_FISCAL_DOCUMENTS].update_one(
        {"company_id": company_id, "id": document_id},
        {"$setOnInsert": {
            "company_id": company_id, "id": document_id, "created_at": now,
            "source": source, "source_ref": source_ref,
        }, "$set": {
            "filename": filename, "category": category,
            "current_version_id": version_id, "updated_at": now,
            "metadata": dict(metadata or {}),
        }}, upsert=True,
    )
    version = {
        "company_id": company_id, "id": version_id, "document_id": document_id,
        "sha256": sha256, "size_bytes": len(content), "page_count": max(1, int(page_count)),
        "source": source, "source_ref": source_ref, "created_at": now,
    }
    await db[COLL_FISCAL_DOCUMENT_VERSIONS].insert_one(version.copy())
    for page in range(1, version["page_count"] + 1):
        await db[COLL_FISCAL_PAGES].update_one(
            {"company_id": company_id, "version_id": version_id, "page_number": page},
            {"$setOnInsert": {
                "company_id": company_id, "id": stable_id("fpage", version_id, page),
                "document_id": document_id, "version_id": version_id,
                "page_number": page, "created_at": now,
            }}, upsert=True,
        )
    return {"duplicate": False, **version}


async def link_evidence(
    db, *, company_id: str, entity_type: str, entity_id: str,
    relation_type: str, evidence: Iterable[dict[str, Any]], actor: str,
    status: str = "confirmed",
) -> str:
    """Crea un link idempotente; un link non modifica mai lo stato di pagamento."""
    if status not in {"confirmed", "pending", "revoked"}:
        raise ValueError("stato collegamento non valido")
    evidence_ids: list[str] = []
    for item in evidence:
        record = dict(item)
        if not record.get("id"):
            raise ValueError("evidence id obbligatorio")
        record.update({"company_id": company_id, "updated_at": now_iso()})
        await db[COLL_FISCAL_EVIDENCE].update_one(
            {"company_id": company_id, "id": record["id"]},
            {"$setOnInsert": {**record, "created_at": now_iso()}}, upsert=True,
        )
        evidence_ids.append(record["id"])
    link_id = stable_id("flink", company_id, entity_type, entity_id, relation_type, *sorted(evidence_ids))
    await db[COLL_FISCAL_LINKS].update_one(
        {"company_id": company_id, "id": link_id},
        {"$setOnInsert": {"created_at": now_iso(), "created_by": actor}, "$set": {
            "company_id": company_id, "id": link_id, "entity_type": entity_type,
            "entity_id": entity_id, "relation_type": relation_type,
            "evidence_ids": evidence_ids, "status": status,
            "updated_at": now_iso(), "updated_by": actor,
        }}, upsert=True,
    )
    return link_id


async def find_linked_evidence(db, *, company_id: str, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    links = await db[COLL_FISCAL_LINKS].find(
        {"company_id": company_id, "entity_type": entity_type, "entity_id": entity_id,
         "status": {"$ne": "revoked"}}, {"_id": 0}
    ).to_list(500)
    ids = sorted({item for link in links for item in link.get("evidence_ids", [])})
    evidence = [] if not ids else await db[COLL_FISCAL_EVIDENCE].find(
        {"company_id": company_id, "id": {"$in": ids}}, {"_id": 0}
    ).to_list(2000)
    by_id = {item["id"]: item for item in evidence}
    for link in links:
        link["evidence"] = [by_id[eid] for eid in link.get("evidence_ids", []) if eid in by_id]
        for item in link["evidence"]:
            item["viewer_url"] = f"/api/fiscal/documents/{item['document_id']}/content#page={item['page_number']}"
    return links
