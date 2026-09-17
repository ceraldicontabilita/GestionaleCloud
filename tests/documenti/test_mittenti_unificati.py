"""Test dell'unificazione mittenti (P2-2): accessor unico su `mittenti_email`
con union legacy, e migrazione idempotente da `mittenti_attendibili`."""
import asyncio

from app.services import mittenti as M


class _Cur:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._it = iter(list(self._items))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, n):
        return [dict(x) for x in self._items[:n]]


def _match(d, q):
    return all(d.get(k) == v for k, v in q.items())


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, query, proj=None):
        return _Cur([d for d in self.docs if _match(d, query)])

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_senders_unisce_canonica_e_legacy():
    db = _Db()
    db["mittenti_email"].docs = [
        {"pattern": "pm@comune.it", "canale": "gmail",
         "tipo_documento": "verbale_cds", "attivo": True},
    ]
    db["mittenti_attendibili"].docs = [
        {"indirizzo_email": "verbali@polizia.it", "canale": "gmail",
         "tipo_documento": "verbale_cds", "attivo": True},
        # tipo diverso: non deve comparire
        {"indirizzo_email": "x@y.it", "canale": "gmail",
         "tipo_documento": "altro", "attivo": True},
    ]
    s = _run(M.senders_attendibili(db, "verbale_cds", "gmail"))
    assert s == {"pm@comune.it", "verbali@polizia.it"}


def test_migrazione_idempotente():
    db = _Db()
    db["mittenti_attendibili"].docs = [
        {"indirizzo_email": "A@B.it", "canale": "gmail",
         "tipo_documento": "verbale_cds", "attivo": True},
        {"indirizzo_email": "gia@presente.it", "canale": "gmail",
         "tipo_documento": "verbale_cds", "attivo": True},
    ]
    db["mittenti_email"].docs = [
        {"pattern": "gia@presente.it", "canale": "gmail",
         "tipo_documento": "verbale_cds", "attivo": True},
    ]
    # dry-run: nulla scritto
    dry = _run(M.migra_mittenti_legacy(db, dry_run=True))
    assert dry["migrati"] == 1 and dry["gia_presenti"] == 1
    assert len(db["mittenti_email"].docs) == 1
    # esecuzione: migra il solo mancante
    run = _run(M.migra_mittenti_legacy(db, dry_run=False))
    assert run["migrati"] == 1
    assert len(db["mittenti_email"].docs) == 2
    # riesecuzione: idempotente, nessun nuovo doc
    again = _run(M.migra_mittenti_legacy(db, dry_run=False))
    assert again["migrati"] == 0 and again["gia_presenti"] == 2
    assert len(db["mittenti_email"].docs) == 2
