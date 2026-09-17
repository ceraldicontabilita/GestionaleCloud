import asyncio
from types import SimpleNamespace

import app.services.email_monitor_service as monitor


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        if upsert:
            merged = dict(query)
            merged.update(update.get("$setOnInsert", {}))
            merged.update(update.get("$set", {}))
            self.docs.append(merged)
        return SimpleNamespace(matched_count=0)


class _Db:
    def __init__(self):
        self.email_monitor_runs = _Coll()
        self.email_retry_queue = _Coll()
        self.email_delivery_log = _Coll()

    def __getitem__(self, name):
        if name == "email_monitor_runs":
            return self.email_monitor_runs
        if name == "email_retry_queue":
            return self.email_retry_queue
        if name == "email_delivery_log":
            return self.email_delivery_log
        raise KeyError(name)


def _run(coro):
    return asyncio.run(coro)


def test_start_and_finalize_email_monitor_run_persists_execution_metadata():
    db = _Db()
    run = _run(monitor.start_email_monitor_run(db, source="gmail_daily"))

    assert run["execution_id"]
    assert run["status"] == "running"
    assert run["source"] == "gmail_daily"

    final = _run(monitor.finalize_email_monitor_run(db, run["execution_id"], status="completed", counters={"new_documents": 2, "xml_processed": 1}))
    assert final["status"] == "completed"
    assert final["counters"]["new_documents"] == 2
    assert final["ended_at"]


def test_sync_email_documents_enqueues_retry_on_transient_errors(monkeypatch):
    db = _Db()

    async def _boom(*args, **kwargs):
        raise TimeoutError("IMAP timeout")

    monkeypatch.setattr(monitor, "_build_gmail_credentials", lambda *a, **k: ("user", "pass", "imap.gmail.com"))
    monkeypatch.setattr(monitor, "_load_allowed_gmail_patterns", lambda *a, **k: ["@example.com"])
    monkeypatch.setattr(monitor, "_download_email_batch", _boom)

    result = _run(monitor.sync_email_documents(db, giorni=1))

    assert result["success"] is False
    assert result["status"] == "transient_error"
    retry = _run(db["email_retry_queue"].find_one({"execution_id": result["execution_id"]}))
    assert retry is not None
    assert retry["retry_after_seconds"] > 0
