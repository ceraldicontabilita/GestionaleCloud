"""Calendario canonico delle scadenze fiscali mensili italiane.

Il documento conserva sempre la data nominale (normalmente il giorno 16) e
la data legale effettiva.  Le pagine IVA, Ritenute e Scadenze devono usare
questo modulo invece di ricostruire autonomamente il calendario.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict


CALENDAR_RULE_VERSION = "fiscal_deadlines_it_v1"


def _easter_sunday(year: int) -> date:
    """Algoritmo gregoriano di Meeus/Jones/Butcher."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def italian_public_holidays(year: int) -> set[date]:
    fixed = {
        (1, 1), (1, 6), (4, 25), (5, 1), (6, 2),
        (8, 15), (11, 1), (12, 8), (12, 25), (12, 26),
    }
    holidays = {date(year, month, day) for month, day in fixed}
    holidays.add(_easter_sunday(year) + timedelta(days=1))
    return holidays


def next_business_day(value: date) -> date:
    result = value
    while result.weekday() >= 5 or result in italian_public_holidays(result.year):
        result += timedelta(days=1)
    return result


def monthly_deadline(anno: int, mese_competenza: int) -> Dict[str, Any]:
    """Data nominale e legale del versamento del mese di competenza.

    Il termine nominale e' il 16 del mese successivo. Per i versamenti di
    agosto viene applicato il differimento al 20 gia' adottato dal gestionale;
    weekend e festivita' nazionali spostano poi il termine al primo giorno
    lavorativo successivo.
    """
    if mese_competenza not in range(1, 13):
        raise ValueError("mese di competenza non valido")
    if mese_competenza == 12:
        nominal = date(anno + 1, 1, 16)
    else:
        nominal = date(anno, mese_competenza + 1, 16)
    base_legale = nominal.replace(day=20) if nominal.month == 8 else nominal
    legal = next_business_day(base_legale)
    reasons = []
    if base_legale != nominal:
        reasons.append("differimento_agosto_al_20")
    if legal != base_legale:
        reasons.append("primo_giorno_lavorativo_successivo")
    return {
        "scadenza_nominale": nominal.isoformat(),
        "scadenza_legale": legal.isoformat(),
        "regola_scadenza": CALENDAR_RULE_VERSION,
        "motivi_differimento": reasons,
    }
