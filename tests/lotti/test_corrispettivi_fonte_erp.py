import asyncio
from datetime import date
from unittest.mock import AsyncMock
from mongomock_motor import AsyncMongoMockClient
from app.database import Database
from app.lotti.routers import corrispettivi


def test_erp_source_deduplicates_and_preserves_zero(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()['erp']
        monkeypatch.setattr(Database, 'get_db', classmethod(lambda cls: db))
        await db.corrispettivi.insert_many([
            {'id': 'a', 'data': '2026-10-01', 'totale': 100, 'corrispettivo_key': 'day1'},
            {'id': 'copy', 'data': '2026-10-01', 'totale': 100, 'corrispettivo_key': 'day1'},
            {'id': 'zero', 'data': '2026-10-02', 'totale': 0},
            {'id': 'gone', 'data': '2026-10-03', 'totale': 999, 'entity_status': 'deleted'},
        ])
        values = await corrispettivi._serie('data', 'totale', date(2026, 10, 1), date(2026, 10, 3))
        assert values == {'2026-10-01': 100, '2026-10-02': 0}
        assert await corrispettivi._campi_rilevati() == ('data', 'totale')
    asyncio.run(scenario())


def test_import_delegates_canonical_erp_writer(monkeypatch):
    import app.routers.invoices.corrispettivi as erp
    writer = AsyncMock(return_value={'imported': 1, 'skipped': 1})
    monkeypatch.setattr(erp, 'upload_corrispettivi_xml_bulk', writer)
    result = asyncio.run(corrispettivi.importa_xml(files=['a', 'copy'], _admin=True))
    assert result['importati'] == 1 and result['duplicati'] == 1
    writer.assert_awaited_once_with(files=['a', 'copy'], force_update=False)
