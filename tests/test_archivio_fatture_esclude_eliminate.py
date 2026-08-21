"""Bug trovato in audit 15/07/2026: DELETE /api/fatture/{id} (default, senza
hard_delete) fa un soft-delete — CascadeOperations.delete_fattura_cascade
imposta status="deleted" ed entity_status="deleted" sul documento in
`invoices`, ma né la query dell'Archivio Fatture né il dettaglio fattura
escludevano quello stato: una fattura "eliminata" poteva ricomparire in
lista/dettaglio nonostante il messaggio di conferma dell'UI dica che
l'operazione non è reversibile."""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.fatture_module import crud as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


def _matches(doc, query):
    for k, v in query.items():
        if k in ("$and", "$or"):
            continue
        if isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    for sub in query.get("$and", []):
        if not _matches(doc, sub):
            return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_archivio_fatture_esclude_eliminate(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [
        {"id": "f1", "invoice_number": "1", "invoice_date": "2026-05-10",
         "supplier_name": "Attiva SRL", "total_amount": 100.0},
        # Eliminata da DELETE /api/fatture/f2 (default, soft-delete reale).
        {"id": "f2", "invoice_number": "2", "invoice_date": "2026-05-11",
         "supplier_name": "Eliminata SRL", "total_amount": 200.0,
         "status": "deleted", "entity_status": "deleted"},
    ]

    esito = _run(mod.get_archivio_fatture(
        anno=None, mese=None, fornitore_piva=None, fornitore_nome=None,
        stato=None, search=None, limit=200, skip=0,
    ))

    ids = [f["id"] for f in esito["fatture"]]
    assert "f1" in ids
    assert "f2" not in ids


def test_archivio_usa_metodo_canonico_prima_del_legacy(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [
        {"id": "f1", "invoice_number": "1", "invoice_date": "2026-07-16",
         "supplier_name": "FORNITORE TEST SRL", "supplier_vat": "00000000000",
         "total_amount": 100.0},
    ]
    db["fornitori"].docs = [
        {"partita_iva": "00000000000", "ragione_sociale": "FORNITORE TEST SRL",
         "metodo_pagamento": "misto", "metodo_pagamento_predefinito": "cassa"},
    ]

    esito = _run(mod.get_archivio_fatture(
        anno=2026, mese=None, fornitore_piva=None, fornitore_nome=None,
        stato=None, search=None, limit=200, skip=0,
    ))

    assert esito["fatture"][0]["fornitore_metodo_pagamento"] == "misto"


def test_dettaglio_fattura_eliminata_ritorna_404(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [
        {"id": "f2", "invoice_number": "2", "status": "deleted", "entity_status": "deleted"},
    ]

    try:
        _run(mod.get_fattura_dettaglio("f2"))
        assert False, "doveva sollevare 404"
    except Exception as e:
        assert getattr(e, "status_code", None) == 404


def test_dettaglio_fattura_attiva_resta_visibile(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["invoices"].docs = [
        {"id": "f1", "invoice_number": "1"},
    ]

    esito = _run(mod.get_fattura_dettaglio("f1"))

    assert esito["fattura"]["id"] == "f1"


def test_statistiche_restano_disponibili_nel_database_e2e_in_memoria(monkeypatch):
    db = MemorySheetsClient()["fatture_statistiche_e2e"]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    _run(db["invoices"].insert_many([
        {
            "id": "f1", "invoice_number": "1", "invoice_date": "2026-08-08",
            "supplier_vat": "00000000001", "total_amount": 122.0,
        },
        {
            "id": "f2", "invoice_number": "2", "invoice_date": "2026-08-07",
            "supplier_vat": "00000000002", "total_amount": 244.0,
            "status": "paid",
        },
    ]))

    esito = _run(mod.get_statistiche(anno=2026))

    assert esito["totale_fatture"] == 2
    assert esito["totale_importo"] == 366.0
    assert esito["pagate"] == 1
    assert esito["fornitori_unici"] == 2
