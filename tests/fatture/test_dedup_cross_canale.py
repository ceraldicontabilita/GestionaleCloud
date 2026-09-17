"""Test del dedup cross-canale documenti (P2-1): la stessa impronta md5 viene
riconosciuta sia nelle collezioni *_email_attachments (campo pdf_hash) sia in
documents_inbox (campo file_hash)."""
import asyncio

from app.services.deduplica import esiste_documento_cross_canale


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items() if not k.startswith("_")):
                return dict(d)
        return None


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_trova_in_documents_inbox():
    db = _Db()
    db["documents_inbox"].docs = [{"file_hash": "ABC", "id": "d1"}]
    r = _run(esiste_documento_cross_canale(db, "ABC"))
    assert r == {"collezione": "documents_inbox", "campo": "file_hash"}


def test_trova_in_email_attachments():
    db = _Db()
    db["f24_email_attachments"].docs = [{"pdf_hash": "XYZ", "id": "a1"}]
    r = _run(esiste_documento_cross_canale(db, "XYZ"))
    assert r["collezione"] == "f24_email_attachments" and r["campo"] == "pdf_hash"


def test_escludi_collezione_di_partenza():
    # Se sto per inserire in documents_inbox, non deve auto-rilevarsi lì.
    db = _Db()
    db["documents_inbox"].docs = [{"file_hash": "ABC", "id": "d1"}]
    r = _run(esiste_documento_cross_canale(db, "ABC", escludi_collezione="documents_inbox"))
    assert r is None


def test_impronta_assente():
    db = _Db()
    assert _run(esiste_documento_cross_canale(db, "NOPE")) is None
    assert _run(esiste_documento_cross_canale(db, "")) is None
