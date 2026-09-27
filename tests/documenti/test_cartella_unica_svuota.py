"""«Importa tutto adesso»: giri uno dopo l'altro finche' la cartella e' vuota."""
import asyncio

from app.services import drive_cartella_unica as cu


def test_svuota_continua_finche_restano_file(monkeypatch):
    esiti = iter([
        {"letti": 50, "elaborati": 50, "errori": 0, "restanti": 136},
        {"letti": 50, "elaborati": 49, "errori": 1, "restanti": 86},
        {"letti": 50, "elaborati": 50, "errori": 0, "restanti": 36},
        {"letti": 36, "elaborati": 36, "errori": 0, "restanti": 0},
    ])

    async def _giro(db):
        return next(esiti)

    monkeypatch.setattr(cu, "giro", _giro)
    totale = asyncio.run(cu.svuota(object()))
    assert totale["giri"] == 4
    assert totale["letti"] == 186 and totale["elaborati"] == 185 and totale["errori"] == 1
    assert totale["restanti"] == 0
    assert not cu.svuotamento_in_corso()


def test_svuota_si_ferma_se_un_giro_non_legge_niente(monkeypatch):
    chiamate = []

    async def _giro(db):
        chiamate.append(1)
        return {"letti": 0, "restanti": 5}

    monkeypatch.setattr(cu, "giro", _giro)
    assert asyncio.run(cu.svuota(object()))["giri"] == 1
    assert len(chiamate) == 1


def test_svuota_si_ferma_su_errore_di_drive(monkeypatch):
    async def _giro(db):
        return {"errore": "RuntimeError: credenziali Drive non disponibili"}

    monkeypatch.setattr(cu, "giro", _giro)
    totale = asyncio.run(cu.svuota(object()))
    assert totale["giri"] == 0
    assert "credenziali" in totale["fermato_da"]
