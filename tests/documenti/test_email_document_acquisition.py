"""La scansione email conserva revisioni e riprende salvataggi interrotti."""
import asyncio
import base64
import hashlib
import imaplib
from email.message import EmailMessage
import sys
from types import ModuleType, SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import email_document_downloader as downloader_mod

_REAL_EMAIL_DOWNLOADER = downloader_mod.EmailDocumentDownloader


def _document(document_id, content, *, filename="F24_settembre_2026.pdf"):
    return {
        "id": document_id,
        "filename": filename,
        "category": "f24",
        "category_label": "F24",
        "file_hash": hashlib.md5(content, usedforsecurity=False).hexdigest(),
        "pdf_data": base64.b64encode(content).decode("ascii"),
        "size_bytes": len(content),
        "identificatore_periodo": "2026-09",
        "email_subject": "Modello F24 settembre 2026",
        "email_from": "test@example.invalid",
    }


@pytest.fixture
def email_batch(monkeypatch):
    documents = []

    class FakeDownloader:
        def __init__(self, *_args):
            self.connection = SimpleNamespace(select=lambda _folder: None)

        def connect(self):
            return True

        def disconnect(self):
            pass

        def search_emails_with_attachments(self, **_kwargs):
            return [b"1"]

        def fetch_message_id(self, _email_id):
            return "<acquisition-test@example.invalid>"

        def download_attachments_from_email(self, _email_id, **_kwargs):
            return [dict(doc) for doc in documents]

    async def propagate_event(*_args, **_kwargs):
        return None

    async def process_document_with_ai(**_kwargs):
        return {"success": False}

    events = ModuleType("app.services.event_bus")
    events.EventTypes = SimpleNamespace(DOCUMENTO_ACQUISITO="documento.acquisito")
    events.propagate_event = propagate_event
    ai = ModuleType("app.services.ai_integration_service")
    ai.process_document_with_ai = process_document_with_ai
    monkeypatch.setitem(sys.modules, events.__name__, events)
    monkeypatch.setitem(sys.modules, ai.__name__, ai)
    monkeypatch.setattr(downloader_mod, "EmailDocumentDownloader", FakeDownloader)
    return documents


async def _download(db, **kwargs):
    return await downloader_mod.download_documents_from_email(
        db, "test@example.invalid", "unused-offline-password", **kwargs,
    )


def test_same_name_period_and_size_do_not_discard_different_content(email_batch):
    db = AsyncMongoMockClient()["email_acquisition"]
    original = _document("original", b"%PDF-F24-1000.00-2026-09-%%EOF")
    revision = _document("revision", b"%PDF-F24-2000.00-2026-09-%%EOF")
    assert original["size_bytes"] == revision["size_bytes"]
    assert original["file_hash"] != revision["file_hash"]
    email_batch.append(revision)

    async def scenario():
        await db["documents_inbox"].insert_one(original)
        result = await _download(db)
        return result, await db["documents_inbox"].count_documents({})

    result, count = asyncio.run(scenario())
    assert result["stats"]["new_documents"] == 1
    assert result["stats"]["period_duplicates"] == 0
    assert count == 2


def test_failed_second_attachment_is_retried_without_duplicating_first(email_batch, monkeypatch):
    db = AsyncMongoMockClient()["email_acquisition"]
    email_batch.extend([
        _document("first", b"%PDF-F24-first-%%EOF", filename="F24_primo.pdf"),
        _document("second", b"%PDF-F24-second-%%EOF", filename="F24_secondo.pdf"),
    ])
    collection = db["documents_inbox"]
    original_insert = collection.insert_one
    failed = False

    async def fail_second_once(document):
        nonlocal failed
        if document["id"] == "second" and not failed:
            failed = True
            raise RuntimeError("offline simulated persistence failure")
        return await original_insert(document)

    monkeypatch.setattr(collection, "insert_one", fail_second_once)

    class DbWithFailingInbox:
        def __getitem__(self, name):
            return collection if name == "documents_inbox" else db[name]

    retry_db = DbWithFailingInbox()

    async def scenario():
        with pytest.raises(RuntimeError, match="simulated persistence failure"):
            await _download(retry_db)
        before_retry = await db["email_message_index"].count_documents({})
        result = await _download(retry_db)
        return before_retry, result, await collection.count_documents({})

    indexed, result, count = asyncio.run(scenario())
    assert indexed == 0
    assert result["stats"]["skipped_by_dict"] == 0
    assert result["stats"]["duplicates_skipped"] == 1
    assert result["stats"]["new_documents"] == 1
    assert count == 2


def test_identical_bytes_under_different_name_are_skipped(email_batch):
    db = AsyncMongoMockClient()["email_acquisition"]
    content = b"%PDF-F24-same-content-%%EOF"
    original = _document("original", content, filename="F24_originale.pdf")
    email_batch.append(_document("copy", content, filename="F24_copia.pdf"))

    async def scenario():
        await db["documents_inbox"].insert_one(original)
        result = await _download(db)
        indexed = await db["email_message_index"].count_documents({})
        return result, indexed, await db["documents_inbox"].count_documents({})

    result, indexed, count = asyncio.run(scenario())
    assert result["stats"]["new_documents"] == 0
    assert result["stats"]["duplicates_skipped"] == 1
    assert indexed == 1
    assert count == 1


