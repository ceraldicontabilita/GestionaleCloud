import asyncio

from app.services.document_hash_lookup import find_one_by_hashes


class _Collection:
    def __init__(self, records, calls):
        self.records = records
        self.calls = calls

    async def find_one(self, selector, projection=None):
        self.calls.append((selector, projection))
        field, value = next(iter(selector.items()))
        return next((row for row in self.records if row.get(field) == value), None)


class _Database:
    def __init__(self, records):
        self.calls = []
        self.collection = _Collection(records, self.calls)

    def __getitem__(self, name):
        assert name == "documents_inbox"
        return self.collection


def test_lookup_hash_non_costruisce_query_or_e_si_ferma_al_primo_match():
    db = _Database([{"id": "doc-1", "file_hash": "legacy"}])
    found = asyncio.run(find_one_by_hashes(
        db,
        "documents_inbox",
        (("sha256", "strong"), ("file_hash", "legacy"), ("file_hash", "legacy")),
        {"id": 1},
    ))

    assert found == {"id": "doc-1", "file_hash": "legacy"}
    assert db.calls == [
        ({"sha256": "strong"}, {"id": 1}),
        ({"file_hash": "legacy"}, {"id": 1}),
    ]
