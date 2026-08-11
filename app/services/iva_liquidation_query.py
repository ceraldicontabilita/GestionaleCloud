"""Fonte unica in lettura per calcoli, conteggi e scadenze IVA mensili."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict

from app.engines import liquidazione_iva_engine as liq
from app.services.fiscal_deadlines import monthly_deadline


SERVICE_VERSION = "iva_liquidation_query_v2"


def money_cents(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(
            (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except (InvalidOperation, TypeError, ValueError):
        return 0


def euros(cents: int) -> float:
    return float((Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01")))


def _iva_corrispettivo_cents(doc: Dict[str, Any]) -> int:
    direct = money_cents(doc.get("totale_iva"))
    if direct:
        return direct
    rows = doc.get("riepilogo_iva") or []
    rows_total = sum(
        money_cents(row.get("imposta")) for row in rows if isinstance(row, dict)
    )
    if rows_total:
        return rows_total
    # Non inventare l'IVA da un totale lordo. In assenza dell'imposta XML il
    # periodo deve restare esplicitamente non verificabile.
    return 0


async def corrispettivi_periodo(db, periodo: str) -> Dict[str, Any]:
    docs = await db["corrispettivi"].find(
        {"data": {"$regex": f"^{periodo}"}}, {"_id": 0}
    ).to_list(10000)
    docs = [
        item for item in docs
        if item.get("entity_status") != "deleted"
        and item.get("status") not in ("deleted", "archived")
    ]
    seen: set[str] = set()
    total_cents = 0
    included = 0
    iva_non_verificabile = 0
    for doc in sorted(docs, key=lambda item: str(item.get("created_at") or "")):
        key = str(doc.get("corrispettivo_key") or "").strip()
        if not key:
            key = "|".join((
                str(doc.get("data") or ""),
                str(doc.get("matricola_rt") or doc.get("id_dispositivo") or ""),
                str(money_cents(doc.get("totale") or doc.get("totale_complessivo"))),
            ))
        if key in seen:
            continue
        seen.add(key)
        included += 1
        iva_cents = _iva_corrispettivo_cents(doc)
        total_cents += iva_cents
        if iva_cents == 0 and money_cents(doc.get("totale") or doc.get("totale_complessivo")) > 0:
            iva_non_verificabile += 1
    return {
        "iva_vendite_cents": total_cents,
        "iva_vendite": euros(total_cents),
        "corrispettivi_inclusi": included,
        "corrispettivi_duplicati_esclusi": max(0, len(docs) - included),
        "corrispettivi_iva_non_verificabile": iva_non_verificabile,
    }


def _previous_period(periodo: str) -> str:
    year, month = map(int, periodo.split("-"))
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def _is_open_period(periodo: str, today: date) -> bool:
    year, month = map(int, periodo.split("-"))
    return (year, month) >= (today.year, today.month)


async def get_iva_period_snapshot(
    db, *, anno: int, mese: int, today: date | None = None,
) -> Dict[str, Any]:
    if mese not in range(1, 13):
        raise ValueError("mese IVA non valido")
    today = today or date.today()
    periodo = f"{anno}-{mese:02d}"
    deadline = monthly_deadline(anno, mese)
    if _is_open_period(periodo, today):
        return {
            "periodo": periodo,
            "stato_calcolo": "NON_CALCOLATO",
            "motivo_non_calcolato": "periodo_non_concluso",
            "iva_vendite": None,
            "iva_vendite_cents": None,
            "iva_acquisti": None,
            "iva_acquisti_cents": None,
            "saldo": None,
            "saldo_cents": None,
            "debito_periodo": None,
            "debito_periodo_cents": None,
            "credito_periodo": None,
            "credito_periodo_cents": None,
            "fonte": "periodo_non_concluso",
            "fonte_calcolo": SERVICE_VERSION,
            "conteggi": {
                "fatture_periodo_attribuito": 0,
                "fatture_incluse_calcolo": 0,
                "fatture_escluse_calcolo": 0,
                "detraibilita_da_verificare": 0,
            },
            **deadline,
        }

    confirmed = await db["liquidazioni_iva"].find_one(
        {"periodo": periodo, "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}},
        {"_id": 0}, sort=[("versione", -1)],
    )
    invoices = await db["invoices"].find(
        {"periodo_iva_attribuito": periodo}, {"_id": 0}
    ).to_list(20000)
    # Due grandezze diverse, che non devono mai essere confuse:
    # - competenza: tutte le fatture fiscalmente attribuite al mese, anche se
    #   gia' usate in quella liquidazione;
    # - disponibilita': sole fatture ancora inseribili in una NUOVA
    #   liquidazione, quindi al netto di iva_utilizzata.
    competence_included, competence_excluded = liq.seleziona_fatture_per_competenza(
        invoices, periodo,
    )
    available_included, available_excluded = liq.seleziona_fatture_per_liquidazione(
        invoices, periodo,
    )
    sales = await corrispettivi_periodo(db, periodo)
    previous = await db["liquidazioni_iva"].find_one(
        {"periodo": _previous_period(periodo),
         "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}},
        {"_id": 0}, sort=[("versione", -1)],
    )
    previous_credit_cents = money_cents((previous or {}).get("credito_periodo"))
    competence_purchases_cents = sum(
        money_cents(item.get("iva_detraibile")) for item in competence_included
    )
    available_purchases_cents = sum(
        money_cents(item.get("iva_detraibile")) for item in available_included
    )
    purchases_cents = available_purchases_cents
    sales_cents = sales["iva_vendite_cents"]
    balance_cents = sales_cents - purchases_cents - previous_credit_cents
    source = "calcolo_canonico"
    status = liq.CALCOLATA
    if confirmed:
        source = "liquidazione_confermata"
        status = str(confirmed.get("stato") or liq.CONFERMATA)
        sales_cents = money_cents(confirmed.get("iva_vendite"))
        purchases_cents = money_cents(confirmed.get("iva_acquisti"))
        previous_credit_cents = money_cents(confirmed.get("credito_precedente"))
        balance_cents = money_cents(confirmed.get("saldo"))
    elif sales.get("corrispettivi_iva_non_verificabile"):
        status = "NON_VERIFICABILE"
        source = "corrispettivi_iva_mancante"

    counts = {
        "fatture_periodo_attribuito": len(invoices),
        "fatture_incluse_competenza": len(competence_included),
        "fatture_escluse_competenza": len(competence_excluded),
        "fatture_incluse_calcolo": len(available_included),
        "fatture_escluse_calcolo": len(available_excluded),
        "fatture_gia_utilizzate": sum(
            1 for item in invoices if item.get("iva_utilizzata") is True
        ),
        "detraibilita_da_verificare": sum(
            1 for item in invoices
            if item.get("stato_detrazione_iva") in (None, "", "NON_VALUTATA", "DA_VERIFICARE")
        ),
        "detraibilita_verificata": sum(
            1 for item in invoices
            if item.get("stato_detrazione_iva") not in (None, "", "NON_VALUTATA", "DA_VERIFICARE")
        ),
    }
    return {
        "periodo": periodo,
        "stato_calcolo": status,
        "iva_vendite_cents": sales_cents,
        "iva_acquisti_cents": purchases_cents,
        "iva_acquisti_competenza_cents": competence_purchases_cents,
        "iva_acquisti_disponibile_cents": available_purchases_cents,
        "credito_precedente_cents": previous_credit_cents,
        "saldo_cents": balance_cents,
        "debito_periodo_cents": max(balance_cents, 0),
        "credito_periodo_cents": max(-balance_cents, 0),
        "iva_vendite": euros(sales_cents),
        "iva_acquisti": euros(purchases_cents),
        "iva_acquisti_competenza": euros(competence_purchases_cents),
        "iva_acquisti_disponibile": euros(available_purchases_cents),
        "credito_precedente": euros(previous_credit_cents),
        "saldo": euros(balance_cents),
        "debito_periodo": euros(max(balance_cents, 0)),
        "credito_periodo": euros(max(-balance_cents, 0)),
        "fonte": source,
        "fonte_calcolo": SERVICE_VERSION,
        "conteggi": counts,
        "fatture_escluse": available_excluded,
        "fatture_escluse_competenza": competence_excluded,
        **sales,
        **deadline,
    }
