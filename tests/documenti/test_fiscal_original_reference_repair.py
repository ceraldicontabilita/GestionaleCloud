import asyncio
import hashlib

import pytest
from mongomock_motor import AsyncMongoMockClient
from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService


def test_riaggancio_originale_verificato_idempotente_senza_cambiare_dati():
    async def scenario():
        db = AsyncMongoMockClient()['repair']
        service = FiscalDocumentIngestionService(db, company_id='azienda')
        content = b'%PDF-originale'
        await db.fiscal_documents.insert_one({'id':'doc','company_id':'azienda','current_version_id':'v',
            'quadri':{'credito':12345},'review_status':'DA_VERIFICARE','source_metadata':{'data_presentazione':'2026-09-27'}})
        await db.fiscal_document_versions.insert_one({'id':'v','document_id':'doc','company_id':'azienda',
            'sha256':hashlib.sha256(content).hexdigest()})
        for _ in range(2):
            assert await service.repair_original_reference(document_id='doc', content=content,drive_file_id='drive')
        row = await db.fiscal_documents.find_one({'id':'doc'})
        assert len(row['source_occurrences']) == 1
        assert row['quadri'] == {'credito':12345}
        assert row['review_status'] == 'DA_VERIFICARE'
        assert row['source_metadata'] == {'data_presentazione':'2026-09-27'}
        with pytest.raises(ValueError,match='SHA-256'):
            await service.repair_original_reference(document_id='doc',content=b'%PDF-altro',drive_file_id='altro')
        with pytest.raises(ValueError,match='contribuente'):
            await FiscalDocumentIngestionService(db,company_id='altra').repair_original_reference(
                document_id='doc',content=content,drive_file_id='drive')
        assert len((await db.fiscal_documents.find_one({'id':'doc'}))['source_occurrences']) == 1
        assert await db.fiscal_pages.count_documents({}) == 0
    asyncio.run(scenario())
