"""Regressioni delle pagine segnalate: verifica di risposte e dati salvati."""
import asyncio
import base64
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httplib2
import pytest
from fastapi import FastAPI
from googleapiclient.errors import HttpError
from httpx import ASGITransport, AsyncClient

from app.services.archivio_documenti_memoria import ArchivioDocumenti


def test_rotte_statiche_raggiungono_le_funzioni_corrette(monkeypatch):
    from app.hr.database import Database
    from app.hr.routers import turni, portale_documenti, cedolini
    from app.lotti.routers import anomalie
    db = ArchivioDocumenti('test')
    app = FastAPI()
    for module, prefix in [(turni, '/turni'), (portale_documenti, '/documenti'), (cedolini, '/cedolini'), (anomalie, '')]:
        app.include_router(module.router, prefix=prefix)
        if hasattr(module, 'get_identity'):
            app.dependency_overrides[module.get_identity] = lambda: {'id': 'test', 'role': 'admin'}
    monkeypatch.setattr(Database, 'get_db', lambda: db)
    monkeypatch.setattr(anomalie, 'db', db)
    async def scenario():
        await db[portale_documenti.COLL_TEMPLATES].insert_one({
            'id': 'r', 'tipo': 'regolamento', 'filename': 'regolamento.docx',
            'file_data': base64.b64encode(b'regolamento di test').decode()})
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            for url in ['/turni/disponibilita-bar', '/turni/preferenza-riposo',
                        '/cedolini/simulazione-f24?anno=2026&mese=1',
                        '/anomalie/report-pdf-range?start_anno=2025&end_anno=2026']:
                response = await client.get(url)
                assert response.status_code == 200, (url, response.text)
            response = await client.get('/documenti/regolamento/file')
            assert response.status_code == 200
            assert response.content == b'regolamento di test'
    asyncio.run(scenario())


def test_diagnostica_usa_ping_del_database_hr(monkeypatch):
    from app.hr.routers import diagnostica
    db = ArchivioDocumenti('test')
    db.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(diagnostica.Database, 'get_db', lambda: db)
    result = asyncio.run(diagnostica.diagnostica())
    check = next(c for c in result['checks'] if c['area'] == 'Database')
    assert check['stato'] == 'ok'
    db.ping.assert_awaited_once()


@pytest.mark.parametrize('status', ['429', '503'])
def test_atti_usano_archivio_persistito_quando_drive_non_risponde(monkeypatch, status):
    from app.routers import documenti
    db = ArchivioDocumenti('test')
    db['documents_inbox']._documents = [{'_id': 't', 'id': 't', 'category': 'tari_avviso', 'filename': 'avviso.pdf'}]
    error = HttpError(httplib2.Response({'status': status}), b'{"error":{"message":"temporaneo"}}')
    def failing(**kwargs):
        raise error
    monkeypatch.setattr('app.services.drive_document_index.list_administrative_documents', failing)
    monkeypatch.setattr(documenti.Database, 'get_db', lambda: db)
    result = asyncio.run(documenti.lista_atti_amministrativi(area=None, anno=None, search=None, review_only=False, limit=200))
    assert result['total'] == 1
    assert result['items'][0]['id'] == 't'


@pytest.mark.parametrize('method', ['', None, 'banca'])
def test_salvare_email_non_avvia_riparazione_contabile(monkeypatch, method):
    from app.routers.suppliers_module import base
    db = ArchivioDocumenti('test')
    db['fornitori']._documents = [{'_id': 's', 'id': 's', 'partita_iva': '12345678900',
                                  'metodo_pagamento': method, 'metodo_pagamento_dal': '2025-01-01'}]
    repair = AsyncMock(return_value={})
    history = AsyncMock()
    monkeypatch.setattr(base.Database, 'get_db', lambda: db)
    monkeypatch.setattr('app.routers.prima_nota_module.manutenzione.ripristina_provvisori_metodo_errato', repair)
    monkeypatch.setattr('app.utils.iva_calculator.save_supplier_payment_method', history)
    monkeypatch.setattr('app.services.event_bus.propagate_event', AsyncMock())
    monkeypatch.setattr(base, 'carica_decisioni', AsyncMock(return_value=None))
    monkeypatch.setattr(base, 'vista_scheda', lambda *args: {})
    async def scenario():
        await base.update_supplier('s', {'email': 'nuova@example.test', 'metodo_pagamento': method,
                                        'metodo_pagamento_dal': '2025-01-01'})
        await asyncio.sleep(0)
        supplier = await db['fornitori'].find_one({'id': 's'})
        assert supplier['email'] == 'nuova@example.test'
        assert supplier['metodo_pagamento'] == method
        repair.assert_not_awaited()
        history.assert_not_awaited()
    asyncio.run(scenario())


def test_ripristino_limitato_al_fornitore_e_alla_decorrenza(monkeypatch):
    from app.routers.prima_nota_module import manutenzione as module
    db = ArchivioDocumenti('test')
    db['fornitori']._documents = [{'_id': 's', 'id': 's', 'partita_iva': '12345678900'}]
    db['invoices']._documents = [
        {'_id': 'i1', 'id': 'i1', 'supplier_vat': '12345678900', 'invoice_date': '2026-06-01'},
        {'_id': 'i2', 'id': 'i2', 'supplier_vat': '12345678900', 'invoice_date': '2026-01-01'},
        {'_id': 'i3', 'id': 'i3', 'supplier_vat': '98765432100', 'invoice_date': '2026-06-01'},
    ]
    cassa = db[module.COLLECTION_PRIMA_NOTA_CASSA]
    cassa._documents = [{'_id': f'm{n}', 'id': f'm{n}', 'fattura_id': f'i{n}',
                         'tipo': 'uscita', 'importo': 100, 'source': 'auto_conferma',
                         'data': '2026-06-02', 'status': 'active'} for n in range(1, 4)]
    monkeypatch.setattr(module.Database, 'get_db', lambda: db)
    monkeypatch.setattr('app.routers.prima_nota_module.sync.mappa_fornitori_per_piva',
                        AsyncMock(return_value=({'12345678900': 'banca', '98765432100': 'banca'}, set())))
    async def scenario():
        await module.ripristina_provvisori_metodo_errato(
            dry_run=False, anno=2026, banca_non_riconciliate=False, fornitore_id='s', dal='2026-05-01')
        assert (await cassa.find_one({'id': 'm1'}))['status'] == 'deleted'
        assert (await cassa.find_one({'id': 'm2'}))['status'] == 'active'
        assert (await cassa.find_one({'id': 'm3'}))['status'] == 'active'
    asyncio.run(scenario())


def test_query_allergeni_non_blocca_le_altre_richieste(monkeypatch):
    from app.menu.routes import allergeni_routes as module
    entered, release = threading.Event(), threading.Event()
    class Query:
        def select(self, *args): return self
        def is_(self, *args): return self
        def execute(self):
            entered.set()
            assert release.wait(2), 'query bloccata sul loop della richiesta'
            return SimpleNamespace(data=[])
    monkeypatch.setattr(module, 'supabase', SimpleNamespace(table=lambda *args: Query()))
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.verify_token] = lambda: 'admin'
    async def scenario():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            task = asyncio.create_task(client.get('/api/admin/allergeni/mancanti'))
            assert await asyncio.to_thread(entered.wait, 1)
            release.set()
            response = await task
            assert response.status_code == 200, response.text
            assert response.json()['prodotti'] == []
    asyncio.run(scenario())
