"""Test del dedup cross-canale documenti (P2-1): lo stesso file viene
riconosciuto sia nelle collezioni *_email_attachments (campo pdf_hash) sia in
documents_inbox (campo file_hash). L'MD5 salvato fa solo da prefiltro: decide
lo SHA-256 del contenuto (salvato sul record o ricalcolato dal PDF salvato)."""
import asyncio
import base64
import hashlib

from app.services.deduplica import esiste_documento_cross_canale

PDF = b"%PDF-1.4 documento vero"
MD5 = hashlib.md5(PDF).hexdigest()
SHA = hashlib.sha256(PDF).hexdigest()


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items() if not k.startswith("_")):
                return dict(d)
        return None

    def find(self, query, proj=None):
        async def matching_documents():
            for doc in self.docs:
                if all(doc.get(key) == value for key, value in query.items()):
                    yield {key: doc[key] for key, included in (proj or {}).items()
                           if included and key in doc} if proj else dict(doc)
        return matching_documents()


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


def test_trova_in_documents_inbox_confermato_dal_pdf_salvato():
    db = _Db()
    db["documents_inbox"].docs = [{
        "file_hash": MD5, "id": "d1", "pdf_data": base64.b64encode(PDF).decode(),
    }]
    r = _run(esiste_documento_cross_canale(db, MD5, contenuto=PDF))
    assert r == {"collezione": "documents_inbox", "campo": "file_hash", "sha256": SHA, "id": "d1"}


def test_trova_in_email_attachments_con_sha256_salvato():
    db = _Db()
    db["f24_email_attachments"].docs = [{"pdf_hash": MD5, "id": "a1", "sha256": SHA}]
    r = _run(esiste_documento_cross_canale(db, MD5, contenuto=PDF))
    assert r["collezione"] == "f24_email_attachments" and r["campo"] == "pdf_hash"


def test_md5_uguale_ma_sha256_diverso_non_e_doppione():
    # L'MD5 non decide: un record con lo stesso MD5 ma altro SHA-256 (o altri
    # byte) non e' lo stesso file.
    db = _Db()
    db["documents_inbox"].docs = [{"file_hash": MD5, "id": "d1", "sha256": "0" * 64}]
    db["f24_email_attachments"].docs = [{
        "pdf_hash": MD5, "id": "a1", "pdf_data": base64.b64encode(b"altri byte").decode(),
    }]
    assert _run(esiste_documento_cross_canale(db, MD5, contenuto=PDF)) is None


def test_solo_md5_senza_contenuto_non_basta():
    db = _Db()
    db["documents_inbox"].docs = [{"file_hash": MD5, "id": "d1", "sha256": SHA}]
    assert _run(esiste_documento_cross_canale(db, MD5)) is None
    # Un record con il solo MD5, senza SHA-256 ne' PDF, non si puo' confermare.
    db["documents_inbox"].docs = [{"file_hash": MD5, "id": "d1"}]
    assert _run(esiste_documento_cross_canale(db, MD5, contenuto=PDF)) is None


def test_escludi_collezione_di_partenza():
    # Se sto per inserire in documents_inbox, non deve auto-rilevarsi lì.
    db = _Db()
    db["documents_inbox"].docs = [{"file_hash": MD5, "id": "d1", "sha256": SHA}]
    r = _run(esiste_documento_cross_canale(db, MD5, escludi_collezione="documents_inbox",
                                           contenuto=PDF))
    assert r is None


def test_impronta_assente():
    db = _Db()
    assert _run(esiste_documento_cross_canale(db, "NOPE", contenuto=PDF)) is None
    assert _run(esiste_documento_cross_canale(db, "", contenuto=PDF)) is None
