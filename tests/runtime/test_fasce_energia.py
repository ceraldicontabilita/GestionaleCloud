from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.fasce_energia import fascia_per_istante, riepilogo_fasce


ROMA = ZoneInfo("Europe/Rome")


def dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=ROMA)


def test_giorno_feriale_rispetta_le_tre_fasce():
    assert fascia_per_istante(dt("2026-08-06T06:59:00")) == "F3"
    assert fascia_per_istante(dt("2026-08-06T07:30:00")) == "F2"
    assert fascia_per_istante(dt("2026-08-06T12:00:00")) == "F1"
    assert fascia_per_istante(dt("2026-08-06T20:00:00")) == "F2"
    assert fascia_per_istante(dt("2026-08-06T23:00:00")) == "F3"


def test_sabato_domenica_e_festivi_non_vengono_trattati_come_feriali():
    assert fascia_per_istante(dt("2026-08-08T12:00:00")) == "F2"  # sabato
    assert fascia_per_istante(dt("2026-08-09T12:00:00")) == "F3"  # domenica
    assert fascia_per_istante(dt("2026-08-15T12:00:00")) == "F3"  # Ferragosto
    assert fascia_per_istante(dt("2026-04-06T12:00:00")) == "F3"  # Lunedi dell'Angelo


def test_riepilogo_indica_f2_come_fascia_piu_costosa_e_prossima_f3():
    res = riepilogo_fasce(dt("2026-08-08T12:00:00"))
    assert res["fascia_attuale"] == "F2"
    assert res["azione"] == "RIDUCI SE POSSIBILE"
    assert res["tariffe"]["F2"]["euro_kwh"] > res["tariffe"]["F1"]["euro_kwh"]
    assert res["tariffe"]["F1"]["euro_kwh"] > res["tariffe"]["F3"]["euro_kwh"]
    assert res["prossima_f3"].startswith("2026-08-08T23:00:00")
