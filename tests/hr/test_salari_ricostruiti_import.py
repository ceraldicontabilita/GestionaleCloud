import asyncio

from app.routers.accounting import prima_nota_salari as modulo


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return list(self.docs)


class _Collection:
    def __init__(self):
        self.docs = []

    def find(self, _query, _projection):
        return _Cursor(self.docs)

    async def insert_many(self, docs):
        self.docs.extend(docs)


class _Db:
    def __init__(self):
        self.collection = _Collection()

    def __getitem__(self, name):
        assert name == "salari_ricostruiti"
        return self.collection


def test_importo_ricostruito_include_acconto_senza_dichiarare_pagamento(monkeypatch):
    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))
    payload = {"righe": [{
        "workbook_row": 2,
        "employee": "Ariante Marcella",
        "year": 2018,
        "month_label": "Gennaio",
        "net_residual": 1000,
        "payslip_advance": 200,
        "reconstructed_amount": 1200,
        "residual_to_pay": 1200,
        "payslip_source": "Busta paga - Ariante Marcella - Gennaio 2018.pdf",
    }]}

    result = asyncio.run(modulo.import_salari_ricostruiti(payload, {}))

    assert result["created"] == 1
    assert result["totale_ricostruito"] == 1200
    record = db.collection.docs[0]
    assert record["netto_residuo_busta"] == 1000
    assert record["acconto_indicato_busta"] == 200
    assert record["importo_busta_ricostruito"] == 1200
    assert record["stato_pagamento"] == "PAGAMENTO_DA_ASSOCIARE"
    assert record["riconciliato"] is False


def test_data_e_riferimento_restano_evidenza_documentale(monkeypatch):
    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))
    payload = {"righe": [{
        "workbook_row": 100,
        "employee": "Ceraldi Valerio",
        "year": 2022,
        "month_label": "Settembre",
        "reconstructed_amount": 900,
        "payment_dates": "22/01/2023",
        "bank_references": "139467067",
        "payslip_source": "cedolino.pdf",
    }]}

    result = asyncio.run(modulo.import_salari_ricostruiti(payload, {}))

    assert result["evidenze_complete"] == 1
    record = db.collection.docs[0]
    assert record["stato_pagamento"] == "EVIDENZA_DOCUMENTALE_COMPLETA"
    assert record["riferimenti_bancari_documentati"] == "139467067"
    assert record["riconciliato"] is False
