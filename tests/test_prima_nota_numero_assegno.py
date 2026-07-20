import asyncio

from app.routers.prima_nota_module import banca as banca_mod


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Result:
    def __init__(self, matched_count=0):
        self.matched_count = matched_count


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return _Result(1)
        return _Result(0)


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def test_creazione_banca_salva_entrambi_gli_alias_numero_assegno(monkeypatch):
    db = _Db()
    monkeypatch.setattr(banca_mod.Database, "get_db", staticmethod(lambda: db))

    _run(banca_mod.create_prima_nota_banca({
        "data": "2026-05-31",
        "tipo": "uscita",
        "importo": 1098.28,
        "descrizione": "Fattura fornitore",
        "categoria": "Fatture",
        "numero_assegno": "208769333",
    }))

    movimento = db[banca_mod.COLLECTION_PRIMA_NOTA_BANCA].docs[0]
    assert movimento["numero_assegno"] == "208769333"
    assert movimento["assegno_numero"] == "208769333"


def test_modifica_banca_normalizza_il_numero_assegno(monkeypatch):
    db = _Db()
    db[banca_mod.COLLECTION_PRIMA_NOTA_BANCA].docs = [{"id": "mov-1"}]
    monkeypatch.setattr(banca_mod.Database, "get_db", staticmethod(lambda: db))

    _run(banca_mod.update_prima_nota_banca("mov-1", {
        "numero_assegno": " 208769333 ",
    }))

    movimento = db[banca_mod.COLLECTION_PRIMA_NOTA_BANCA].docs[0]
    assert movimento["numero_assegno"] == "208769333"
    assert movimento["assegno_numero"] == "208769333"
