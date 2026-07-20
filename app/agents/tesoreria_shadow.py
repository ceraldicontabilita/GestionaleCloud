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
                semantic_key="tesoreria:overdue",
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
                semantic_key="tesoreria:upcoming",
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

        liquidita = snapshot["liquidity"]
        if Decimal(liquidita["totale"]) < 0:
            proposte.append(DecisioneInput(
                decision_key=self._chiave("liquidita_negativa", snapshot),
                semantic_key="tesoreria:liquidita_negativa",
                agent=self.nome,
                objective="Verificare la liquidità complessiva negativa",
                input_sources=[{
                    "type": "typed_service",
                    "service": "tesoreria_snapshot",
                    "collections": ["prima_nota_cassa", "prima_nota_banca"],
                    "reference_date": snapshot["reference_date"],
                }],
                facts=[{"liquidity": liquidita}],
                assumptions=["I saldi usano il motore unico della Prima Nota e i riporti configurati"],
                rule_ids=["TREASURY-LIQUIDITY-001", "HUMAN-APPROVAL-001"],
                alternatives=[
                    {"type": "verify_opening_balances", "label": "Verificare i saldi iniziali"},
                    {"type": "review_unreconciled_records", "label": "Verificare le evidenze non riconciliate"},
                    {"type": "prepare_cash_plan", "label": "Preparare un piano di cassa da approvare"},
                ],
                recommended_action={
                    "type": "human_review",
                    "description": "Verificare saldi ed evidenze prima di qualsiasi intervento finanziario",
                },
                confidence=1.0,
                financial_impact=abs(float(Decimal(liquidita["totale"]))),
                risk_level=LivelloRischio.HIGH,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L3,
                approver_role="admin",
                explanation=(
                    f"Cassa e banca producono una liquidità complessiva di € {liquidita['totale']}. "
                    "L'agente non modifica saldi e non dispone pagamenti."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        pendenti = snapshot["pending_checks"]
        if any(voce["count"] for voce in pendenti.values()):
            totale_pendente = sum((Decimal(voce["total"]) for voce in pendenti.values()), Decimal("0"))
            proposte.append(DecisioneInput(
                decision_key=self._chiave("riconciliazioni_pendenti", snapshot),
                semantic_key="tesoreria:riconciliazioni_pendenti",
                agent=self.nome,
                objective="Verificare assegni, bonifici e PayPal non riconciliati",
                input_sources=[{
                    "type": "typed_service",
                    "service": "tesoreria_snapshot",
                    "collections": ["assegni", "bonifici_transfers", "paypal_transactions"],
                    "reference_date": snapshot["reference_date"],
                }],
                facts=[{"pending_checks": pendenti}],
                assumptions=["Non riconciliato significa privo di evidenza bancaria completa, non necessariamente errato"],
                rule_ids=["TREASURY-RECONCILIATION-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Esaminare le code e confermare solo gli abbinamenti supportati da evidenze",
                },
                confidence=1.0,
                financial_impact=float(totale_pendente),
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                approver_role="admin",
                explanation=(
                    "La fotografia aggregata contiene elementi ancora da verificare. "
                    "Nessuna riconciliazione viene applicata automaticamente."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        pos = snapshot["pos"]
        if pos["giorni_senza_evidenza_banca"] or pos["giorni_importo_non_coerente"]:
            proposte.append(DecisioneInput(
                decision_key=self._chiave("pos_evidenze", snapshot),
                semantic_key="tesoreria:pos_evidenze",
                agent=self.nome,
                objective="Verificare le chiusure POS senza riscontro bancario coerente",
                input_sources=[{
                    "type": "typed_service",
                    "service": "tesoreria_snapshot",
                    "collections": ["chiusure_pos_manuali", "estratto_conto_movimenti"],
                    "reference_date": snapshot["reference_date"],
                }],
                facts=[{"pos": pos}],
                assumptions=["La causale NUMIA con giorno DEL identifica il giorno operativo del terminale"],
                rule_ids=["TREASURY-POS-EVIDENCE-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Controllare il dettaglio POS e l'estratto conto senza creare accrediti sintetici",
                },
                confidence=1.0,
                financial_impact=0.0,
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                approver_role="admin",
                explanation=(
                    f"Risultano {pos['giorni_senza_evidenza_banca']} giorni senza evidenza bancaria e "
                    f"{pos['giorni_importo_non_coerente']} giorni con importo diverso. "
                    "Il controllo usa solo accrediti reali dell'estratto conto."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        for proposta in proposte:
            await crea_decisione(db, proposta)
