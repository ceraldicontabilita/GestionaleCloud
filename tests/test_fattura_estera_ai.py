"""Fatture ESTERE via email (PDF, mai XML): estrazione AI + import con la
pipeline condivisa `import_parsed_invoice` (stessa dei fatture XML), così il
matching PayPal/bonifico e l'alert di scadenza già esistenti la aggancino
senza codice nuovo lato riconciliazione (scelta utente 14/07/2026)."""
import asyncio

from app.routers.invoices.fatture_upload import (
    _ai_fattura_a_parsed,
    process_fattura_estera_pdf,
)


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in (query or {}).items()):
                return {k2: v for k2, v in d.items() if k2 != "_id"}
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, *a, **k):
        pass

    async def update_many(self, *a, **k):
        class _R:
            modified_count = 0
        return _R()

    async def delete_one(self, *a, **k):
        pass

    async def count_documents(self, *a, **k):
        return 0

    def find(self, *a, **k):
        class _Cur:
            def sort(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            async def to_list(self, *a, **k):
                return []
        return _Cur()

    def aggregate(self, *a, **k):
        class _Cur:
            async def to_list(self, *a, **k):
                return []
        return _Cur()


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


AI_OK = {
    "tipo_documento": "FATTURA",
    "numero_fattura": "RE-2026-055",
    "data_fattura": "2026-06-10",
    "fornitore": {
        "denominazione": "Foreign Supplies GmbH",
        "partita_iva": "DE123456789",
        "codice_fiscale": "",
        "indirizzo": "Musterstr. 1, Berlin",
    },
    "cliente": {"denominazione": "Ceraldi Group srl", "partita_iva": "01111111111"},
    "imponibile": 100.0,
    "iva": 0.0,
    "totale": 100.0,
    "aliquota_iva": 0,
    "metodo_pagamento": "bonifico",
    "scadenza_pagamento": "2026-07-10",
    "descrizione_righe": ["Forniture varie"],
}


def _patch_extraction(monkeypatch, structured_result):
    import app.services.document_ai_extractor as extractor

    async def _fake(base64_data, filename, document_type=None, model=None):
        return {"filename": filename, "structured_data": structured_result}

    monkeypatch.setattr(extractor, "process_document_from_base64", _fake)


def test_ai_fattura_a_parsed_mapping():
    parsed = _ai_fattura_a_parsed(AI_OK)
    assert parsed["invoice_number"] == "RE-2026-055"
    assert parsed["invoice_date"] == "2026-06-10"
    assert parsed["supplier_vat"] == "DE123456789"
    assert parsed["supplier_name"] == "Foreign Supplies GmbH"
    assert parsed["total_amount"] == 100.0
    assert parsed["imponibile"] == 100.0
    assert parsed["divisa"] == "EUR"


def test_estrazione_riuscita_crea_fattura_vera(monkeypatch):
    _patch_extraction(monkeypatch, {"success": True, "data": AI_OK})
    db = _FakeDb()

    res = _run(process_fattura_estera_pdf(db, "base64...", "fattura_estera.pdf"))

    assert res["status"] == "imported"
    invoices = db.collections["invoices"].docs
    assert len(invoices) == 1
    inv = invoices[0]
    # Schema canonico: stesso usato dalle fatture XML e letto dal matching
    # PayPal (total_amount/supplier_name) e bonifico (importo_totale/cedente_denominazione).
    assert inv["invoice_number"] == "RE-2026-055"
    assert inv["supplier_name"] == "Foreign Supplies GmbH"
    assert inv["total_amount"] == 100.0
    assert inv["importo_totale"] == 100.0
    assert inv["cedente_denominazione"] == "Foreign Supplies GmbH"
    assert inv["source"] == "email_gmail_estera"
    assert inv["status"] == "imported"


def test_dedup_seconda_fattura_identica(monkeypatch):
    _patch_extraction(monkeypatch, {"success": True, "data": AI_OK})
    db = _FakeDb()

    r1 = _run(process_fattura_estera_pdf(db, "base64...", "fattura_estera.pdf"))
    r2 = _run(process_fattura_estera_pdf(db, "base64...", "fattura_estera_bis.pdf"))

    assert r1["status"] == "imported"
    assert r2["status"] == "duplicate"
    assert len(db.collections["invoices"].docs) == 1


def test_estrazione_fallita_non_crea_nulla(monkeypatch):
    _patch_extraction(monkeypatch, {"success": False, "error": "PDF illeggibile"})
    db = _FakeDb()

    res = _run(process_fattura_estera_pdf(db, "base64...", "fattura_estera.pdf"))

    assert res["status"] == "extraction_error"
    assert "invoices" not in db.collections or db.collections["invoices"].docs == []


def test_dati_insufficienti_non_crea_nulla(monkeypatch):
    dati_vuoti = {**AI_OK, "numero_fattura": None, "totale": None}
    _patch_extraction(monkeypatch, {"success": True, "data": dati_vuoti})
    db = _FakeDb()

    res = _run(process_fattura_estera_pdf(db, "base64...", "fattura_estera.pdf"))

    assert res["status"] == "dati_insufficienti"
    assert "invoices" not in db.collections or db.collections["invoices"].docs == []
