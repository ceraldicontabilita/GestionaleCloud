"""Indicatori acquisti aggregati; nessuna giacenza o proposta d'ordine."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AcquistiSnapshot:
    reference_date: str
    lookback_days: int
    products_observed: int
    price_increase_products: int
    max_price_increase_pct: float
    single_supplier_products: int
    records_excluded: int
    reorder_supported: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _date_value(doc: Dict[str, Any]) -> Optional[date]:
    raw = doc.get("data_fattura") or doc.get("data")
    try:
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        return date.fromisoformat(str(raw)[:10]) if raw else None
    except (TypeError, ValueError):
        return None


def _price(doc: Dict[str, Any]) -> Optional[Decimal]:
    raw = doc.get("prezzo_unitario")
    try:
        value = Decimal(str(raw)).copy_abs()
        return value if value > 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


async def leggi_snapshot_acquisti(
    db, reference_date: Optional[date] = None, lookback_days: int = 180
) -> AcquistiSnapshot:
    oggi = reference_date or date.today()
    inizio = oggi - timedelta(days=lookback_days)
    docs = await db["acquisti_prodotti"].find(
        {}, {"_id": 0, "prodotto_id": 1, "descrizione_normalizzata": 1,
             "data_fattura": 1, "data": 1, "prezzo_unitario": 1,
             "unita_misura": 1, "fornitore_id": 1, "fornitore": 1}
    ).to_list(50000)
    groups: Dict[str, list] = {}
    excluded = 0
    for doc in docs:
        key = str(doc.get("prodotto_id") or doc.get("descrizione_normalizzata") or "").strip()
        when, price = _date_value(doc), _price(doc)
        unit = str(doc.get("unita_misura") or "").strip().lower()
        supplier = str(doc.get("fornitore_id") or doc.get("fornitore") or "").strip()
        if not key or not when or not price or when < inizio or when > oggi:
            excluded += 1
            continue
        groups.setdefault(key, []).append((when, price, unit, supplier))

    increases = []
    concentration = 0
    for rows in groups.values():
        rows.sort(key=lambda item: item[0])
        if len(rows) >= 2:
            previous, latest = rows[-2], rows[-1]
            if previous[2] == latest[2] and latest[1] > previous[1]:
                pct = float(((latest[1] - previous[1]) / previous[1]) * 100)
                if pct >= 10:
                    increases.append(pct)
        suppliers = {row[3] for row in rows if row[3]}
        if len(rows) >= 3 and len(suppliers) == 1:
            concentration += 1

    return AcquistiSnapshot(
        reference_date=oggi.isoformat(),
        lookback_days=lookback_days,
        products_observed=len(groups),
        price_increase_products=len(increases),
        max_price_increase_pct=round(max(increases, default=0), 2),
        single_supplier_products=concentration,
        records_excluded=excluded,
        reorder_supported=False,
    )
