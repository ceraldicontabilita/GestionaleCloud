import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.services.email_monitor_service import allinea_status_documenti_processati


class _Documents:
    def __init__(self):
        self.calls = []

    async def update_many(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(modified_count=3789)


class _Db:
    def __init__(self):
        self.documents = _Documents()

    def __getitem__(self, name):
        assert name == "documents_inbox"
        return self.documents


def test_allinea_badge_documenti_processati_e_idempotente():
    db = _Db()

    aggiornati = asyncio.run(allinea_status_documenti_processati(db))

    assert aggiornati == 3789
    query, update = db.documents.calls[0]
    assert query["$or"] == [{"processed": True}, {"xml_processed": True}]
    assert query["status"]["$in"] == ["nuovo", "da_processare", None]
    assert update == {"$set": {"status": "processato"}}


def test_riallineamento_badge_non_blocca_startup_ed_e_protetto_da_lease():
    source = Path("app/main.py").read_text(encoding="utf-8")

    assert "badge_alignment_task = asyncio.create_task(" in source
    assert 'lease_factory("startup_allinea_badge_documenti")' in source
    assert "await badge_alignment_task" in source
