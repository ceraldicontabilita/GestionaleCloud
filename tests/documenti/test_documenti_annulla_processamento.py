"""Segnalato dall'utente 18/07/2026: "ho cliccato f24 ed ho sbagliato come
riclassifico, ma poi a cosa mi serve se gia mi dice cartella esattoriale?"
— un documento (documents_inbox, RAV_AR071767964..., category già corretta
"cartella_esattoriale") era stato marcato per errore processed_to="f24" via
POST /documento/{id}/processa. Quell'endpoint non scrive nulla nella
collezione di destinazione (solo segna processed/processed_to/status sul
documento), quindi annullare è un semplice reset di questi metadati:
annulla_processamento_documento fa esattamente questo."""
import asyncio

from fastapi import HTTPException

from app.routers.documenti import annulla_processamento_documento


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def update_one(self, q, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                if "$unset" in update:
                    for k in update["$unset"]:
                        d.pop(k, None)
                if "$set" in update:
                    d.update(update["$set"])


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())


def test_annulla_processamento_resetta_metadati_e_mantiene_categoria(monkeypatch):
    db = _DB()
    db["documents_inbox"].docs = [{
        "id": "d1", "category": "cartella_esattoriale",
        "status": "processato", "processed": True, "processed_to": "f24",
        "processed_at": "2026-07-18T20:46:14",
    }]
    import app.routers.documenti as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(annulla_processamento_documento(doc_id="d1"))
    assert res["success"] is True
    assert res["category"] == "cartella_esattoriale"
    doc = db["documents_inbox"].docs[0]
    assert doc["status"] == "nuovo"
    assert "processed" not in doc
    assert "processed_to" not in doc
    assert "processed_at" not in doc
    assert doc["category"] == "cartella_esattoriale"


def test_annulla_processamento_documento_non_processato_errore(monkeypatch):
    db = _DB()
    db["documents_inbox"].docs = [{"id": "d1", "status": "nuovo"}]
    import app.routers.documenti as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    try:
        _run(annulla_processamento_documento(doc_id="d1"))
        assert False, "doveva sollevare HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


def test_annulla_processamento_documento_inesistente_errore(monkeypatch):
    db = _DB()
    import app.routers.documenti as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    try:
        _run(annulla_processamento_documento(doc_id="non-esiste"))
        assert False, "doveva sollevare HTTPException"
    except HTTPException as e:
        assert e.status_code == 404
