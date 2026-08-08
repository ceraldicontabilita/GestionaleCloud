"""Short-lived, in-memory proposals for guarded MCP mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid
from typing import Any, Mapping

from .catalog import ACTION_BY_ID, ActionOperation
from .schemas import PreparedAction


class ProposalError(ValueError):
    pass


@dataclass(slots=True)
class StoredProposal:
    proposal_id: str
    action: ActionOperation
    path_parameters: dict[str, Any]
    query: dict[str, Any]
    body: dict[str, Any]
    reason: str
    payload_sha256: str
    expires_at: datetime
    used: bool = False


class ProposalStore:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, StoredProposal] = {}

    @staticmethod
    def _validate_mapping(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(value)
        if len(result) > 50:
            raise ProposalError(f"{name} contiene troppi campi")
        encoded = json.dumps(result, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > 65_536:
            raise ProposalError(f"{name} supera 64 KiB")
        return result

    def prepare(
        self,
        *,
        action_id: str,
        path_parameters: Mapping[str, Any],
        query: Mapping[str, Any],
        body: Mapping[str, Any],
        reason: str,
    ) -> PreparedAction:
        action = ACTION_BY_ID.get(action_id)
        if action is None:
            raise ProposalError(f"Azione non consentita: {action_id}")
        clean_reason = reason.strip()
        if len(clean_reason) < 10 or len(clean_reason) > 500:
            raise ProposalError("La motivazione deve contenere da 10 a 500 caratteri")
        clean_path = self._validate_mapping("path_parameters", path_parameters)
        clean_query = self._validate_mapping("query", query)
        clean_body = self._validate_mapping("body", body)
        canonical = json.dumps(
            {
                "action_id": action_id,
                "path_parameters": clean_path,
                "query": clean_query,
                "body": clean_body,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        proposal_id = uuid.uuid4().hex[:16]
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        self._items[proposal_id] = StoredProposal(
            proposal_id=proposal_id,
            action=action,
            path_parameters=clean_path,
            query=clean_query,
            body=clean_body,
            reason=clean_reason,
            payload_sha256=digest,
            expires_at=expires_at,
        )
        phrase = f"CONFERMO {proposal_id}"
        return PreparedAction(
            proposal_id=proposal_id,
            action_id=action_id,
            summary=action.description,
            reason=clean_reason,
            expires_at=expires_at.isoformat(timespec="seconds"),
            confirmation_phrase=phrase,
            payload_sha256=digest,
        )

    def consume(self, proposal_id: str, confirmation_phrase: str) -> StoredProposal:
        item = self._items.get(proposal_id)
        if item is None:
            raise ProposalError("Proposta inesistente o già rimossa")
        if item.used:
            raise ProposalError("Proposta già eseguita")
        if datetime.now(timezone.utc) > item.expires_at:
            self._items.pop(proposal_id, None)
            raise ProposalError("Proposta scaduta: crearne una nuova")
        if confirmation_phrase != f"CONFERMO {proposal_id}":
            raise ProposalError("Frase di conferma non valida")
        item.used = True
        return item
