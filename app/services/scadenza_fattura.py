"""La scadenza sintetica di una fattura, calcolata in un posto solo.

La regola giusta e' quella che l'upload manuale applicava:

1. la **prima scadenza dichiarata nell'XML** (`pagamento_rate[].data_scadenza`),
   che e' il termine vero pattuito col fornitore;
2. solo se l'XML non ne dichiara nessuna, il ripiego **data fattura + 30
   giorni**.

Il canale automatico (`import_parsed_invoice`, quello del Drive, da cui
passa la stragrande maggioranza delle fatture) faceva solo il punto 2, con
un commento che diceva «come l'upload manuale» — e non lo era. Misurato in
produzione il 19/09/2026 sulle 624 fatture attive del canale Drive: 427
dichiarano una scadenza nell'XML e in **414** casi e' stata sostituita dal
+30. Effetto:

- 390 fatture, 204.069,70 EUR: scadenza mostrata **piu' tardi** di quella
  vera, in media di 29 giorni e fino a 40. Sono le pericolose: gia' scadute
  e non segnalate, e il cash flow prevede l'uscita un mese dopo il dovuto.
  Il caso tipico e' un fornitore a pagamento immediato — San Carlo, fattura
  del 29/05/2026, scadenza XML 29/05, salvata 28/06.
- 24 fatture, 11.742,90 EUR: scadenza mostrata **prima** di quella vera,
  fino a 58 giorni. Risultano scadute quando non lo sono.

Il +30 non e' mai una data di pagamento e non sostituisce il piano rate, che
resta conservato sulla fattura.
"""
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

__all__ = ["scadenza_sintetica", "GIORNI_RIPIEGO"]

#: Giorni aggiunti alla data fattura quando l'XML non dichiara scadenze.
GIORNI_RIPIEGO = 30

_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _scadenze_dichiarate(fattura: Dict[str, Any]) -> list:
    rate = fattura.get("pagamento_rate") or []
    if not isinstance(rate, list):
        return []
    return sorted(
        str(rata.get("data_scadenza"))[:10]
        for rata in rate
        if isinstance(rata, dict) and rata.get("data_scadenza")
        and _DATA_ISO.fullmatch(str(rata.get("data_scadenza"))[:10])
    )


def scadenza_sintetica(fattura: Dict[str, Any]) -> Optional[str]:
    """La scadenza della fattura in `YYYY-MM-DD`, o `None` se indeterminabile.

    Funziona sia sul dizionario appena letto dall'XML (`parsed`) sia sulla
    fattura salvata: entrambi portano `invoice_date` e `pagamento_rate`.
    Senza data fattura e senza scadenze XML non si inventa nulla: `None`.
    """
    dichiarate = _scadenze_dichiarate(fattura)
    if dichiarate:
        return dichiarate[0]

    data_fattura = str(fattura.get("invoice_date") or "")[:10]
    if not data_fattura:
        return None
    try:
        return (
            datetime.strptime(data_fattura, "%Y-%m-%d") + timedelta(days=GIORNI_RIPIEGO)
        ).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None
