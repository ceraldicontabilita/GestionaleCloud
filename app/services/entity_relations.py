"""Registro canonico delle relazioni tra entita' contabili.

Le collection operative continuano a conservare i riferimenti necessari alle
schermate esistenti. Questo registro aggiunge una sola relazione verificabile,
interrogabile da entrambi i lati e idempotente. Non modifica mai lo stato di
pagamento di fatture o movimenti: descrive soltanto il legame e le sue prove.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.db_collections import COLL_ENTITY_RELATIONS
from app.services.payment_invoice_matching import money_cents


VALID_STATUSES = {"confirmed", "pending", "revoked"}


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} obbligatorio")
    return text


def relation_key(
    source_type: str,
    source_id: str,
    relation_type: str,
    target_type: str,
    target_id: str,
) -> str:
    """Chiave leggibile e deterministica della coppia di evidenze."""
    return "|".join(
        (
            _required_text(source_type, "source_type"),
            _required_text(source_id, "source_id"),
            _required_text(relation_type, "relation_type"),
            _required_text(target_type, "target_type"),
            _required_text(target_id, "target_id"),
        )
    )


def _normalize_evidence(evidence: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        value = item.get("value")
        if not kind or value in (None, ""):
            continue
        marker = (kind, str(value))
        if marker in seen:
            continue
        seen.add(marker)
        result.append({"type": kind, "value": value})
    return result


async def upsert_entity_relation(
    db,
    *,
    source_type: str,
    source_id: str,
    relation_type: str,
    target_type: str,
    target_id: str,
    status: str,
    rule: str,
    evidence: Optional[Iterable[Dict[str, Any]]] = None,
    amount: Any = None,
    provenance: Optional[Dict[str, Any]] = None,
    actor: str = "system",
) -> str:
    """Crea o aggiorna una relazione senza produrre duplicati.

    ``amount_cents`` evita confronti float. La provenienza contiene soltanto
    metadati e hash: mai il PDF o altri byte del documento.
    """
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"status non valido: {status}")
    key = relation_key(source_type, source_id, relation_type, target_type, target_id)
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "relation_key": key,
        "source": {"type": source_type, "id": source_id},
        "target": {"type": target_type, "id": target_id},
        "relation_type": relation_type,
        "status": normalized_status,
        "rule": _required_text(rule, "rule"),
        "evidence": _normalize_evidence(evidence),
        "amount_cents": money_cents(amount),
        "provenance": dict(provenance or {}),
        "updated_at": now,
        "updated_by": actor,
    }
    await getattr(db, COLL_ENTITY_RELATIONS).update_one(
        {"relation_key": key},
        {
            "$setOnInsert": {"created_at": now, "created_by": actor},
            "$set": document,
            "$unset": {"revoked_at": "", "revoked_by": ""},
        },
        upsert=True,
    )
    return key


async def revoke_entity_relation(
    db,
    *,
    source_type: str,
    source_id: str,
    relation_type: str,
    target_type: str,
    target_id: str,
    actor: str = "system",
) -> bool:
    """Revoca il legame senza cancellarne la traccia di audit."""
    key = relation_key(source_type, source_id, relation_type, target_type, target_id)
    now = datetime.now(timezone.utc).isoformat()
    result = await getattr(db, COLL_ENTITY_RELATIONS).update_one(
        {"relation_key": key, "status": {"$ne": "revoked"}},
        {"$set": {
            "status": "revoked",
            "revoked_at": now,
            "revoked_by": actor,
            "updated_at": now,
            "updated_by": actor,
        }},
    )
    return bool(getattr(result, "matched_count", 0))


async def find_entity_relations(
    db,
    *,
    entity_type: str,
    entity_id: str,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Legge lo stesso legame da uno qualunque dei due estremi."""
    entity_type = _required_text(entity_type, "entity_type")
    entity_id = _required_text(entity_id, "entity_id")
    query: Dict[str, Any] = {"$or": [
        {"source.type": entity_type, "source.id": entity_id},
        {"target.type": entity_type, "target.id": entity_id},
    ]}
    if status:
        query["status"] = status
    cursor = getattr(db, COLL_ENTITY_RELATIONS).find(query, {"_id": 0}).sort("updated_at", -1)
    return await cursor.to_list(max(1, min(int(limit), 500)))
