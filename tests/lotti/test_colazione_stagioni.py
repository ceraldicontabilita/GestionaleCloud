"""
test_colazione_stagioni.py
────────────────────────────
Regression test per lo switch automatico di stagione per data (richiesta
Enzo 03/07/2026): niente più scelta manuale della stagione ogni mattina —
i 4 periodi di default (equinozi/solstizi) devono coprire OGNI giorno
dell'anno esattamente una volta, incluso il periodo Invernale che
attraversa il capodanno (dicembre -> marzo dell'anno dopo).
"""
from datetime import date, timedelta

from app.lotti.routers.colazione import _data_in_periodo, _DATE_STAGIONI_DEFAULT


def test_esempi_concreti():
    assert _data_in_periodo("04-15", *_DATE_STAGIONI_DEFAULT["Primavera"])
    assert _data_in_periodo("07-01", *_DATE_STAGIONI_DEFAULT["Estiva"])
    assert _data_in_periodo("10-10", *_DATE_STAGIONI_DEFAULT["Autunnale"])
    assert _data_in_periodo("01-15", *_DATE_STAGIONI_DEFAULT["Invernale"])  # capodanno
    assert _data_in_periodo("12-25", *_DATE_STAGIONI_DEFAULT["Invernale"])
    assert not _data_in_periodo("06-15", *_DATE_STAGIONI_DEFAULT["Invernale"])


def test_confini_periodo_incluso():
    inizio, fine = _DATE_STAGIONI_DEFAULT["Primavera"]
    assert _data_in_periodo(inizio, inizio, fine)
    assert _data_in_periodo(fine, inizio, fine)


def test_giorno_dopo_confine_esce_dal_periodo():
    # 21 marzo è il primo giorno di Primavera: non deve più risultare Invernale
    assert not _data_in_periodo("03-21", *_DATE_STAGIONI_DEFAULT["Invernale"])
    assert _data_in_periodo("03-21", *_DATE_STAGIONI_DEFAULT["Primavera"])


def test_periodo_vuoto_o_mancante():
    assert not _data_in_periodo("04-15", None, "06-20")
    assert not _data_in_periodo("04-15", "03-21", None)
    assert not _data_in_periodo("04-15", "", "")


def test_ogni_giorno_dell_anno_cade_in_una_sola_stagione():
    """Nessun buco, nessuna sovrapposizione tra i 4 periodi di default."""
    giorno = date(2024, 1, 1)  # 2024 bisestile: copre anche il 29 febbraio
    for _ in range(366):
        mmdd = giorno.strftime("%m-%d")
        trovate = [
            nome for nome, (inizio, fine) in _DATE_STAGIONI_DEFAULT.items()
            if _data_in_periodo(mmdd, inizio, fine)
        ]
        assert len(trovate) == 1, f"{mmdd} risulta in {trovate}, atteso esattamente 1"
        giorno += timedelta(days=1)
