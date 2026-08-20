"""
Upload manuale documenti fiscali (dichiarazione IVA, cartelle esattoriali,
avvisi bonari): carichi un PDF → ottieni un ID → il file è memorizzato in
documents_inbox e recuperabile/scaricabile.
"""
import asyncio
import base64
import hashlib

import pytest

from app.routers import documenti_fiscali as df
from app.database import Database


class _FakeInbox:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if "file_hash" in query and d.get("file_hash") == query["file_hash"]:
                return d
            if "sha256" in query and d.get("sha256") == query["sha256"]:
                return d
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)

    def find(self, query, proj=None):
        docs = self.docs
        cat = query.get("category")
        if isinstance(cat, str):
            docs = [d for d in docs if d.get("category") == cat]
        elif isinstance(cat, dict) and "$in" in cat:
            docs = [d for d in docs if d.get("category") in cat["$in"]]

        class _Cur:
            def __init__(self, items):
                self.items = items

            def sort(self, *a, **k):
                return self

            async def to_list(self, n):
                return [dict(x) for x in self.items[:n]]

        return _Cur(docs)


class _FakeDb:
    def __init__(self, inbox):
        self._inbox = inbox

    def __getitem__(self, name):
        assert name == "documents_inbox"
        return self._inbox


class _FakeUpload:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def fake_db(monkeypatch):
    inbox = _FakeInbox()
    db = _FakeDb(inbox)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    class _FakeIngestion:
        def __init__(self, _db): self.db = _db
        async def ingest(self, *, content, filename, source, category_hint, source_metadata, **_kwargs):
            digest = hashlib.sha256(content).hexdigest()
            existing = await inbox.find_one({"sha256": digest})
            if existing:
                return {"status": "duplicate", "document_id": existing["fiscal_document_id"],
                        "version_id": existing["fiscal_version_id"], "sha256": digest}
            doc_id = f"doc-{len(inbox.docs) + 1}"
            fiscal_id = f"fiscal-{len(inbox.docs) + 1}"
            await inbox.insert_one({"id": doc_id, "company_id": df.settings.FISCAL_COMPANY_ID,
                                    "filename": filename, "pdf_data": base64.b64encode(content).decode(),
                                    "sha256": digest, "file_hash": digest, "category": category_hint,
                                    "periodo": source_metadata.get("periodo") if isinstance(source_metadata.get("periodo"), str) else None,
                                    "fiscal_document_id": fiscal_id, "fiscal_version_id": f"version-{fiscal_id}",
                                    "created_at": "2026-08-10T00:00:00Z"})
            return {"status": "inserted", "document_id": fiscal_id,
                    "version_id": f"version-{fiscal_id}", "inbox_id": doc_id, "sha256": digest}

    from app.services import drive_declaration_upload
    uploaded = {}
    def _fake_drive_upload(*, content, filename, category, filing_year, note=None):
        digest = hashlib.sha256(content).hexdigest()
        duplicate = digest in uploaded
        document_id = uploaded.setdefault(digest, f"drive-{len(uploaded) + 1}")
        return {"success": True, "duplicate": duplicate, "document_id": document_id,
                "sha256": digest, "drive_path": f"01_DICHIARAZIONI_FISCALI/{filing_year}/{filename}",
                "drive_url": f"https://drive.google.com/open?id={document_id}"}
    monkeypatch.setattr(drive_declaration_upload, "upload_declaration", _fake_drive_upload)
    return db, inbox


def test_upload_categoria_non_valida(fake_db):
    from fastapi import HTTPException
    up = _FakeUpload("x.pdf", b"%PDF-1.4 test")
    with pytest.raises(HTTPException) as ei:
        _run(df.upload_documento_fiscale(file=up, categoria="pippo"))
    assert ei.value.status_code == 400


def test_upload_solo_pdf(fake_db):
    from fastapi import HTTPException
    up = _FakeUpload("x.txt", b"ciao")
    with pytest.raises(HTTPException) as ei:
        _run(df.upload_documento_fiscale(file=up, categoria="dichiarazione_iva"))
    assert ei.value.status_code == 400


def test_upload_dichiarazione_iva_ok(fake_db):
    _db, inbox = fake_db
    up = _FakeUpload("dichiarazione_iva_2025.pdf", b"%PDF-1.4 contenuto")
    res = _run(df.upload_documento_fiscale(file=up, categoria="dichiarazione_iva", periodo="2025"))
    assert res["success"] and not res["duplicate"]
    assert res["storage"] == "google_drive"
    assert res["drive_url"].startswith("https://drive.google.com/")
    assert len(inbox.docs) == 0


def test_upload_dedup_stesso_file(fake_db):
    _db, inbox = fake_db
    up1 = _FakeUpload("a.pdf", b"%PDF-1.4 stesso")
    r1 = _run(df.upload_documento_fiscale(file=up1, categoria="avviso_bonario", periodo="2026"))
    up2 = _FakeUpload("b.pdf", b"%PDF-1.4 stesso")  # stesso contenuto, nome diverso
    r2 = _run(df.upload_documento_fiscale(file=up2, categoria="avviso_bonario", periodo="2026"))
    assert r2["duplicate"] is True
    assert r2["document_id"] == r1["document_id"]
    assert len(inbox.docs) == 0  # nessuna copia Mongo


def test_lista_filtra_per_categoria(fake_db):
    _db, inbox = fake_db
    _run(inbox.insert_one({"id": "legacy-iva", "company_id": df.settings.FISCAL_COMPANY_ID,
        "filename": "iva.pdf", "category": "dichiarazione_iva"}))
    _run(inbox.insert_one({"id": "legacy-cart", "company_id": df.settings.FISCAL_COMPANY_ID,
        "filename": "cart.pdf", "category": "cartella_esattoriale"}))
    res = _run(df.lista_documenti_fiscali(categoria="dichiarazione_iva", limit=200))
    assert res["totale"] == 1
    assert res["documenti"][0]["category"] == "dichiarazione_iva"
    assert res["documenti"][0]["download_url"].endswith("/download")
    # senza filtro: entrambe
    tutti = _run(df.lista_documenti_fiscali(categoria=None, limit=200))
    assert tutti["totale"] == 2
