"""L'aggiornamento ricette da fattura non deve tenere fermo il loop.

prodotti x ricette x ingredienti gira tutto in CPU: senza pause /api/health
non rispondeva entro 5 s, Render dichiarava il servizio morto e lo
riavviava (502 per il titolare).
"""
import asyncio

from app.lotti.routers import aggiornamento_ricette as mod


class _Cursore:
    def __init__(self, righe):
        self._righe = righe

    async def to_list(self, _n):
        return list(self._righe)


class _Collezione:
    def __init__(self, righe=()):
        self.righe = list(righe)
        self.scritture = []

    def find(self, *_a, **_k):
        return _Cursore(self.righe)

    async def update_one(self, filtro, *_a, **_k):
        self.scritture.append(filtro)


class _Db:
    def __init__(self, ricette):
        self.ricette = _Collezione(ricette)
        self.mappature_ingredienti = _Collezione()


def test_il_loop_resta_libero_e_i_match_non_cambiano(monkeypatch):
    ricette = [
        {"id": f"r{i}", "nome": f"Ricetta {i}",
         "ingredienti_dettaglio": [{"nome": "farina 00"}, {"nome": f"aroma {i}"}]}
        for i in range(200)
    ]
    finto = _Db(ricette)
    monkeypatch.setattr(mod, "db", finto)
    fattura = {"numero": "1/1", "fornitore": "Molino Prova",
               "prodotti": [{"descrizione": "FARINA 00 KG 25"}, {"descrizione": "ZUCCHERO"}]}

    battiti = 0

    async def cuore():
        nonlocal battiti
        while True:
            battiti += 1
            await asyncio.sleep(0)

    async def giro():
        compito = asyncio.create_task(cuore())
        esito = await mod.aggiorna_ricette_da_fattura(fattura)
        compito.cancel()
        return esito

    esito = asyncio.run(giro())
    assert esito["aggiornate"] == 200
    farina = [f for f in finto.mappature_ingredienti.scritture if f["nome_ricetta"] == "farina 00"]
    assert len(farina) == 200
    # Il battito gira fra una ricetta e l'altra, non solo fra una scrittura e l'altra.
    assert battiti >= 2 * len(ricette)
