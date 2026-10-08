"""Calendario dei giorni lavorativi italiani: un posto solo.

Pasqua, festivita' nazionali e giorni lavorativi servivano in tre servizi
(scadenzario tributi, piano tributi, fasce energia), ognuno con la sua copia.
Qui sta l'unica. Il santo patrono non e' compreso: vale il calendario
nazionale, quello delle scadenze fiscali.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Set

_FESTIVITA_FISSE = (
    (1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26),
)


def pasqua(anno: int) -> date:
    """Pasqua gregoriana (algoritmo di Meeus/Jones/Butcher)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lettera = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lettera) // 451
    mese = (h + lettera - 7 * m + 114) // 31
    giorno = (h + lettera - 7 * m + 114) % 31 + 1
    return date(anno, mese, giorno)


def festivita_nazionali(anno: int) -> Set[date]:
    """Le festivita' fisse piu' il lunedi' di Pasqua."""
    return {date(anno, m, g) for m, g in _FESTIVITA_FISSE} | {pasqua(anno) + timedelta(days=1)}


def e_festivo(giorno: date) -> bool:
    """Sabato, domenica o festivita' nazionale."""
    return giorno.weekday() >= 5 or giorno in festivita_nazionali(giorno.year)


def giorni_lavorativi_tra(da: date, a: date) -> int:
    """Giorni lavorativi dopo ``da`` fino ad ``a`` compreso; negativo se ``a`` precede ``da``.

    Venerdi' → lunedi' = 1, stesso giorno = 0. Un pagamento datato sabato o
    festivo conta dal primo giorno lavorativo successivo.
    """
    if a < da:
        return -giorni_lavorativi_tra(a, da)
    n, g = 0, da
    while g < a:
        g += timedelta(days=1)
        if not e_festivo(g):
            n += 1
    return n
