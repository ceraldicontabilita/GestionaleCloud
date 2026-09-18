"""P1 §5.5 — Fatture emesse unificate sulla canonica `fatture_emesse`: il CRUD
scrive e legge da un unico posto reale, non più dall'alias legacy `invoices_emesse`."""
import asyncio
import inspect

from app.routers.invoices import invoices_emesse as mod


class _Coll:
    def __init__(self, name):
        self.name = name
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def delete_one(self, query):
        self.docs = [d for d in self.docs if d.get("id") != query.get("id")]

    def find(self, *a, **k):
        outer = self

        class _Cur:
            def sort(self, *a, **k):
                return self

            async def to_list(self, *a, **k):
                return list(outer.docs)
        return _Cur()

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if d.get("id") == query.get("id"):
                return d
        return None


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        if name not in self.colls:
            self.colls[name] = _Coll(name)
        return self.colls[name]


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _patch_db(monkeypatch, monkey_db):
    """Isola il database finto al singolo test.

    Una assegnazione diretta a ``Database.get_db`` contaminava tutti i test
    successivi nello stesso processo e poteva bloccare il test del lease dello
    scheduler. ``monkeypatch`` ripristina sempre il metodo originale.
    """
    monkeypatch.setattr(
        mod.Database,
        "get_db",
        staticmethod(lambda: monkey_db),
    )


def test_crud_usa_solo_fatture_emesse(monkeypatch):
    db = _Db()
    _patch_db(monkeypatch, db)
    user = {"user_id": "u1"}

    _run(mod.create_invoice_emessa(data={"cliente": "ACME", "importo": 100}, current_user=user))

    # scritto SOLO nella canonica
    assert "fatture_emesse" in db.colls
    assert db.colls["fatture_emesse"].docs
    assert "invoices_emesse" not in db.colls

    lista = _run(mod.get_invoices_emesse(current_user=user))
    assert len(lista) == 1 and lista[0]["cliente"] == "ACME"


def test_nessun_riferimento_invoices_emesse_nel_sorgente():
    src = inspect.getsource(mod)
    assert 'db["invoices_emesse"]' not in src
    assert 'db["fatture_emesse"]' in src
