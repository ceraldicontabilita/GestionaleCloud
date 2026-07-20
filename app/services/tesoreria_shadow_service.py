"""Lettura tipizzata e deterministica dei dati per l'agente Tesoreria.

Il servizio non modifica alcuna collection e non espone strumenti di pagamento.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FasciaScadenze:
    count: int
    total: str
    first_due_date: Optional[str]
    last_due_date: Optional[str]


@dataclass(frozen=True)
class TesoreriaSnapshot:
    reference_date: str
    horizon_days: int
    overdue: FasciaScadenze
    upcoming: FasciaScadenze

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _importo(doc: Dict[str, Any]) -> Decimal:
    raw = doc.get("importo_residuo")
    if raw is None:
        raw = doc.get("importo_rata")
    if raw is None:
        raw = doc.get("importo", 0)
    try:
        testo = str(raw or 0).strip()
        if "," in testo:
            testo = testo.replace(".", "").replace(",", ".")
        return abs(Decimal(testo))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fascia(docs: List[Dict[str, Any]]) -> FasciaScadenze:
    date_valide = sorted(str(d.get("data_scadenza")) for d in docs if d.get("data_scadenza"))
    totale = sum((_importo(doc) for doc in docs), Decimal("0"))
    return FasciaScadenze(
        count=len(docs),
        total=f"{totale.quantize(Decimal('0.01'))}",
        first_due_date=date_valide[0] if date_valide else None,
        last_due_date=date_valide[-1] if date_valide else None,
    )


async def leggi_snapshot_tesoreria(
    db,
    reference_date: Optional[date] = None,
    horizon_days: int = 30,
) -> TesoreriaSnapshot:
    """Restituisce soli aggregati di scadenze aperte, senza dati personali."""
    oggi = reference_date or date.today()
    fine = oggi + timedelta(days=horizon_days)
    base = {
        "pagato": {"$ne": True},
        "stato": {"$nin": ["pagata", "pagato", "chiusa", "annullata"]},
    }
    projection = {
        "_id": 0,
        "data_scadenza": 1,
        "importo_residuo": 1,
        "importo_rata": 1,
        "importo": 1,
    }
    overdue = await db["scadenziario_fornitori"].find(
        {**base, "data_scadenza": {"$lt": oggi.isoformat()}}, projection
    ).sort("data_scadenza", 1).to_list(10000)
    upcoming = await db["scadenziario_fornitori"].find(
        {**base, "data_scadenza": {"$gte": oggi.isoformat(), "$lte": fine.isoformat()}},
        projection,
    ).sort("data_scadenza", 1).to_list(10000)
    return TesoreriaSnapshot(
        reference_date=oggi.isoformat(),
        horizon_days=horizon_days,
        overdue=_fascia(overdue),
        upcoming=_fascia(upcoming),
    )
