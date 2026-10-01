"""Calendario canonico delle scadenze fiscali mensili italiane.

Il documento conserva sempre la data nominale (normalmente il giorno 16) e
la data legale effettiva.  Le pagine IVA, Ritenute e Scadenze devono usare
questo modulo invece di ricostruire autonomamente il calendario.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

from app.services.calendario_lavorativo import e_festivo


CALENDAR_RULE_VERSION = "fiscal_deadlines_it_v1"


def next_business_day(value: date) -> date:
    """Primo giorno lavorativo da ``value`` in poi (calendario unico: ``calendario_lavorativo``)."""
    result = value
    while e_festivo(result):
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
