"""Indicatori aggregati di compliance applicativa, in sola lettura.

Il servizio osserva permessi, tracciabilita' e code documentali senza esporre
identita', contenuti o riferimenti dei documenti e senza modificare record.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict

from app.utils.ruoli import NON_AUTORIZZATO, normalizza_ruolo


@dataclass(frozen=True)
class ComplianceSnapshot:
    active_users: int
    active_users_with_invalid_role: int
    active_users_without_name: int
    audit_records: int
    audit_records_complete: int
    audit_records_missing_actor: int
    audit_records_missing_timestamp: int
    audit_records_missing_entity_reference: int
    audit_coverage_percent: float
    inbox_documents_pending: int
    inbox_documents_in_error: int
    inbox_documents_without_payload: int
    documents_unassociated: int
    permissions_write_supported: bool
    audit_write_supported: bool
    document_link_supported: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _blank(field: str) -> Dict[str, Any]:
    return {"$or": [
        {field: {"$exists": False}},
        {field: None},
        {field: ""},
    ]}


async def leggi_snapshot_compliance(db) -> ComplianceSnapshot:
    users = await db["utenti_pin"].find(
        {"attivo": {"$ne": False}},
        {"_id": 0, "nome": 1, "ruolo": 1},
    ).to_list(5000)
    invalid_roles = sum(
        1 for user in users
        if normalizza_ruolo(user.get("ruolo")) == NON_AUTORIZZATO
    )
    without_name = sum(1 for user in users if not str(user.get("nome") or "").strip())

    audit = db["audit_log"]
    audit_records = await audit.count_documents({})
    missing_actor = await audit.count_documents(_blank("utente"))
    missing_timestamp = await audit.count_documents(_blank("timestamp"))
    missing_entity = await audit.count_documents({"$or": [
        *_blank("entita_id")["$or"],
        *_blank("entita_collection")["$or"],
    ]})
    incomplete = await audit.count_documents({"$or": [
        *_blank("id")["$or"],
        *_blank("modulo")["$or"],
        *_blank("azione")["$or"],
        *_blank("timestamp")["$or"],
        *_blank("utente")["$or"],
        *_blank("entita_id")["$or"],
        *_blank("entita_collection")["$or"],
    ]})
    complete = max(0, audit_records - incomplete)
    coverage = round((complete / audit_records) * 100, 2) if audit_records else 100.0

    inbox_active = {"status": {"$nin": ["deleted", "archived", "eliminato"]}}
    pending = await db["documents_inbox"].count_documents({
        **inbox_active,
        "processed": {"$ne": True},
    })
    errors = await db["documents_inbox"].count_documents({
        **inbox_active,
        "status": {"$in": ["errore", "error", "failed"]},
    })
    without_payload = await db["documents_inbox"].count_documents({
        **inbox_active,
        "$or": [
            {"pdf_data": {"$exists": False}},
            {"pdf_data": None},
            {"pdf_data": ""},
        ],
    })
    unassociated = await db["documenti_non_associati"].count_documents({
        "associato": {"$ne": True},
        "status": {"$nin": ["deleted", "archived", "eliminato"]},
    })

    return ComplianceSnapshot(
        active_users=len(users),
        active_users_with_invalid_role=invalid_roles,
        active_users_without_name=without_name,
        audit_records=audit_records,
        audit_records_complete=complete,
        audit_records_missing_actor=missing_actor,
        audit_records_missing_timestamp=missing_timestamp,
        audit_records_missing_entity_reference=missing_entity,
        audit_coverage_percent=coverage,
        inbox_documents_pending=pending,
        inbox_documents_in_error=errors,
        inbox_documents_without_payload=without_payload,
        documents_unassociated=unassociated,
        permissions_write_supported=False,
        audit_write_supported=False,
        document_link_supported=False,
    )
