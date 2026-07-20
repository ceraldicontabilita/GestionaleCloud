"""Agente Tesoreria in shadow mode: osserva e propone, non esegue."""

import hashlib
import json
from decimal import Decimal

from app.agents.decision_engine import crea_decisione
from app.agents.models import (
    DecisioneInput,
    LivelloAutonomia,
    LivelloRischio,
    Reversibilita,
)
from app.services.tesoreria_shadow_service import leggi_snapshot_tesoreria


class TesoreriaShadow:
    nome = "TesoreriaShadow"

    @staticmethod
    def _chiave(tipo: str, snapshot: dict) -> str:
        contenuto = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        impronta = hashlib.sha256(contenuto.encode("utf-8")).hexdigest()[:20]
        return f"tesoreria:{tipo}:{impronta}"

    async def run(self, db):
        snapshot = (await leggi_snapshot_tesoreria(db)).to_dict()
        proposte = []

        overdue = snapshot["overdue"]
        if overdue["count"]:
            proposte.append(DecisioneInput(
                decision_key=self._chiave("overdue", snapshot),
                agent=self.nome,
                objective=f"Verificare {overdue['count']} scadenze fornitore scadute",
                input_sources=[{
                    "type": "typed_service",
                    "service": "tesoreria_snapshot",
                    "reference_date": snapshot["reference_date"],
                }],
                facts=[{
                    "count": overdue["count"],
                    "total": overdue["total"],
                    "first_due_date": overdue["first_due_date"],
                }],
                assumptions=["Le scadenze marcate aperte rappresentano obblighi ancora da verificare"],
                rule_ids=["TREASURY-OVERDUE-001", "HUMAN-APPROVAL-001"],
                alternatives=[
                    {"type": "verify_payment_evidence", "label": "Verificare pagamenti già effettuati"},
                    {"type": "review_due_dates", "label": "Correggere eventuali scadenze errate"},
                    {"type": "prepare_payment_plan", "label": "Preparare un piano da approvare"},
                ],
                recommended_action={
                    "type": "human_review",
                    "description": "Verificare evidenze e priorità prima di qualsiasi disposizione",
                },
                confidence=1.0,
                financial_impact=float(Decimal(overdue["total"])),
                risk_level=LivelloRischio.HIGH,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L3,
                approver_role="admin",
                explanation=(
                    f"Il piano fornitori contiene {overdue['count']} scadenze aperte già decorse, "
                    f"per un totale di € {overdue['total']}. Nessun pagamento è stato preparato o eseguito."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        upcoming = snapshot["upcoming"]
        if upcoming["count"]:
            proposte.append(DecisioneInput(
                decision_key=self._chiave("upcoming", snapshot),
                agent=self.nome,
                objective=f"Pianificare {upcoming['count']} scadenze dei prossimi {snapshot['horizon_days']} giorni",
                input_sources=[{
                    "type": "typed_service",
                    "service": "tesoreria_snapshot",
                    "reference_date": snapshot["reference_date"],
                }],
                facts=[{
                    "count": upcoming["count"],
                    "total": upcoming["total"],
                    "first_due_date": upcoming["first_due_date"],
                    "last_due_date": upcoming["last_due_date"],
                }],
                assumptions=["Le date provengono dallo scadenzario operativo corrente"],
                rule_ids=["TREASURY-HORIZON-030"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Confrontare le uscite previste con la liquidità disponibile",
                },
                confidence=1.0,
                financial_impact=float(Decimal(upcoming["total"])),
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                approver_role="admin",
                explanation=(
                    f"Nei prossimi {snapshot['horizon_days']} giorni risultano {upcoming['count']} "
                    f"scadenze aperte per € {upcoming['total']}. È una raccomandazione, non una disposizione."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        for proposta in proposte:
            await crea_decisione(db, proposta)
