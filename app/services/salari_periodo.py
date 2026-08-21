"""Confine temporale unico della contabilita' salari.

I documenti cedolino restano nello storico documentale. Soltanto le scritture
di ``prima_nota_salari`` sono ammesse nel periodo operativo richiesto:
dicembre 2025 e, dal 2026, fino al mese corrente.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple


PERIODO_MINIMO_SALARI: Tuple[int, int] = (2025, 12)


def normalizza_periodo(anno: Any, mese: Any) -> Optional[Tuple[int, int]]:
    try:
        periodo = int(anno), int(mese)
    except (TypeError, ValueError):
        return None
    if periodo[0] < 2000 or not 1 <= periodo[1] <= 12:
        return None
    return periodo


def periodo_ammesso_in_prima_nota(
    anno: Any,
    mese: Any,
    *,
    oggi: Optional[date] = None,
) -> bool:
    periodo = normalizza_periodo(anno, mese)
    if periodo is None:
        return False
    corrente = oggi or date.today()
    return PERIODO_MINIMO_SALARI <= periodo <= (corrente.year, corrente.month)


def filtro_periodo_prima_nota(*, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Filtro repository per tutte e sole le mensilita' contabili ammesse."""
    corrente = oggi or date.today()
    anno_minimo, mese_minimo = PERIODO_MINIMO_SALARI
    if corrente.year == anno_minimo:
        return {
            "anno": anno_minimo,
            "mese": {"$gte": mese_minimo, "$lte": corrente.month},
        }
    return {
        "$or": [
            {"anno": anno_minimo, "mese": {"$gte": mese_minimo}},
            {
                "anno": {"$gt": anno_minimo, "$lt": corrente.year},
            },
            {"anno": corrente.year, "mese": {"$lte": corrente.month}},
        ],
    }


def filtro_fuori_periodo_prima_nota(*, oggi: Optional[date] = None) -> Dict[str, Any]:
    return {"$nor": [filtro_periodo_prima_nota(oggi=oggi)]}
