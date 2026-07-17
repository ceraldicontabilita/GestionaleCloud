"""Bug segnalato dall'utente 15/07/2026 (estratto conto Excel): un
versamento di contanti in banca veniva riconciliato — l'uscita cassa e il
movimento EC risultavano marcati "riconciliato" — ma non compariva MAI la
corrispondente voce in dare (entrata) in Prima Nota Banca: la riconciliazione
si limitava a marcare i due lati come riconciliati senza mai creare il
movimento bancario."""
import asyncio

from app.services import riconciliazione_bancaria as mod


def _match_value(actual, expected):
    if isinstance(expected, dict):
        if "$ne" in expected and actual == expected["$ne"]:
            return False
        if "$in" in expected and actual not in expected["$in"]:
            return False
        if "$nin" in expected and actual in expected["$nin"]:
            return False
        if "$gte" in expected and (actual is None or actual < expected["$gte"]):
            return False
        if "$lte" in expected and (actual is None or actual > expected["$lte"]):
            return False
        return True
    return actual == expected


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if k == "$and":
            if not all(_matches(doc, sub) for sub in v):
                return False
            continue
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        if not _match_value(doc.get(k), v):
            return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        return iter(self._docs).__iter__() if False else _AsyncIter(self._docs)

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _AsyncIter:
    def __init__(self, docs):
        self._docs = list(docs)
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_versamento_riconciliato_crea_movimento_banca(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-1", "data": "2026-07-10", "importo": 500.0, "tipo": "entrata",
        "descrizione_originale": "VERSAMENTO CONTANTI SPORTELLO", "riconciliato": False,
    }]
    db["prima_nota_cassa"].docs = [{
        "id": "cassa-1", "data": "2026-07-10", "importo": 500.0,
        "categoria": "Versamento Banca", "tipo": "uscita", "riconciliato": False,
    }]

    res = _run(mod.riconcilia_movimenti_banca())

    assert res["riconciliati_versamenti"] == 1

    cassa = db["prima_nota_cassa"].docs[0]
    assert cassa["riconciliato"] is True

    ec = db["estratto_conto_movimenti"].docs[0]
    assert ec["riconciliato"] is True
    assert ec["tipo_riconciliazione"] == "versamento"

    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["tipo"] == "entrata"
    assert banca[0]["importo"] == 500.0
    assert banca[0]["categoria"] == "Versamento Banca"
    assert banca[0]["estratto_conto_id"] == "EC-1"
    assert banca[0]["prima_nota_cassa_id"] == "cassa-1"
