"""Agente Crediti shadow: aging e bozze interne, nessun invio."""

import hashlib
import json

from app.agents.decision_engine import crea_decisione
from app.agents.models import DecisioneInput, LivelloAutonomia, LivelloRischio, Reversibilita
from app.services.crediti_shadow_service import leggi_snapshot_crediti


class CreditiShadow:
    nome = "CreditiShadow"

    @staticmethod
    def _key(kind: str, snapshot: dict) -> str:
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        return f"crediti:{kind}:{digest}"

    async def run(self, db):
        snapshot = (await leggi_snapshot_crediti(db)).to_dict()
        missing = snapshot["records_without_due_date"] + snapshot["records_without_amount"]

        if snapshot["overdue"]["count"]:
            draft = (
                "Gentile cliente, dai dati interni risultano partite scadute. "
                "Salvo pagamento gia' disposto o non ancora registrato, chiediamo "
                "di verificare la posizione con il nostro ufficio amministrativo."
            )
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("scaduti", snapshot),
                semantic_key="crediti:scaduti",
                agent=self.nome,
                objective=f"Verificare {snapshot['overdue']['count']} crediti scaduti",
                input_sources=[{
                    "type": "typed_service",
                    "service": "crediti_snapshot",
                    "collection": "fatture_emesse",
                }],
                facts=[{
                    "count": snapshot["overdue"]["count"],
                    "total": snapshot["overdue"]["total"],
                    "oldest_due_date": snapshot["oldest_due_date"],
                    "max_days_overdue": snapshot["max_days_overdue"],
                    "overdue_by_month": snapshot["overdue_by_month"],
                    "reminder_send_supported": False,
                }],
                assumptions=[
                    "Lo stato aperto non prova che l'incasso non sia avvenuto fuori dal gestionale",
                    "Evidenze bancarie e posizione del cliente devono essere verificate prima di usare la bozza",
                    "La bozza e' generica e non contiene dati identificativi del cliente",
                ],
                rule_ids=["CREDIT-AGING-001", "CREDIT-REMINDER-DRAFT-001", "HUMAN-APPROVAL-001"],
                alternatives=[
                    {"type": "verify_bank_evidence", "label": "Verificare prima gli incassi bancari"},
                    {"type": "hold_draft", "label": "Non utilizzare la bozza e mantenere la verifica interna"},
                ],
                recommended_action={
                    "type": "human_review",
                    "description": "Verificare le evidenze e valutare la bozza interna",
                    "draft": draft,
                    "send": False,
                },
                confidence=0.8 if missing else 1.0,
                financial_impact=float(snapshot["overdue"]["total"]),
                risk_level=LivelloRischio.HIGH,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L3,
                approver_role="admin",
                explanation=(
                    "L'aging usa solo date e residui registrati. La bozza resta nel registro "
                    "decisionale: nessuna email, PEC, notifica o comunicazione e' stata inviata."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot, "outbound_enabled": False},
            ))

        if missing:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("qualita", snapshot),
                semantic_key="crediti:qualita",
                agent=self.nome,
                objective="Verificare i dati incompleti nell'aging crediti",
                input_sources=[{"type": "typed_service", "service": "crediti_snapshot"}],
                facts=[{
                    "records_without_due_date": snapshot["records_without_due_date"],
                    "records_without_amount": snapshot["records_without_amount"],
                }],
                assumptions=["I record incompleti sono esclusi dall'aging e non vengono stimati"],
                rule_ids=["CREDIT-DATA-QUALITY-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Completare data di scadenza e residuo dalla fonte documentale",
                },
                confidence=1.0,
                financial_impact=0.0,
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                explanation="Nessun valore mancante viene ricostruito o inventato.",
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))
