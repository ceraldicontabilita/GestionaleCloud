import asyncio
import copy
import re

from app.services import verbali_document_import as mod


def _match(doc, query):
    if not query:
        return True
    if "$or" in query:
        return any(_match(doc, item) for item in query["$or"])
    for key, expected in query.items():
        if key.startswith("$"):
            continue
        actual = doc.get(key)
        if isinstance(expected, dict) and "$regex" in expected:
            flags = re.I if "i" in expected.get("$options", "") else 0
            if not re.search(expected["$regex"], str(actual or ""), flags):
                return False
        elif actual != expected:
            return False
    return True


class _Result:
    modified_count = 1


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, _n):
        return self

    async def to_list(self, n):
        return [copy.deepcopy(doc) for doc in self.docs[:n]]


class _Collection:
    def __init__(self, docs=None):
        self.docs = [copy.deepcopy(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        found = next((doc for doc in self.docs if _match(doc, query)), None)
        return copy.deepcopy(found) if found else None

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _match(doc, query)])

    async def update_one(self, query, update, upsert=False):
        found = next((doc for doc in self.docs if _match(doc, query)), None)
        inserted = False
        if found is None and upsert:
            found = {key: value for key, value in query.items() if not key.startswith("$")}
            self.docs.append(found)
            inserted = True
        if found is None:
            return _Result()
        found.update(copy.deepcopy(update.get("$set", {})))
        if inserted:
            for key, value in update.get("$setOnInsert", {}).items():
                found.setdefault(key, copy.deepcopy(value))
        for key, value in update.get("$addToSet", {}).items():
            values = found.setdefault(key, [])
            if value not in values:
                values.append(copy.deepcopy(value))
        return _Result()


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def _run(coro):
    return asyncio.run(coro)


def test_documento_senza_numero_o_iuv_resta_da_revisionare(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-1", "status": "nuovo"}]
    monkeypatch.setattr(mod, "_extract_text", lambda _content: "Documento generico senza riferimenti")

    result = _run(mod.process_verbale_document(
        db, document_id="doc-1", content=b"pdf", filename="documento.pdf"
    ))

    assert result["status"] == "review"
    assert db["documents_inbox"].docs[0]["status"] == "da_revisionare"
    assert db["documents_inbox"].docs[0]["processed"] is False
    assert db["verbali_noleggio"].docs == []


def test_verbale_collega_documento_veicolo_e_driver_senza_duplicare(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-1"}]
    db["veicoli_noleggio"].docs = [{
        "id": "car-1", "targa": "AB123CD", "driver_id": "dip-1", "driver": "Mario Rossi"
    }]
    monkeypatch.setattr(
        mod,
        "_extract_text",
        lambda _content: "Verbale numero A25111540620 Targa AB123CD Da pagare euro 120,50",
    )

    first = _run(mod.process_verbale_document(
        db, document_id="doc-1", content=b"same", filename="verbale.pdf"
    ))
    second = _run(mod.process_verbale_document(
        db, document_id="doc-1", content=b"same", filename="verbale.pdf"
    ))

    assert first["verbale_id"] == second["verbale_id"]
    assert len(db["verbali_noleggio"].docs) == 1
    verbale = db["verbali_noleggio"].docs[0]
    assert verbale["numero_verbale"] == "A25111540620"
    assert verbale["targa"] == "AB123CD"
    assert verbale["driver_id"] == "dip-1"
    assert verbale["document_ids"] == ["doc-1"]
    assert db["documents_inbox"].docs[0]["verbale_id"] == verbale["id"]


def test_ricevuta_pagopa_non_si_associa_se_importo_non_coincide(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-r"}]
    db["verbali_noleggio"].docs = [{
        "id": "verb-1", "numero_verbale": "A25111540620", "importo": 120.51
    }]
    monkeypatch.setattr(
        mod,
        "_extract_text",
        lambda _content: (
            "Ricevuta di pagamento Verbale numero A25111540620 "
            "Codice Avviso 012345678901234567 Totale 120,50 Data pagamento 05/08/2026"
        ),
    )

    result = _run(mod.process_verbale_document(
        db, document_id="doc-r", content=b"receipt", filename="ricevuta_pagopa.pdf"
    ))

    assert result["status"] == "review"
    assert result["verbale_id"] is None
    assert db["ricevute_pagopa"].docs[0]["stato"] == "non_associata"
    assert db["documents_inbox"].docs[0]["processed"] is False
