"""P1 §5.2 — Alla cessazione di un dipendente i contratti attivi vanno terminati
sulla canonica `contratti_dipendenti` (non sull'alias legacy vuoto
`employee_contracts`). Regressione del redirect."""
import asyncio

from app.services.handlers.dipendente_handlers import on_dipendente_cessato


class _Coll:
    def __init__(self, name, docs=None):
        self.name = name
        self.docs = docs or []
        self.update_many_calls = 0

    async def update_many(self, query, update):
        self.update_many_calls += 1
        n = 0
        for d in self.docs:
            if d.get("dipendente_id") == query.get("dipendente_id"):
                d.update(update.get("$set", {}))
                n += 1

        class _R:
            modified_count = n
        return _R()

    async def update_one(self, *a, **k):
        class _R:
            modified_count = 0
        return _R()

    def find(self, *a, **k):
        class _Cur:
            def __init__(self, docs):
                self._docs = docs

            def sort(self, *a, **k):
                return self

            async def to_list(self, *a, **k):
                return list(self._docs)
        return _Cur([])

    async def find_one(self, *a, **k):
        return None

    async def insert_one(self, *a, **k):
        return None

    async def count_documents(self, *a, **k):
        return 0


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


def test_cessazione_termina_contratti_su_canonica():
    db = _Db()
    # contratto attivo reale nella canonica
    db.colls["contratti_dipendenti"] = _Coll(
        "contratti_dipendenti",
        [{"dipendente_id": "DIP1", "stato": "attivo", "data_fine": None}],
    )
    _run(on_dipendente_cessato(
        {"dipendente_id": "DIP1", "nome_completo": "Mario Rossi",
         "data_cessazione": "2026-06-30"}, db))

    canonica = db.colls["contratti_dipendenti"]
    assert canonica.update_many_calls == 1
    assert canonica.docs[0]["stato"] == "terminato"
    assert canonica.docs[0]["data_fine"] == "2026-06-30"
    # l'alias legacy NON deve ricevere update_many
    assert db.colls.get("employee_contracts") is None or \
        db.colls["employee_contracts"].update_many_calls == 0
