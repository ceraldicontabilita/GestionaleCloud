"""Il Registro HACCP e Anomalie devono contare gli stessi stati reali."""

import asyncio

from app.lotti.routers import anomalie, diagnostic


class Cursore:
    def __init__(self, righe):
        self.righe = righe

    async def to_list(self, _limite):
        return self.righe

    def __aiter__(self):
        async def righe():
            for riga in self.righe:
                yield riga
        return righe()


class Collezione:
    def __init__(self, righe=()):
        self.righe = list(righe)

    async def count_documents(self, filtro):
        if "stato" in filtro:
            return sum(r.get("stato") in filtro["stato"]["$in"] for r in self.righe)
        return 0

    def find(self, _filtro, _proiezione=None):
        return Cursore(self.righe)

    async def find_one(self, _filtro, _proiezione=None):
        return None


class Database:
    def __init__(self, righe):
        self.collezioni = {"anomalie": Collezione(righe)}

    def __getitem__(self, nome):
        return self.collezioni.setdefault(nome, Collezione())

    def __getattr__(self, nome):
        return self[nome]


def test_registro_e_statistiche_escludono_risolte_e_chiuse(monkeypatch):
    dati = Database([
        {"stato": "Aperta"},
        {"stato": "In corso"},
        {"stato": "Risolta"},
        {"stato": "Chiusa"},
    ])
    monkeypatch.setattr(diagnostic, "db", dati)
    monkeypatch.setattr(anomalie, "db", dati)

    registro = asyncio.run(diagnostic.registro_haccp_riepilogo())
    statistiche = asyncio.run(anomalie.get_statistiche())

    assert registro["anomalie_aperte"] == statistiche["aperte"] == 2
    assert statistiche["risolte"] == 2
