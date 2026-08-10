"""Calcolo ravvedimento esclusivamente da regole legali versionate."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


class RavvedimentoEngine:
    @staticmethod
    def calculate(*, principal: Any, days_late: int, legal_rule: dict | None) -> dict:
        if not legal_rule or not legal_rule.get("version") or not legal_rule.get("effective_from"):
            return {"status": "NOT_DETERMINABLE", "reason": "legal_rule_version_missing"}
        if days_late < 0:
            raise ValueError("days_late non puo essere negativo")
        amount = Decimal(str(principal)).quantize(Decimal("0.01"))
        penalty_rate = Decimal(str(legal_rule.get("penalty_rate") or 0))
        interest_rate = Decimal(str(legal_rule.get("annual_interest_rate") or 0))
        penalty = (amount * penalty_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        interest = (amount * interest_rate * Decimal(days_late) / Decimal(365)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "status": "CALCULATED", "principal": str(amount), "penalty": str(penalty),
            "interest": str(interest), "total": str(amount + penalty + interest),
            "days_late": days_late, "rule_version": legal_rule["version"],
            "effective_from": legal_rule["effective_from"],
        }
