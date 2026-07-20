"""Agente CFO cash flow: osserva gli aggregati a 13 settimane e propone."""

import hashlib
import json

from app.agents.decision_engine import crea_decisione
from app.agents.models import DecisioneInput, LivelloAutonomia, LivelloRischio, Reversibilita
from app.services.cash_flow_13w_service import calcola_cash_flow_13_settimane


class CashFlow13WShadow:
    nome = "CashFlow13WShadow"

    async def run(self, db):
        previsione = await calcola_cash_flow_13_settimane(db)
        base = next(s for s in previsione["scenari"] if s["nome"] == "base")
        stress = next(s for s in previsione["scenari"] if s["nome"] == "stress")
        negativo = min(base["saldo_minimo"], stress["saldo_minimo"]) < 0
        impronta = hashlib.sha256(
            json.dumps(previsione, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        proposta = DecisioneInput(
            decision_key=f"cashflow13w:{previsione['data_riferimento']}:{impronta}",
            semantic_key="cashflow13w:previsione",
            agent=self.nome,
            objective="Gestire una possibile tensione di liquidita a 13 settimane" if negativo
            else "Verificare la previsione di liquidita a 13 settimane",
            input_sources=[
                {"type": "typed_service", "service": "cash_flow_13w", "version": previsione["versione_regole"]}
            ],
            facts=[{
                "liquidita_iniziale": previsione["liquidita_iniziale"],
                "saldo_minimo_base": base["saldo_minimo"],
                "saldo_minimo_stress": stress["saldo_minimo"],
                "copertura_percentuale": previsione["qualita_dati"]["copertura_percentuale"],
            }],
            assumptions=previsione["assunzioni"],
            rule_ids=["CF13W-001", "HUMAN-APPROVAL-001"] if negativo else ["CF13W-001"],
            alternatives=[
                {"type": "accelerate_receivables", "label": "Valutare l'anticipo degli incassi"},
                {"type": "reschedule_optional_outflows", "label": "Rivedere solo le uscite rinviabili"},
                {"type": "prepare_financing_review", "label": "Preparare una valutazione finanziaria"},
            ] if negativo else [],
            recommended_action={
                "type": "human_review" if negativo else "recommendation",
                "description": "Esaminare gli scenari e i dati esclusi prima di qualsiasi azione"
                if negativo else "Monitorare settimanalmente lo scenario prudente",
            },
            confidence=1.0 if previsione["qualita_dati"]["record_esclusi"] == 0 else 0.8,
            financial_impact=abs(min(0, stress["saldo_minimo"])),
            risk_level=LivelloRischio.HIGH if negativo else LivelloRischio.MEDIUM,
            reversibility=Reversibilita.FULL,
            autonomy_level=LivelloAutonomia.L3 if negativo else LivelloAutonomia.L1,
            approver_role="admin",
            explanation=(
                f"Lo scenario base raggiunge un minimo di euro {base['saldo_minimo']:.2f}; "
                f"lo scenario stress euro {stress['saldo_minimo']:.2f}. "
                "La previsione e' informativa: nessun pagamento o movimento e' stato creato."
            ),
            metadata={"shadow_mode": True, "forecast": previsione},
        )
        await crea_decisione(db, proposta)
