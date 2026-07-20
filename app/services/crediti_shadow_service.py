"""Aging crediti aggregato per decisioni supervisionate.

Il servizio legge esclusivamente fatture emesse gia' materializzate nel
gestionale. Non invia comunicazioni, non modifica fatture e non presume che
l'assenza di una registrazione equivalga a un mancato pagamento reale.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional


CENT = Decimal("0.01")
STATI_CHIUSI = frozenset({
    "pagato", "pagata", "paid", "chiuso", "chiusa", "closed",
    "annullato", "annullata", "cancelled", "deleted", "stornato", "stornata",
})
TIPI_NOTA_CREDITO = frozenset({
    "td04", "nota_credito", "nota di credito", "credit_note", "credit note",
})


@dataclass(frozen=True)
class FasciaCrediti:
    count: int
    total: str


@dataclass(frozen=True)
class CreditiSnapshot:
    reference_date: str
    overdue: FasciaCrediti
    not_due: FasciaCrediti
    oldest_due_date: Optional[str]
    max_days_overdue: int
    overdue_by_month: List[Dict[str, Any]]
    records_without_due_date: int
    records_without_amount: int
    credit_notes_excluded: int
    reminder_draft_supported: bool
    reminder_send_supported: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _raw_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        parsed = Decimal(text)
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _first_decimal(doc: Dict[str, Any], fields: Iterable[str]) -> Optional[Decimal]:
    for field in fields:
        value = _raw_decimal(doc.get(field))
        if value is not None:
            return value
    return None


def _residual(doc: Dict[str, Any]) -> Optional[Decimal]:
    explicit = _first_decimal(doc, ("importo_residuo", "residuo"))
    if explicit is not None:
        return max(Decimal("0"), explicit)
    total = _first_decimal(doc, ("totale", "total_amount", "importo_totale"))
    if total is None:
        return None
    paid = _first_decimal(doc, ("importo_pagato", "paid_amount")) or Decimal("0")
    return max(Decimal("0"), total - paid)


def _due_date(doc: Dict[str, Any]) -> Optional[date]:
    for field in ("data_scadenza", "due_date", "scadenza"):
        raw = doc.get(field)
        if raw in (None, ""):
            continue
        try:
            if isinstance(raw, datetime):
                return raw.date()
            if isinstance(raw, date):
                return raw
            return date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            continue
    return None


def _is_open(doc: Dict[str, Any]) -> bool:
    if doc.get("pagato") is True:
        return False
    states = {
        str(doc.get(field) or "").strip().lower()
        for field in ("stato", "status", "stato_pagamento", "payment_status")
    }
    return not bool(states & STATI_CHIUSI)


def _is_credit_note(doc: Dict[str, Any]) -> bool:
    types = {
        str(doc.get(field) or "").strip().lower()
        for field in ("tipo_documento", "document_type", "tipo", "invoice_type")
    }
    return bool(types & TIPI_NOTA_CREDITO)


def _bucket(rows: List[tuple[date, Decimal]]) -> FasciaCrediti:
    total = sum((amount for _, amount in rows), Decimal("0"))
    return FasciaCrediti(
        count=len(rows),
        total=str(total.quantize(CENT, rounding=ROUND_HALF_UP)),
    )


async def leggi_snapshot_crediti(
    db, reference_date: Optional[date] = None
) -> CreditiSnapshot:
    oggi = reference_date or date.today()
    docs = await db["fatture_emesse"].find(
        {},
        {
            "_id": 0, "pagato": 1, "stato": 1, "status": 1,
            "stato_pagamento": 1, "payment_status": 1,
            "tipo_documento": 1, "document_type": 1, "tipo": 1,
            "invoice_type": 1, "data_scadenza": 1, "due_date": 1,
            "scadenza": 1, "importo_residuo": 1, "residuo": 1,
            "totale": 1, "total_amount": 1, "importo_totale": 1,
            "importo_pagato": 1, "paid_amount": 1,
        },
    ).to_list(20000)

    overdue: List[tuple[date, Decimal]] = []
    not_due: List[tuple[date, Decimal]] = []
    without_due = 0
    without_amount = 0
    credit_notes = 0

    for doc in docs:
        if not _is_open(doc):
            continue
        if _is_credit_note(doc):
            credit_notes += 1
            continue
        amount = _residual(doc)
        if amount is None:
            without_amount += 1
            continue
        if amount <= 0:
            continue
        due = _due_date(doc)
        if not due:
            without_due += 1
            continue
        if due < oggi:
            overdue.append((due, amount))
        else:
            not_due.append((due, amount))

    months: Dict[str, List[Decimal]] = {}
    for due, amount in overdue:
        months.setdefault(due.strftime("%Y-%m"), []).append(amount)
    overdue_by_month = [
        {
            "month": month,
            "count": len(amounts),
            "total": str(sum(amounts, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)),
        }
        for month, amounts in sorted(months.items())
    ]
    oldest = min((due for due, _ in overdue), default=None)

    return CreditiSnapshot(
        reference_date=oggi.isoformat(),
        overdue=_bucket(overdue),
        not_due=_bucket(not_due),
        oldest_due_date=oldest.isoformat() if oldest else None,
        max_days_overdue=(oggi - oldest).days if oldest else 0,
        overdue_by_month=overdue_by_month,
        records_without_due_date=without_due,
        records_without_amount=without_amount,
        credit_notes_excluded=credit_notes,
        reminder_draft_supported=True,
        reminder_send_supported=False,
    )
