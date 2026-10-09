import asyncio

from app.routers import noleggio


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.offset = 0
        self.maximum = len(self.rows)
        self.position = 0

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

    def __aiter__(self):
        self.position = 0
        return self

    async def __anext__(self):
        if self.position >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self.position]
        self.position += 1
        return row


class Collection:
    def __init__(self, rows):
        self.rows = rows

    async def count_documents(self, _query):
        return len(self.rows)

    def find(self, _query, _projection):
        return Cursor(self.rows)


def test_riepilogo_noleggio_pagina_anche_i_casi_oltre_i_primi_dieci(monkeypatch):
    db = {
        noleggio.COLLECTION_VERBALI_POSTA: Collection([
            {"numero_verbale": f"V-{index}", "data_verbale": f"2026-01-0{index + 1}", "stato": "aperto"}
            for index in range(3)
        ]),
        noleggio.COLLECTION_VERBALI_FATTURE: Collection([]),
        "trattenute_dipendenti": Collection([{"id": f"T-{index}"} for index in range(3)]),
        noleggio.COLLECTION: Collection([{"targa": f"AA00{index}AA"} for index in range(3)]),
        "invoices": Collection([{"id": f"I-{index}"} for index in range(3)]),
        "alerts": Collection([{"id": f"A-{index}"} for index in range(3)]),
    }
    monkeypatch.setattr(noleggio.Database, "get_db", lambda: db)

    async def fake_fatture_non_associate(anno=None):
        return {"fatture": [{"id": f"F-{index}"} for index in range(3)]}

    monkeypatch.setattr(noleggio, "get_fatture_non_associate", fake_fatture_non_associate)
    result = asyncio.run(noleggio.get_riepilogo_controlli(anno=2026, offset=1, limit=1))

    assert result["trattenute_da_confermare"]["items"] == [{"id": "T-1"}]
    assert result["auto_senza_driver"]["items"] == [{"targa": "AA001AA"}]
    assert result["fatture_non_associate"]["items"] == [{"id": "F-1"}]
    assert result["pagamenti_non_riconciliati"]["items"] == [{"id": "I-1"}]
    assert result["alert_aperti"]["items"] == [{"id": "A-1"}]
    assert result["pagination"] == {"offset": 1, "limit": 1}
