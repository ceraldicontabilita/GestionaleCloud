"""P1 §6.2 — L'endpoint bilancio espone la VISTA in piano dei conti UFFICIALE CEE
(campo `bilancio_ufficiale`) derivata dai saldi operativi, senza alterare l'output
storico. I codici mostrati sono quelli ufficiali del bilancio (es. 55.01.07, 47.01.03)."""
import asyncio

import app.routers.accounting.piano_conti as pc


class _Cur:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return list(self._docs)


class _Coll:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *a, **k):
        return _Cur(self._docs)


class _Db:
    def __init__(self, conti):
        self._conti = conti

    def __getitem__(self, name):
        return _Coll(self._conti)


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_bilancio_espone_vista_ufficiale(monkeypatch):
    # piano dei conti (operativo) con categorie
    conti = [
        {"codice": "05.01.01", "nome": "Acquisto merci", "categoria": "costi"},
        {"codice": "04.01.01", "nome": "Ricavi vendite", "categoria": "ricavi"},
        {"codice": "01.01.02", "nome": "Banca c/c", "categoria": "attivo"},
    ]
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: _Db(conti)))

    async def _fake_saldi(db, anno=None):
        return {"05.01.01": 100.0, "04.01.01": 500.0, "01.01.02": 3000.0}
    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _fake_saldi)

    res = _run(pc.get_bilancio(anno="2025"))

    # output storico invariato
    assert "stato_patrimoniale" in res and "conto_economico" in res
    # nuova vista ufficiale
    uff = res["bilancio_ufficiale"]
    codici_ce = {v["descrizione"]: v for v in uff["conto_economico"]}
    # 05.01.01 → 55.01.07 Acquisti merci ; 04.01.01 → 47.01.03 Vendita merci
    assert any("Acquisti merci" == d for d in codici_ce)
    assert any("Vendita merci" == d for d in codici_ce)
    codici_sp = [v for v in uff["stato_patrimoniale"]]
    assert any(v["descrizione"] == "Banca c/c" and v["saldo"] == 3000.0 for v in codici_sp)