def test_md5_candidate_requires_same_original_content(email_batch):
    db = AsyncMongoMockClient()["email_acquisition"]
    original = _document("original", b"%PDF-original-different-%%EOF")
    new = _document("new", b"%PDF-new-document-%%EOF", filename="F24_nuovo.pdf")
    original["file_hash"] = new["file_hash"]  # Simula un indice legacy incoerente.
    email_batch.append(new)

    async def scenario():
        await db["documents_inbox"].insert_one(original)
        first = await _download(db)
        retry = await _download(db, ignore_dict=True)
        return first, retry, await db["documents_inbox"].count_documents({})

    first, retry, count = asyncio.run(scenario())
    assert first["stats"]["new_documents"] == 1
    assert retry["stats"]["new_documents"] == 0
    assert retry["stats"]["duplicates_skipped"] == 1
    assert count == 2


def test_ignored_non_administrative_attachment_is_not_rescanned(email_batch):
    db = AsyncMongoMockClient()["email_acquisition"]
    photo = _document("photo", b"%PDF-photo-%%EOF", filename="foto.pdf")
    photo["category"] = "altro"
    email_batch.append(photo)

    async def scenario():
        first = await _download(db)
        second = await _download(db)
        return first, second, await db["documents_inbox"].count_documents({})

    first, second, count = asyncio.run(scenario())
    assert first["stats"]["documents_ignored_not_relevant"] == 1
    assert second["stats"]["skipped_by_dict"] == 1
    assert count == 0


def test_same_content_from_other_email_channel_is_not_reinserted(email_batch):
    db = AsyncMongoMockClient()["email_acquisition"]
    content = b"%PDF-F24-other-channel-%%EOF"
    copy = _document("copy", content)
    email_batch.append(copy)

    async def scenario():
        await db["f24_email_attachments"].insert_one({
            "id": "original",
            "pdf_hash": copy["file_hash"],
            "pdf_sha256": hashlib.sha256(content).hexdigest(),
        })
        result = await _download(db)
        return result, await db["documents_inbox"].count_documents({})

    result, count = asyncio.run(scenario())
    assert result["stats"]["duplicates_skipped"] == 1
    assert result["stats"]["new_documents"] == 0
    assert count == 0


def _install_real_fetch_downloader(monkeypatch, fetch):
    class FetchDownloader(_REAL_EMAIL_DOWNLOADER):
        def __init__(self, *_args):
            self.connection = SimpleNamespace(select=lambda _folder: None, fetch=fetch)

        def connect(self):
            return True

        def disconnect(self):
            pass

        def search_emails_with_attachments(self, **_kwargs):
            return [b"1"]

        def fetch_message_id(self, _email_id):
            return "<fetch-test@example.invalid>"

    monkeypatch.setattr(downloader_mod, "EmailDocumentDownloader", FetchDownloader)
    monkeypatch.setattr(downloader_mod, "extract_document_period", lambda *_: None)


def _email_with_f24():
    message = EmailMessage()
    message["Subject"] = "F24 settembre"
    message["Message-ID"] = "<fetch-test@example.invalid>"
    message.add_attachment(
        b"%PDF-F24-import-%%EOF", maintype="application", subtype="pdf", filename="F24.pdf",
    )
    return message


@pytest.mark.parametrize("failure", ["NO", "exception"])
def test_imap_fetch_failure_does_not_confirm_message_and_can_retry(email_batch, monkeypatch, failure):
    db = AsyncMongoMockClient()["email_acquisition"]
    attempts = 0
    message = _email_with_f24()

    def fetch(*_args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if failure == "exception":
                raise imaplib.IMAP4.abort("offline interrupted fetch")
            return "NO", [b"offline rejected fetch"]
        return "OK", [(b"RFC822", message.as_bytes())]

    _install_real_fetch_downloader(monkeypatch, fetch)

    async def scenario():
        with pytest.raises((RuntimeError, imaplib.IMAP4.abort)):
            await _download(db)
        indexed = await db["email_message_index"].count_documents({})
        retry = await _download(db)
        return indexed, retry

    indexed, retry = asyncio.run(scenario())
    assert indexed == 0
    assert retry["stats"]["skipped_by_dict"] == 0
    assert retry["stats"]["new_documents"] == 1


def test_partial_attachment_parsing_failure_does_not_confirm_message(email_batch, monkeypatch):
    db = AsyncMongoMockClient()["email_acquisition"]
    message = _email_with_f24()
    attachment = next(message.iter_attachments())

    class BrokenAttachment:
        def get_content_maintype(self):
            return "application"

        def get_filename(self):
            raise ValueError("offline attachment decode error")

    monkeypatch.setattr(message, "walk", lambda: iter([attachment, BrokenAttachment()]))
    monkeypatch.setattr(downloader_mod.email, "message_from_bytes", lambda *_: message)
    _install_real_fetch_downloader(monkeypatch, lambda *_: ("OK", [(b"RFC822", b"offline-message")]))

    async def scenario():
        with pytest.raises(ValueError, match="attachment decode error"):
            await _download(db)
        return (await db["email_message_index"].count_documents({}),
                await db["documents_inbox"].count_documents({}))

    assert asyncio.run(scenario()) == (0, 0)
