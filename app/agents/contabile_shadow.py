"""Agente Contabile shadow: osserva quadrature e propone, senza registrare."""

import hashlib
import json

from app.agents.decision_engine import crea_decisione
from app.agents.models import DecisioneInput, LivelloAutonomia, LivelloRischio, Reversibilita
from app.services.contabile_shadow_service import leggi_snapshot_contabile


class ContabileShadow:
    nome = "ContabileShadow"

    @staticmethod
    def _chiave(tipo: str, snapshot: dict) -> str:
        impronta = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        return f"contabile:{tipo}:{impronta}"

    async def run(self, db):
        snapshot = (await leggi_snapshot_contabile(db)).to_dict()

        if not snapshot["disponibile"]:
            proposta = DecisioneInput(
                decision_key=self._chiave("report-assente", snapshot),
                semantic_key="contabile:report-assente",
                agent=self.nome,
                objective="Rendere disponibile un collaudo contabile aggiornato",
                input_sources=[{"type": "typed_service", "service": "contabile_snapshot"}],
                facts=[{"report_disponibile": False}],
                assumptions=["Senza un report non vengono formulate correzioni contabili"],
                rule_ids=["ACCOUNTING-SHADOW-001", "DATA-QUALITY-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Eseguire il collaudo canonico e riesaminare l'esito",
                },
                confidence=1.0,
                financial_impact=0.0,
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                explanation=(
                    "Non esiste una fotografia contabile utilizzabile. Nessuna scrittura, "
                    "rettifica o modifica e' stata proposta o eseguita."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            )
            await crea_decisione(db, proposta)
            return

        if not snapshot["obsoleto"] and not snapshot["checks_in_errore"] and not snapshot["checks_violati"]:
            return

        ha_violazioni = snapshot["checks_violati"] > 0
        richiede_revisione = ha_violazioni or snapshot["checks_in_errore"] > 0
        tipo = "anomalie" if richiede_revisione else "report-obsoleto"
        fatti = {
            "report_id": snapshot["report_id"],
            "checks_totali": snapshot["checks_totali"],
            "checks_violati": snapshot["checks_violati"],
            "checks_in_errore": snapshot["checks_in_errore"],
            "violazioni_totali": snapshot["violazioni_totali"],
            "violazioni_critiche": snapshot["violazioni_critiche"],
            "report_obsoleto": snapshot["obsoleto"],
        }
        proposta = DecisioneInput(
            decision_key=self._chiave(tipo, snapshot),
            semantic_key=f"contabile:{tipo}",
            agent=self.nome,
            objective=(
                f"Verificare {snapshot['violazioni_totali']} anomalie di quadratura e Prima Nota"
                if ha_violazioni else "Aggiornare il collaudo contabile prima di decidere"
            ),
            input_sources=[{
                "type": "typed_service",
                "service": "contabile_snapshot",
                "report_id": snapshot["report_id"],
            }],
            facts=[fatti],
            assumptions=[
                "Il collaudo segnala incoerenze ma non dimostra da solo quale rettifica sia corretta",
                "Ogni eventuale scrittura richiede evidenza documentale e approvazione separata",
            ],
            rule_ids=["ACCOUNTING-SHADOW-001", "HUMAN-APPROVAL-001"],
            alternatives=[
                {"type": "verify_source_documents", "label": "Verificare i documenti originari"},
                {"type": "verify_bank_evidence", "label": "Verificare i riscontri bancari"},
                {"type": "prepare_separate_correction", "label": "Preparare una rettifica separata"},
            ] if richiede_revisione else [],
            recommended_action={
                "type": "human_review" if richiede_revisione else "recommendation",
                "description": (
                    "Esaminare le evidenze dei controlli violati; ogni rettifica resta separata e approvata"
                    if richiede_revisione else "Eseguire nuovamente il collaudo canonico"
                ),
            },
            confidence=0.7 if snapshot["checks_in_errore"] or snapshot["obsoleto"] else 1.0,
            financial_impact=0.0,
            risk_level=(
                LivelloRischio.HIGH if snapshot["violazioni_critiche"] or snapshot["checks_in_errore"]
                else LivelloRischio.MEDIUM
            ),
            reversibility=Reversibilita.FULL,
            autonomy_level=LivelloAutonomia.L3 if richiede_revisione else LivelloAutonomia.L1,
            approver_role="admin",
            explanation=(
                "La proposta deriva da conteggi aggregati del collaudo. Non contiene esempi, "
                "anagrafiche o documenti e non crea movimenti contabili."
            ),
            metadata={"shadow_mode": True, "snapshot": snapshot},
        )
        await crea_decisione(db, proposta)
