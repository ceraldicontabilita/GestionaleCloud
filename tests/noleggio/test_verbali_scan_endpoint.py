import asyncio

from app.routers import verbali_riconciliazione as router_module
from app.services import verbali_gmail_scanner


def test_endpoint_attendibili_usa_solo_scanner_canonico(monkeypatch):
    fake_db = object()
    monkeypatch.setattr(router_module.Database, "get_db", lambda: fake_db)
    calls = []

    async def fake_scan(db, days_back, mark_as_read):
        calls.append((db, days_back, mark_as_read))
        return {"email_match": 2, "documenti_nuovi": 2}

    monkeypatch.setattr(verbali_gmail_scanner, "scan_gmail_verbali", fake_scan)
    result = asyncio.run(router_module.scan_gmail_mittenti_attendibili(
        days_back=30, _admin={"role": "admin"}
    ))

    assert result == {"email_match": 2, "documenti_nuovi": 2}
    assert calls == [(fake_db, 30, False)]
