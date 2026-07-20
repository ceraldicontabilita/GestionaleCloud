"""Snapshot fiscale aggregato per decisioni supervisionate.

Legge esclusivamente dati gia' materializzati dal gestionale. Non interpreta
documenti, non calcola imposte, non prepara F24 e non effettua invii.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional


STATI_CHIUSI = frozenset({
    "pagato", "pagata", "paid", "quietanzato", "quietanzata",
    "annullato", "annullata", "cancelled", "deleted",
    "eliminato", "pagata_puntuale", "pagata_con_ravvedimento",
    "pagata_in_ritardo_senza_ravvedimento",
})
CENT = Decimal("0.01")


@dataclass(frozen=True)
class FasciaFiscale:
    count: int
    total: str
    earliest_due_date: Optional[str]


@dataclass(frozen=True)
class FiscaleSnapshot:
    reference_date: str
    horizon_days: int
    f24_overdue: FasciaFiscale
    f24_upcoming: FasciaFiscale
    withholding_overdue: FasciaFiscale
    withholding_upcoming: FasciaFiscale
    previous_vat_period: str
    previous_vat_status: str
    accountant_prima_nota_period: str
    accountant_prima_nota_sent: bool
    records_without_due_date: int
    records_without_amount: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _nested(doc: Dict[str, Any], field: str) -> Any:
    value: Any = doc
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _amount(doc: Dict[str, Any], fields: Iterable[str]) -> Optional[Decimal]:
    for field in fields:
        raw = _nested(doc, field)
        if raw in (None, ""):
            continue
        try:
            text = str(raw).strip()
            if "," in text:
                text = text.replace(".", "").replace(",", ".")
            value = Decimal(text).copy_abs()
            if value > 0:
                return value
        except (InvalidOperation, ValueError):
            continue
    return None


def _due_date(doc: Dict[str, Any], fields: Iterable[str]) -> Optional[date]:
    for field in fields:
        raw = _nested(doc, field)
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
    stati = {
        str(doc.get(field) or "").strip().lower()
        for field in ("stato", "status", "stato_pagamento")
    }
    return not bool(stati & STATI_CHIUSI)


def _bucket(rows: List[tuple[date, Decimal]]) -> FasciaFiscale:
    totale = sum((amount for _, amount in rows), Decimal("0"))
    return FasciaFiscale(
        count=len(rows),
        total=str(totale.quantize(CENT, rounding=ROUND_HALF_UP)),
        earliest_due_date=min((due for due, _ in rows), default=None).isoformat()
        if rows else None,
    )


def _previous_month(reference: date) -> tuple[int, int]:
    if reference.month == 1:
        return reference.year - 1, 12
    return reference.year, reference.month - 1


async def leggi_snapshot_fiscale(
    db,
    reference_date: Optional[date] = None,
    horizon_days: int = 15,
) -> FiscaleSnapshot:
    oggi = reference_date or date.today()
    fine = oggi + timedelta(days=horizon_days)
    f24_overdue: List[tuple[date, Decimal]] = []
    f24_upcoming: List[tuple[date, Decimal]] = []
    withholding_overdue: List[tuple[date, Decimal]] = []
    withholding_upcoming: List[tuple[date, Decimal]] = []
    senza_data = 0
    senza_importo = 0

    f24_docs = await db["f24_unificato"].find(
        {},
        {
            "_id": 0, "pagato": 1, "stato": 1, "status": 1,
            "stato_pagamento": 1, "scadenza": 1, "data_scadenza": 1,
            "data_versamento": 1, "importo_totale": 1, "totale": 1,
            "saldo_finale": 1, "totale_versato": 1, "importo": 1,
            "totali.saldo_finale": 1, "totali.saldo_netto": 1,
        },
    ).to_list(10000)
    for doc in f24_docs:
        if not _is_open(doc):
            continue
        due = _due_date(doc, ("scadenza", "data_scadenza", "data_versamento"))
        amount = _amount(doc, (
            "importo_totale", "totale", "saldo_finale", "totale_versato",
            "importo", "totali.saldo_finale", "totali.saldo_netto",
        ))
        if not due:
            senza_data += 1
        if not amount:
            senza_importo += 1
        if not due or not amount:
            continue
        if due < oggi:
            f24_overdue.append((due, amount))
        elif due <= fine:
            f24_upcoming.append((due, amount))

    withholding_docs = await db["ritenute_acconto"].find(
        {}, {"_id": 0, "stato": 1, "scadenza": 1, "importo": 1}
    ).to_list(10000)
    for doc in withholding_docs:
        if not _is_open(doc):
            continue
        due = _due_date(doc, ("scadenza",))
        amount = _amount(doc, ("importo",))
        if not due:
            senza_data += 1
        if not amount:
            senza_importo += 1
        if not due or not amount:
            continue
        if due < oggi:
            withholding_overdue.append((due, amount))
        elif due <= fine:
            withholding_upcoming.append((due, amount))

    prev_year, prev_month = _previous_month(oggi)
    periodo = f"{prev_year}-{prev_month:02d}"
    liquidazioni = await db["liquidazioni_iva"].find(
        {"periodo": periodo}, {"_id": 0, "stato": 1, "versione": 1}
    ).sort("versione", -1).limit(1).to_list(1)
    iva_status = str(liquidazioni[0].get("stato") or "NON_CLASSIFICATA") if liquidazioni else "ASSENTE"
    package_sent = bool(await db["commercialista_log"].find_one({
        "tipo": "prima_nota_cassa",
        "anno": prev_year,
        "mese": prev_month,
        "success": True,
    }, {"_id": 0, "tipo": 1}))

    return FiscaleSnapshot(
        reference_date=oggi.isoformat(),
        horizon_days=horizon_days,
        f24_overdue=_bucket(f24_overdue),
        f24_upcoming=_bucket(f24_upcoming),
        withholding_overdue=_bucket(withholding_overdue),
        withholding_upcoming=_bucket(withholding_upcoming),
        previous_vat_period=periodo,
        previous_vat_status=iva_status,
        accountant_prima_nota_period=periodo,
        accountant_prima_nota_sent=package_sent,
        records_without_due_date=senza_data,
        records_without_amount=senza_importo,
    )
