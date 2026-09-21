"""La proposta «Usa oggi» contiene solo lotti con scadenza verificata e futura."""

import asyncio
from datetime import date, timedelta

from app.lotti.routers import lotti


class Cursore:
    def __init__(self, righe):
        self.righe = righe

    async def to_list(self, _limite):
        return self.righe


class Collezione:
    def __init__(self, righe):
        self.righe = righe

    def find(self, _filtro, _proiezione):
        return Cursore(self.righe)


class Database:
    def __init__(self, righe):
        self.lotti = Collezione(righe)


def test_cosa_usare_separa_scaduti_e_date_sconosciute(monkeypatch):
    oggi = date.today()
    dati = [
        {"id": "scaduto", "prodotto": "Babà", "quantita": 1, "data_scadenza": (oggi - timedelta(days=1)).isoformat()},
        {"id": "oggi", "prodotto": "Arancino", "quantita": 2, "data_scadenza": oggi.isoformat()},
        {"id": "futuro", "prodotto": "Biscotto", "quantita": 3, "data_scadenza": (oggi + timedelta(days=3)).isoformat()},
        {"id": "sconosciuto", "prodotto": "Crema", "quantita": 4, "data_scadenza": ""},
    ]
    monkeypatch.setattr(lotti, "db", Database(dati))

    risultato = asyncio.run(lotti.cosa_usare_oggi(limit=20))

    assert [r["id"] for r in risultato["lotti"]] == ["oggi", "futuro"]
    assert [r["id"] for r in risultato["scaduti"]] == ["scaduto"]
    assert [r["id"] for r in risultato["da_verificare"]] == ["sconosciuto"]
    assert risultato["totale"] == 2
