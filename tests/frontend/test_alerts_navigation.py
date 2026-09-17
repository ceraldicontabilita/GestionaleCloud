import asyncio

from app.routers import alerts as alerts_router


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.offset = 0
        self.maximum = len(rows)

    def sort(self, *_args):
        return self

    def skip(self, value):
        self.offset = value
        return self

    def limit(self, value):
        self.maximum = value
        return self

    async def to_list(self, _value):
        return self.rows[self.offset:self.offset + self.maximum]


class EmptyAggregate:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class FakeAlertsCollection:
    def __init__(self):
        self.queries = []

    async def count_documents(self, query):
        self.queries.append(query)
        return 2 if query else 5

    def find(self, query, _projection):
        self.queries.append(query)
        return FakeCursor([{"id": "A-1"}, {"id": "A-2"}])

    def aggregate(self, _pipeline):
        return EmptyAggregate()


def test_lista_alert_aperti_filtrata_e_paginata(monkeypatch):
    collection = FakeAlertsCollection()
    monkeypatch.setattr(alerts_router.Database, "get_db", lambda: {"alerts": collection})

    result = asyncio.run(alerts_router.lista_alerts(
        tipo=None, severita="critical", modulo="f24", alert_id=None,
        stato="aperto", letto=None, risolto=None, offset=1, limit=1,
    ))

    filtered_query = collection.queries[0]
    assert filtered_query["severita"] == "critical"
    assert filtered_query["modulo"] == "f24"
    assert {"stato": "aperto"} in filtered_query["$or"]
    assert result["alerts"] == [{"id": "A-2"}]
    assert result["stats"]["totale_filtrato"] == 2
    assert result["pagination"] == {"offset": 1, "limit": 1, "has_more": False}
