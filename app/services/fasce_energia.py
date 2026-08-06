"""Fasce energia del contratto Enel aziendale.

La regola e' centralizzata qui per evitare che Dashboard, report e futuri
controlli pianificati calcolino fasce diverse. Gli orari sono espressi nel
fuso Europe/Rome e rispettano domeniche e festivita' nazionali italiane.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, Tuple
from zoneinfo import ZoneInfo


ROME = ZoneInfo("Europe/Rome")

TARIFFE = {
    "F1": {"euro_kwh": 0.1595, "euro_kwh_con_perdite": 0.1755},
    "F2": {"euro_kwh": 0.1752, "euro_kwh_con_perdite": 0.1927},
    "F3": {"euro_kwh": 0.1336, "euro_kwh_con_perdite": 0.1470},
}


def _pasqua(anno: int) -> date:
    """Pasqua gregoriana (algoritmo di Meeus/Jones/Butcher)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = (h + l - 7 * m + 114) % 31 + 1
    return date(anno, mese, giorno)


def festivita_nazionali(anno: int) -> set[date]:
    fisse: Iterable[Tuple[int, int]] = (
        (1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15),
        (11, 1), (12, 8), (12, 25), (12, 26),
    )
    return {date(anno, mese, giorno) for mese, giorno in fisse} | {
        _pasqua(anno) + timedelta(days=1),
    }


def fascia_per_istante(istante: datetime) -> str:
    locale = istante.astimezone(ROME) if istante.tzinfo else istante.replace(tzinfo=ROME)
    giorno = locale.date()
    ora = locale.time()

    if locale.weekday() == 6 or giorno in festivita_nazionali(locale.year):
        return "F3"
    if locale.weekday() == 5:  # sabato
        return "F2" if time(7) <= ora < time(23) else "F3"
    if time(8) <= ora < time(19):
        return "F1"
    if time(7) <= ora < time(8) or time(19) <= ora < time(23):
        return "F2"
    return "F3"


def _inizio_prossima_f3(istante: datetime) -> datetime:
    locale = istante.astimezone(ROME) if istante.tzinfo else istante.replace(tzinfo=ROME)
    candidato = locale.replace(minute=0, second=0, microsecond=0)
    if candidato <= locale:
        candidato += timedelta(hours=1)
    # Ricerca limitata a otto giorni; una finestra F3 esiste ogni notte.
    for _ in range(24 * 8):
        if fascia_per_istante(candidato) == "F3":
            precedente = candidato - timedelta(minutes=1)
            if fascia_per_istante(precedente) != "F3":
                return candidato
        candidato += timedelta(hours=1)
    return candidato


def riepilogo_fasce(istante: datetime | None = None) -> Dict[str, Any]:
    ora = istante or datetime.now(ROME)
    ora = ora.astimezone(ROME) if ora.tzinfo else ora.replace(tzinfo=ROME)
    fascia = fascia_per_istante(ora)
    prossima_f3 = ora if fascia == "F3" else _inizio_prossima_f3(ora)
    giudizio = {
        "F3": ("PRODUCI ORA", "Fascia piu economica del contratto."),
        "F1": ("CONVENIENTE", "Costo intermedio: meglio di F2."),
        "F2": ("RIDUCI SE POSSIBILE", "Fascia piu costosa del contratto."),
    }
    azione, motivo = giudizio[fascia]
    return {
        "timezone": "Europe/Rome",
        "aggiornato_il": ora.isoformat(),
        "fascia_attuale": fascia,
        "azione": azione,
        "motivo": motivo,
        "tariffa": TARIFFE[fascia],
        "prossima_f3": prossima_f3.isoformat(),
        "regole": [
            {"giorni": "Lunedi-venerdi", "F1": "08:00-19:00", "F2": "07:00-08:00 e 19:00-23:00", "F3": "23:00-07:00"},
            {"giorni": "Sabato", "F1": "-", "F2": "07:00-23:00", "F3": "23:00-07:00"},
            {"giorni": "Domenica e festivita nazionali", "F1": "-", "F2": "-", "F3": "00:00-24:00"},
        ],
        "tariffe": TARIFFE,
        "validita_condizioni": {"dal": "2025-12-01", "al": "2026-11-30"},
        "nota": "Prezzi componente energia, IVA e imposte escluse; il valore con perdite include le perdite di rete indicate nel contratto.",
    }
