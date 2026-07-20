"""Agente Fiscale shadow: osserva aggregati, non calcola o versa imposte."""

import hashlib
import json
from decimal import Decimal

from app.agents.decision_engine import crea_decisione
from app.agents.models import DecisioneInput, LivelloAutonomia, LivelloRischio, Reversibilita
from app.services.fiscale_shadow_service import leggi_snapshot_fiscale


class FiscaleShadow:
    nome = "FiscaleShadow"

    @staticmethod
    def _key(tipo: str, snapshot: dict) -> str:
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        return f"fiscale:{tipo}:{digest}"

    async def run(self, db):
        snapshot = (await leggi_snapshot_fiscale(db)).to_dict()
        overdue_count = snapshot["f24_overdue"]["count"] + snapshot["withholding_overdue"]["count"]
        overdue_total = Decimal(snapshot["f24_overdue"]["total"]) + Decimal(snapshot["withholding_overdue"]["total"])
        upcoming_count = snapshot["f24_upcoming"]["count"] + snapshot["withholding_upcoming"]["count"]
        upcoming_total = Decimal(snapshot["f24_upcoming"]["total"]) + Decimal(snapshot["withholding_upcoming"]["total"])

        if overdue_count:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("scaduti", snapshot),
                agent=self.nome,
                objective=f"Verificare {overdue_count} obblighi fiscali scaduti",
                input_sources=[{"type": "typed_service", "service": "fiscale_snapshot"}],
                facts=[{"count": overdue_count, "total": str(overdue_total)}],
                assumptions=[
                    "Lo stato aperto non prova che il versamento non sia avvenuto fuori dal gestionale",
                    "Importi, ravvedimenti e istruzioni devono essere verificati da una persona competente",
                ],
                rule_ids=["FISCAL-SHADOW-001", "HUMAN-APPROVAL-001"],
                alternatives=[
                    {"type": "verify_payment_evidence", "label": "Verificare quietanze e banca"},
                    {"type": "consult_accountant", "label": "Richiedere verifica al commercialista"},
                ],
                recommended_action={
                    "type": "human_review",
                    "description": "Verificare evidenze e stato prima di preparare qualunque adempimento",
                },
                confidence=0.8 if snapshot["records_without_due_date"] or snapshot["records_without_amount"] else 1.0,
                financial_impact=float(overdue_total),
                risk_level=LivelloRischio.HIGH,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L3,
                approver_role="admin",
                explanation=(
                    "La fotografia mostra obblighi aperti oltre data. Nessun F24 e' stato creato, "
                    "nessun pagamento e nessun invio e' stato eseguito."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        if upcoming_count:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("imminenti", snapshot),
                agent=self.nome,
                objective=f"Pianificare la verifica di {upcoming_count} obblighi fiscali imminenti",
                input_sources=[{"type": "typed_service", "service": "fiscale_snapshot"}],
                facts=[{"count": upcoming_count, "total": str(upcoming_total)}],
                assumptions=["Le date sono quelle esplicitamente registrate, senza stime"],
                rule_ids=["FISCAL-HORIZON-015"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Controllare documenti e disponibilita' prima delle scadenze",
                },
                confidence=1.0,
                financial_impact=float(upcoming_total),
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                explanation="Raccomandazione informativa: nessuna disposizione viene preparata.",
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))

        iva_ok = snapshot["previous_vat_status"].upper() in {"CONFERMATA", "TRASMESSA"}
        if not iva_ok or not snapshot["accountant_prima_nota_sent"]:
            await crea_decisione(db, DecisioneInput(
                decision_key=self._key("completezza", snapshot),
                agent=self.nome,
                objective=f"Verificare la completezza fiscale del periodo {snapshot['previous_vat_period']}",
                input_sources=[{"type": "typed_service", "service": "fiscale_snapshot"}],
                facts=[{
                    "vat_status": snapshot["previous_vat_status"],
                    "accountant_prima_nota_sent": snapshot["accountant_prima_nota_sent"],
                    "records_without_due_date": snapshot["records_without_due_date"],
                    "records_without_amount": snapshot["records_without_amount"],
                }],
                assumptions=["Assenza nel gestionale non equivale ad adempimento omesso"],
                rule_ids=["FISCAL-COMPLETENESS-001"],
                alternatives=[],
                recommended_action={
                    "type": "recommendation",
                    "description": "Controllare liquidazione IVA e invio Prima Nota al commercialista",
                },
                confidence=0.8,
                financial_impact=0.0,
                risk_level=LivelloRischio.MEDIUM,
                reversibility=Reversibilita.FULL,
                autonomy_level=LivelloAutonomia.L1,
                explanation=(
                    "La decisione segnala solo liquidazione IVA e prova di invio della Prima Nota; "
                    "non certifica un pacchetto completo, non afferma un debito e non esegue invii."
                ),
                metadata={"shadow_mode": True, "snapshot": snapshot},
            ))
