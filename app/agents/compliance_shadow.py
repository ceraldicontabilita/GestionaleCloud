"""Agente Compliance shadow: segnala anomalie, non corregge dati o permessi."""

import hashlib
import json

from app.agents.decision_engine import crea_decisione
from app.agents.models import DecisioneInput, LivelloAutonomia, LivelloRischio, Reversibilita
from app.services.compliance_shadow_service import leggi_snapshot_compliance


class ComplianceShadow:
    nome = "ComplianceShadow"

    @staticmethod
    def _key(kind: str, snapshot: dict) -> str:
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        return f"compliance:{kind}:{digest}"

    async def run(self, db):
        snapshot = (await leggi_snapshot_compliance(db)).to_dict()
        invalid_users = (
            snapshot["active_users_with_invalid_role"]
            + snapshot["active_users_without_name"]
        )
        audit_incomplete = snapshot["audit_records"] - snapshot["audit_records_complete"]
        document_gaps = (
            snapshot["inbox_documents_pending"]
            + snapshot["inbox_documents_in_error"]
            + snapshot["inbox_documents_without_payload"]
            + snapshot["documents_unassociated"]
        )

        if invalid_users:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("permessi", snapshot),
                semantic_key="compliance:permessi",
                agent=self.nome,
                objective="Verificare anomalie negli account applicativi attivi",
                input_sources=[{"type": "typed_service", "service": "compliance_snapshot"}],
                facts=[{
                    "active_users": snapshot["active_users"],
                    "invalid_role_count": snapshot["active_users_with_invalid_role"],
                    "missing_name_count": snapshot["active_users_without_name"],
                    "permissions_write_supported": False,
                }],
                assumptions=[
                    "L'amministratore configurato fuori dal database non e' incluso nel conteggio",
                    "La segnalazione non stabilisce quale ruolo debba essere assegnato",
                ],
                rule_ids=["RBAC-VALID-ROLE-001", "HUMAN-APPROVAL-001"],
                alternatives=[{"type": "disable_account_review", "label": "Valutare la disattivazione manuale"}],
                recommended_action={
                    "type": "human_review",
                    "description": "Verificare gli account senza modificare automaticamente ruoli o stato",
                },
                confidence=1.0,
                financial_impact=0.0,
                risk_level=LivelloRischio.HIGH,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L3,
                approver_role="admin",
                explanation="Nessun account, PIN, ruolo o permesso e' stato modificato.",
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        if audit_incomplete:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("audit", snapshot),
                semantic_key="compliance:audit",
                agent=self.nome,
                objective="Verificare la completezza del registro audit",
                input_sources=[{"type": "typed_service", "service": "compliance_snapshot"}],
                facts=[{
                    "audit_records": snapshot["audit_records"],
                    "audit_records_complete": snapshot["audit_records_complete"],
                    "missing_actor": snapshot["audit_records_missing_actor"],
                    "missing_timestamp": snapshot["audit_records_missing_timestamp"],
                    "missing_entity_reference": snapshot["audit_records_missing_entity_reference"],
                    "coverage_percent": snapshot["audit_coverage_percent"],
                    "audit_write_supported": False,
                }],
                assumptions=["Record legacy possono usare uno schema precedente e richiedono verifica umana"],
                rule_ids=["AUDIT-COMPLETENESS-001", "AUDIT-APPEND-ONLY-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Verificare i produttori di eventi incompleti senza riscrivere lo storico",
                },
                confidence=1.0,
                financial_impact=0.0,
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                explanation="Il controllo non modifica, completa o elimina record di audit esistenti.",
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        if document_gaps:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("documenti", snapshot),
                semantic_key="compliance:documenti",
                agent=self.nome,
                objective="Verificare documenti pendenti, in errore o non associati",
                input_sources=[{"type": "typed_service", "service": "compliance_snapshot"}],
                facts=[{
                    "pending": snapshot["inbox_documents_pending"],
                    "errors": snapshot["inbox_documents_in_error"],
                    "without_payload": snapshot["inbox_documents_without_payload"],
                    "unassociated": snapshot["documents_unassociated"],
                    "document_link_supported": False,
                }],
                assumptions=[
                    "Documento pendente o non associato non equivale a documento legalmente mancante",
                    "Nessun contenuto documentale e' stato interpretato da questo controllo",
                ],
                rule_ids=["DOCUMENT-TRACEABILITY-001", "NO-AUTO-LINK-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Rivedere le code documentali dalle rispettive pagine operative",
                },
                confidence=1.0,
                financial_impact=0.0,
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                explanation="Nessun documento viene associato, eliminato o ricreato automaticamente.",
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))
