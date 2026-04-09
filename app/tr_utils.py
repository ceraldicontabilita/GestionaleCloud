"""
tr_utils.py — Utility condivise per i router Tracciabilità.
Date utils + helper vari, estratti dal repo tracciabilita.
"""
from datetime import datetime, timezone, date, timedelta


def oggi_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_to_it(d: str) -> str:
    if not d:
        return ""
    try:
        if "T" in d:
            d = d[:10]
        y, m, day = d.split("-")
        return f"{day}/{m}/{y}"
    except Exception:
        return d


def calcola_pasqua(anno: int) -> date:
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def get_chiusure_obbligatorie(anno: int) -> list:
    """Chiusure fisse + Pasqua + ferie agosto"""
    pasqua = calcola_pasqua(anno)
    pasquetta = pasqua + timedelta(days=1)
    chiusure = [
        {"data": date(anno, 1, 1), "nome": "Capodanno"},
        {"data": pasqua, "nome": "Pasqua"},
        {"data": pasquetta, "nome": "Pasquetta"},
        {"data": date(anno, 4, 25), "nome": "Liberazione"},
        {"data": date(anno, 5, 1), "nome": "Festa Lavoratori"},
        {"data": date(anno, 8, 15), "nome": "Ferragosto"},
        {"data": date(anno, 12, 25), "nome": "Natale"},
        {"data": date(anno, 12, 26), "nome": "S. Stefano"},
    ]
    for g in range(12, 25):
        chiusure.append({"data": date(anno, 8, g), "nome": "Ferie estive"})
    return chiusure


def genera_stati_speciali_random(anno: int) -> dict:
    """Genera manutenzioni e non_usato random per un anno"""
    import random
    result = {"manutenzione": [], "non_usato": []}
    for tipo, (min_blocchi, max_blocchi, min_gg, max_gg) in [
        ("manutenzione", (2, 3, 2, 3)),
        ("non_usato", (1, 2, 3, 5)),
    ]:
        for _ in range(random.randint(min_blocchi, max_blocchi)):
            mese = random.randint(1, 12)
            giorno_start = random.randint(1, 25)
            durata = random.randint(min_gg, max_gg)
            for d in range(durata):
                try:
                    dt = date(anno, mese, giorno_start + d)
                    result[tipo].append({"data": dt, "nome": tipo.replace("_", " ").title()})
                except ValueError:
                    pass
    return result
