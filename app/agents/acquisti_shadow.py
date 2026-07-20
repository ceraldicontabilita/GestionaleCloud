"""Agente Acquisti shadow: osserva prezzi e dipendenze, non ordina."""

import hashlib
import json

from app.agents.decision_engine import crea_decisione
from app.agents.models import DecisioneInput, LivelloAutonomia, LivelloRischio, Reversibilita
from app.services.acquisti_shadow_service import leggi_snapshot_acquisti


class AcquistiShadow:
    nome = "AcquistiShadow"

    async def run(self, db):
        snapshot = (await leggi_snapshot_acquisti(db)).to_dict()
        if not snapshot["price_increase_products"] and not snapshot["single_supplier_products"]:
            return
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        await crea_decisione(db, DecisioneInput(
            decision_key=f"acquisti:indicatori:{digest}",
            agent=self.nome,
            objective="Verificare prezzi di acquisto e dipendenza dai fornitori",
            input_sources=[{"type": "typed_service", "service": "acquisti_snapshot"}],
            facts=[{
                "products_observed": snapshot["products_observed"],
                "price_increase_products": snapshot["price_increase_products"],
                "max_price_increase_pct": snapshot["max_price_increase_pct"],
                "single_supplier_products": snapshot["single_supplier_products"],
                "records_excluded": snapshot["records_excluded"],
                "reorder_supported": False,
            }],
            assumptions=[
                "Lo storico fatture misura acquisti, non consumo o giacenza fisica",
                "Prodotti con descrizioni diverse possono richiedere normalizzazione manuale",
            ],
            rule_ids=["PURCHASE-PRICE-001", "NO-INVENTORY-NO-REORDER-001"],
            alternatives=[],
            recommended_action={
                "type": "recommendation",
                "description": "Rivedere manualmente i listini e valutare alternative di fornitura",
            },
            confidence=0.8 if snapshot["records_excluded"] else 1.0,
            financial_impact=0.0,
            risk_level=LivelloRischio.MEDIUM,
            reversibility=Reversibilita.FULL,
            autonomy_level=LivelloAutonomia.L1,
            explanation=(
                "Sono indicatori aggregati. Nessuna quantita' di riordino, ordine, richiesta "
                "al fornitore o movimento di magazzino e' stato creato."
            ),
            metadata={"shadow_mode": True, "snapshot": snapshot},
        ))
