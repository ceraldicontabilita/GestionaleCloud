"""
DEPRECATO: helper filtri anno per record storici

Questo modulo produce filtri compatibili con le query legacy DB storiche. Con
la rimozione di legacy DB questo helper è deprecato; resta disponibile per
compatibilità con codice legacy ma non va usato in nuovi flussi.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


def filtro_anno_registro(
    anno: Optional[int],
    campi_data: Iterable[str],
    *,
    campo_anno: Optional[str] = "anno",
) -> Dict[str, Any]:
    """Restituisce un filtro che riconosce l'anno in tutti i formati noti."""
    if anno is None:
        return {}

    anno = int(anno)
    clausole = []
    if campo_anno:
        clausole.append({campo_anno: {"$in": [anno, str(anno)]}})

    inizio = datetime(anno, 1, 1, tzinfo=timezone.utc)
    fine = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
    for campo in campi_data:
        clausole.extend([
            {campo: {"$regex": rf"^{anno}(?:-|/)"}},
            {campo: {"$regex": rf"/{anno}(?:\s.*)?$"}},
            {campo: {"$gte": inizio, "$lt": fine}},
        ])

    return {"$or": clausole}


def combina_filtri(*filtri: Dict[str, Any]) -> Dict[str, Any]:
    """Combina filtri senza sovrascrivere clausole omonime."""
    validi = [filtro for filtro in filtri if filtro]
    if not validi:
        return {}
    if len(validi) == 1:
        return validi[0]
    return {"$and": validi}
