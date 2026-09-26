import base64
import asyncio

from app.services import bonifici_pdf_ingest as mod


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


class Collection:
    def __init__(self, metadata, payloads):
        self.metadata = metadata
        self.payloads = payloads
        self.find_projections = []
        self.find_one_projections = []

    def find(self, _selector, projection):
        self.find_projections.append(projection)
        return Cursor(self.metadata)

    async def find_one(self, selector, projection):
        self.find_one_projections.append(projection)
        key = selector.get("_id") or selector.get("id")
        return {"pdf_data": self.payloads[key]}

    async def update_one(self, *_args, **_kwargs):
        return None


class DB:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, name):
        return self.collections[name]


def test_inbox_non_materializza_cento_pdf_in_memoria(monkeypatch):
    encoded = base64.b64encode(b"pdf").decode()
    collection = Collection(
        [{"_id": "d1", "filename": "uno.pdf", "created_at": "2026"}],
        {"d1": encoded},
    )
    db = DB({"documents_inbox": collection})

    async def importa(*_args, **_kwargs):
        return {"status": "duplicate", "associato": False}

    monkeypatch.setattr(mod, "importa_pdf_bonifico", importa)
    result = asyncio.run(mod.processa_inbox_bonifici(db))

    assert result["letti"] == 1
    assert collection.find_projections[0].get("pdf_data") is None
    assert collection.find_one_projections == [{"_id": 0, "pdf_data": 1}]


def test_pendenti_carica_un_pdf_per_volta(monkeypatch):
    encoded = base64.b64encode(b"pdf").decode()
    collection = Collection(
        [{"_id": "t1", "source_file": "uno.pdf", "created_at": "2026"}],
        {"t1": encoded},
    )
    db = DB({"bonifici_transfers": collection})

    async def importa(*_args, **_kwargs):
        return {"status": "duplicate", "associato": False}

    monkeypatch.setattr(mod, "importa_pdf_bonifico", importa)
    result = asyncio.run(mod.riprocessa_bonifici_pendenti(db))

    assert result == {"letti": 1, "associati": 0, "non_associati": 1, "errori": 0}
    assert collection.find_projections[0].get("pdf_data") is None
    assert collection.find_one_projections == [{"_id": 0, "pdf_data": 1}]


def test_pendenti_ruotano_sui_meno_recenti(monkeypatch):
    """Il giro prende i riletti meno di recente, non sempre i piu' vecchi creati."""
    encoded = base64.b64encode(b"pdf").decode()
    collection = Collection(
        [
            {"_id": "vecchio_appena_riletto", "created_at": "2026-01-01",
             "updated_at": "2026-09-26T15:00"},
            {"_id": "nuovo_mai_riletto", "created_at": "2026-09-26T11:00"},
            {"_id": "medio", "created_at": "2026-03-01", "updated_at": "2026-09-26T09:00"},
        ],
        {k: encoded for k in ("vecchio_appena_riletto", "nuovo_mai_riletto", "medio")},
    )
    db = DB({"bonifici_transfers": collection})
    letti = []

    async def importa(_db, _content, filename, **_kwargs):
        letti.append(filename)
        return {"status": "duplicate", "associato": False}

    monkeypatch.setattr(mod, "importa_pdf_bonifico", importa)
    for doc in collection.metadata:
        doc["source_file"] = doc["_id"]
    asyncio.run(mod.riprocessa_bonifici_pendenti(db, limit=2))

    assert letti == ["medio", "nuovo_mai_riletto"]
