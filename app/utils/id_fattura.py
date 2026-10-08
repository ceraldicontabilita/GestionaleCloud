"""Su `invoices` l'`id` e' un numero su meta' delle righe e un testo sulle altre."""
from __future__ import annotations

from typing import Any, List


def varianti_id(valore: Any) -> List[Any]:
    """Le forme in cui puo' essere salvato lo stesso id: testo e, se e' fatto
    di sole cifre, numero. Un filtro per id di fattura le cerca tutte."""
    testo = str(valore)
    return [testo, int(testo)] if testo.isdigit() else [testo]


def filtro_id(valore: Any) -> dict:
    """`{"id": {"$in": [testo, numero]}}` per una fattura sola."""
    return {"id": {"$in": varianti_id(valore)}}


def filtro_id_in(valori) -> dict:
    """Come `filtro_id` per piu' fatture, senza duplicare le varianti."""
    visti: List[Any] = []
    for v in valori:
        for x in varianti_id(v):
            if x not in visti:
                visti.append(x)
    return {"id": {"$in": visti}}
