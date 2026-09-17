import asyncio

from app.routers.accounting import prima_nota_salari as modulo


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return list(self.docs)


class _Salari:
    async def distinct(self, field, _query):
        assert field == "dipendente"
        return ["CERALDI VALERIO", "Dipendente Storico"]


class _Dipendenti:
    def __init__(self):
        self.query = None

    def find(self, query, _projection):
        self.query = query
        return _Cursor([
            {
                "id": "D1",
                "nome": "Valerio",
                "cognome": "Ceraldi",
                "attivo": True,
            },
            {
                "id": "D2",
                "nome_completo": "Antonietta Ceraldi",
                "attivo": True,
            },
        ])


class _Db:
    def __init__(self):
        self.salari = _Salari()
        self.dipendenti = _Dipendenti()

    def __getitem__(self, name):
        return {
            "prima_nota_salari": self.salari,
            "dipendenti": self.dipendenti,
        }[name]


def test_lista_include_anagrafica_anche_senza_cedolino(monkeypatch):
    db = _Db()
    monkeypatch.setattr(
        modulo.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    result = asyncio.run(modulo.get_dipendenti_lista())

    assert result == [
        "Antonietta Ceraldi",
        "Dipendente Storico",
        "Valerio Ceraldi",
    ]
    assert db.dipendenti.query == {
        "attivo": {"$ne": False},
        "merged_into": {"$exists": False},
    }
