import asyncio

from app.lotti.supabase_document_store import PersistentDatabase


class FakeStore:
    def __init__(self):
        self.docs = {}
        self.upsert_calls = 0

    async def list_collections(self):
        return sorted(self.docs)

    async def list_docs(self, collection):
        return [dict(v) for v in self.docs.get(collection, {}).values()]

    async def upsert_docs(self, collection, docs):
        self.upsert_calls += 1
        bucket = self.docs.setdefault(collection, {})
        for doc in docs:
            bucket[str(doc["_id"])] = dict(doc)
        return len(list(docs))

    async def delete_docs(self, collection, ids):
        bucket = self.docs.setdefault(collection, {})
        n = 0
        for key in ids:
            n += int(bucket.pop(str(key), None) is not None)
        return n

    async def delete_collection(self, collection):
        return len(self.docs.pop(collection, {}))

    async def rename_collection(self, source, target, drop_target):
        if target in self.docs and not drop_target:
            raise RuntimeError("target exists")
        self.docs[target] = self.docs.pop(source, {})
        return len(self.docs[target])

    async def close(self):
        return None


def run(coro):
    return asyncio.run(coro)


def test_crud_persiste_e_si_ricarica():
    store = FakeStore()
    first = PersistentDatabase(store, "Gestionale")
    run(first.ricette.insert_one({"_id": "r1", "nome": "Babà", "qta": 1}))
    run(first.ricette.update_one({"_id": "r1"}, {"$inc": {"qta": 2}}))

    second = PersistentDatabase(store, "Gestionale")
    assert run(second.ricette.find_one({"_id": "r1"}))["qta"] == 3
    assert run(second.ricette.count_documents({})) == 1

    run(second.ricette.delete_one({"_id": "r1"}))
    third = PersistentDatabase(store, "Gestionale")
    assert run(third.ricette.find_one({"_id": "r1"})) is None


def test_cursor_sort_limit_e_aggregate():
    store = FakeStore()
    db = PersistentDatabase(store, "Gestionale")
    run(db.lotti.insert_many([
        {"_id": "1", "reparto": "pasticceria", "qta": 1},
        {"_id": "2", "reparto": "pasticceria", "qta": 3},
        {"_id": "3", "reparto": "bar", "qta": 2},
    ]))
    rows = run(db.lotti.find({}).sort("qta", -1).limit(2).to_list(2))
    assert [r["qta"] for r in rows] == [3, 2]
    grouped = run(db.lotti.aggregate([
        {"$group": {"_id": "$reparto", "totale": {"$sum": "$qta"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(10))
    assert grouped == [
        {"totale": 2, "_id": "bar"},
        {"totale": 4, "_id": "pasticceria"},
    ]


def test_aggiornamenti_diversi_vengono_persistiti_in_un_solo_lotto():
    store = FakeStore()
    db = PersistentDatabase(store, "Gestionale")
    run(db.prodotti.insert_many([
        {"_id": "1", "nome": "A", "descrizione": ""},
        {"_id": "2", "nome": "B", "descrizione": ""},
    ]))
    chiamate_prima = store.upsert_calls

    aggiornati = run(db.prodotti.update_documents_by_id([
        ("1", {"descrizione": "Descrizione A"}),
        ("2", {"descrizione": "Descrizione B"}),
    ]))

    assert aggiornati == 2
    assert store.upsert_calls == chiamate_prima + 1
    assert store.docs["prodotti"]["1"]["descrizione"] == "Descrizione A"
    assert store.docs["prodotti"]["2"]["descrizione"] == "Descrizione B"
