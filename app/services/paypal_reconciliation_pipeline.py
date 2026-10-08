"""Un solo passaggio PayPal -> fattura -> banca per tutti gli ingressi vivi."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else int(value or 0)


async def riconcilia_paypal_importato(
    db, *, start_date: Optional[str] = None, end_date: Optional[str] = None,
) -> Dict[str, Any]:
    from app.services.paypal_reconciliation_links import riprocessa_collegamenti_paypal
    from app.routers.paypal_statements import _auto_riconcilia

    prima = await riprocessa_collegamenti_paypal(
        db, start_date=start_date, end_date=end_date,
    )
    if start_date and end_date:
        anni = range(date.fromisoformat(start_date).year, date.fromisoformat(end_date).year + 1)
        per_anno = {
            str(anno): await _auto_riconcilia(db, anno=anno, applica=True)
            for anno in anni
        }
        if len(per_anno) == 1:
            banca = next(iter(per_anno.values()))
        else:
            banca = {
                "per_anno": per_anno,
                **{
                    key: sum(_count(esito.get(key)) for esito in per_anno.values())
                    for key in ("riconciliati", "proposte", "ambigui")
                },
            }
    else:
        banca = await _auto_riconcilia(db, applica=True)
    dopo = await riprocessa_collegamenti_paypal(
        db, start_date=start_date, end_date=end_date,
    )
    # Le ricevute pagoPA/Mooney arrivate prima del pagamento PayPal lo trovano qui.
    from app.services.pagopa_receipts import ricollega_ricevute_paypal
    try:
        ricevute = await ricollega_ricevute_paypal(db)
    except Exception as exc:  # la rete delle ricevute non ferma il giro PayPal
        logger.warning(
            "Ricevute pagoPA non ricollegate ai pagamenti PayPal (%s): %s",
            type(exc).__name__, exc,
        )
        ricevute = {"in_attesa": 0, "collegate": 0, "errore": type(exc).__name__}
    return {
        "collegamenti_prima": prima,
        "banca": banca,
        "collegamenti_dopo": dopo,
        "ricevute_pagopa": ricevute,
    }
