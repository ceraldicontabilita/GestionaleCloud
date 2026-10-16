"""Parallel MiniHR adapters: fake identities, read-only DB and admin boundaries."""
import asyncio
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.hr.services import minihr
from app.hr.routers import minihr as routes
from app.hr.utils import dependencies
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def run(coro):
    return asyncio.run(coro)


class ReadOnlyCollection:
    def __init__(self, collection):
        self.collection = collection

    def __getattr__(self, method):
        assert method in ("find", "find_one", "count_documents"), f"Unexpected write: {method}"
        return getattr(self.collection, method)


class ReadOnlyDB:
    def __init__(self, db):
        self.db = db

    def __getitem__(self, key):
        return ReadOnlyCollection(self.db[key])

    def __getattr__(self, key):
        return self[key]


def test_dossier_preserves_canonical_engine_and_documents_only(monkeypatch):
    db = ClientArchivioMemoria()["minihr_fake"]
    run(db.documenti_cloud.insert_one({"id": "doc-1", "dipendente_id": "example-1", "tipo": "UNILAV",
                                     "titolo": "Proroga esempio", "file_data": "NEVER_EXPOSE", "data_caricamento": "2026-02-01"}))
    movements = {"registro": [
        {"tipo": "busta", "descrizione": "Busta tredicesima", "dare": Decimal("123.45"), "avere": None,
         "competenza": (2025, 13), "fonte": "cedolino", "link": {"cedolino_id": "slip-1"}},
        {"tipo": "bonifico", "descrizione": "Pagamento esempio", "dare": None, "avere": Decimal("100.00"),
         "data": "2025-12-20", "fonte": "pagamenti_esiti", "link": {"key": "payment-1"}},
        {"tipo": "busta", "dare": None, "avere": None, "competenza": (2026, 1), "link": {}, "avviso": "Illeggibile"},
    ], "bonus": []}
    async def load(db, dip_id):
        assert dip_id == "example-1"
        return movements
    monkeypatch.setattr(minihr.pos, "carica_movimenti", load)
    original = repr(movements)
    result = run(minihr.dossier(ReadOnlyDB(db), {"id": "example-1", "nome_completo": "Persona Esempio", "data_assunzione": "2025-01-01"}))
    assert result["mode"] == "read-only"
    e = result["employee"]
    assert e["slips"][0]["type"] == "Tredicesima" and e["slips"][0]["month"] == "2025-12"
    assert e["slips"][0]["amountCents"] == 12345
    assert e["slips"][1]["amountCents"] is None and e["slips"][1]["counted"] is False
    assert sum(p["amountCents"] for p in e["payments"]) == 10000
    assert result["undatedDocuments"][0]["month"] == ""
    assert "NEVER_EXPOSE" not in str(result) and "file_data" not in str(result)
    assert repr(movements) == original


def test_engine_integration_does_not_write_or_match_by_amount():
    db = ClientArchivioMemoria()["minihr_engine"]
    run(db.dipendenti.insert_one({"id": "example-1", "nome_completo": "Persona Esempio"}))
    run(db.cedolini.insert_one({"id": "slip-1", "dipendente_id": "example-1", "anno": 2025, "mese": 3, "netto": 150.0}))
    run(db.pagamenti_esiti.insert_one({"key": "pay-1", "dipendente_id": "example-1", "anno": 2025, "mese": 3,
                                      "data": "2025-04-01", "importo": 150.0}))
    run(db.pagamenti_esiti.insert_one({"key": "pay-other", "dipendente_id": "other-person", "anno": 2025, "mese": 3,
                                      "data": "2025-04-01", "importo": 150.0}))
    result = run(minihr.dossier(ReadOnlyDB(db), {"id": "example-1", "nome_completo": "Persona Esempio"}))
    assert sum(s["amountCents"] or 0 for s in result["employee"]["slips"]) == 15000
    assert sum(p["amountCents"] for p in result["employee"]["payments"]) == 15000
    assert result["employee"]["events"] == []


def test_f24_reads_existing_register_without_claiming_payment(monkeypatch):
    from app.db_collections import COLL_F24
    from app.services import f24_controllo_incrociato as fiscal
    db = ClientArchivioMemoria()["minihr_fiscal"]
    for doc in [{"id": "f-1", "codice_fiscale": "00000000000"},
                {"id": "f-other", "codice_fiscale": "11111111111"},
                {"id": "f-deleted", "codice_fiscale": "00000000000", "status": "eliminato"}]:
        run(db[COLL_F24].insert_one(doc))
    monkeypatch.setattr(fiscal, "righe_modello", lambda _: [
        {"codice": "1001", "anno": 2022, "mese": 11},
        {"codice": "1001", "anno": 2022, "mese": 12},
        {"codice": "3848", "anno": 2025, "mese": None},
    ])
    result = run(minihr.company_f24(ReadOnlyDB(db), "00000000000"))
    assert [d["id"] for d in result["documents"]] == ["f-1"]
    assert len(result["documents"][0]["lines"]) == 2
    assert result["documents"][0]["evidence"]["stato"] == "DA_PAGARE"
    assert "employee" not in result


def test_api_fails_closed_no_anonymous_or_staff_data(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/minihr")
    client = TestClient(app)
    for path in ("/employees", "/employees/example-1", "/company-f24/00000000000"):
        assert client.get("/api/minihr" + path).status_code in (401, 403)
    async def staff(_):
        return {"role": "responsabile_turni"}
    monkeypatch.setattr(dependencies, "_decode_or_401", staff)
    assert client.get("/api/minihr/employees", headers={"Authorization": "Bearer test-only"}).status_code == 403
    assert all(r.methods == {"GET"} for r in routes.router.routes)


def test_decimal_and_period_contract():
    assert minihr.money_cents(None) is None
    assert minihr.money_cents(Decimal("0.00")) == 0
    assert minihr.calendar_month(2025, 13) == "2025-12"
    assert minihr.calendar_month(2025, 14) == "2025-06"
    assert minihr.calendar_month(2025, 15) == ""
