import asyncio

from app.utils.iva_calculator import calculate_daily_iva


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return list(self.docs)


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, _projection):
        return _Cursor([
            row for row in self.docs
            if all(row.get(key) == value for key, value in query.items())
        ])


class _Db:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, name):
        return _Collection(self.data.get(name, []))


def test_calcolo_giornaliero_non_stima_iva_detraibile_dal_totale():
    db = _Db({
        "invoices": [
            {
                "invoice_date": "2026-03-10", "invoice_number": "A",
                "total_amount": 122, "iva": 22,
            },
            {
                "invoice_date": "2026-03-10", "invoice_number": "B",
                "total_amount": 122, "iva": 22, "iva_detraibile": 8.8,
            },
        ],
        "corrispettivi": [],
    })

    result = asyncio.run(calculate_daily_iva(db, "2026-03-10"))

    assert result["iva_credito"] == 8.8
    assert [row["iva"] for row in result["fatture"]["items"]] == [0, 8.8]
