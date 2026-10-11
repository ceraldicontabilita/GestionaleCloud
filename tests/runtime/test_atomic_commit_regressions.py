"""Concorrenza, rollback e letture limitate del registro autorevole."""
import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from app.services.supabase_runtime_database import ConcurrentDocumentChange
from tests.runtime.test_supabase_runtime_database import FakeRestSupabase
from tests.runtime.test_supabase_runtime_cache import CachingFakeSupabase


class ConcurrentRuntime(FakeRestSupabase):
    def __init__(self, remote, barrier):
        super().__init__()
        self.remote = remote
        self.barrier = barrier
        self.waited = False

    async def _rpc(self, name, payload):
        result = copy.deepcopy(await super()._rpc(name, payload))
        if name == 'gc_fetch_documents_exact' and not self.waited:
            self.waited = True
            await self.barrier.wait()
        return result


@pytest.mark.parametrize('claim', [False, True])
def test_due_processi_non_perdono_incrementi_e_non_prendono_la_stessa_claim(claim):
    async def scenario():
        remote = {'invoices': {'i': {'_id': 'i', 'counter': 0}}}
        barrier = asyncio.Barrier(2)
        workers = [ConcurrentRuntime(remote, barrier) for _ in range(2)]
        selector = {'_id': 'i', **({'claim': {'$exists': False}} if claim else {})}
        update = {'$set': {'claim': 'presa'}} if claim else {'$inc': {'counter': 1}}
        results = await asyncio.gather(*[
            db['invoices'].find_one_and_update(selector, update, return_document=True) for db in workers
        ])
        if claim:
            assert sum(r is not None for r in results) == 1
        else:
            assert remote['invoices']['i']['counter'] == 2
    asyncio.run(scenario())


def test_transazione_isolata_annulla_tutte_le_scritture_e_consente_riprova():
    async def scenario():
        db = FakeRestSupabase({'fornitori': [{'_id': 's', 'nome': 'prima'}]})
        with pytest.raises(ValueError):
            async with db.transaction():
                await db['fornitori'].update_one({'_id': 's'}, {'$set': {'nome': 'dopo'}})
                await db['invoices'].insert_one({'_id': 'i', 'totale': 100})
                assert (await db['fornitori'].find_one({'_id': 's'}))['nome'] == 'dopo'
                assert await db['invoices'].find_one({'_id': 'i'})
                # Un'altra richiesta non vede ancora nessuna scrittura.
                async def altra_richiesta():
                    assert await db['invoices'].find_one({'_id': 'i'}) is None
                await asyncio.create_task(altra_richiesta())
                raise ValueError('errore dopo fattura')
        assert db.remote['fornitori']['s']['nome'] == 'prima'
        assert not db.remote.get('invoices')
        async with db.transaction():
            await db['invoices'].insert_one({'_id': 'i', 'totale': 100})
            await db['invoices'].update_one({'_id': 'i'}, {'$inc': {'totale': 10}})
        assert db.remote['invoices']['i']['totale'] == 110
    asyncio.run(scenario())


def test_conflitto_al_commit_non_salva_le_altre_collezioni():
    async def scenario():
        db = FakeRestSupabase({'fornitori': [{'_id': 's', 'n': 0}]})
        with pytest.raises(ConcurrentDocumentChange):
            async with db.transaction():
                await db['fornitori'].update_one({'_id': 's'}, {'$inc': {'n': 1}})
                await db['invoices'].insert_one({'_id': 'i'})
                db.remote['fornitori']['s']['n'] = 9
        assert db.remote['fornitori']['s']['n'] == 9
        assert not db.remote.get('invoices')
    asyncio.run(scenario())


@pytest.mark.parametrize('exact', [False, True])
def test_sort_skip_limit_precedono_il_download_dei_pdf(monkeypatch, exact):
    db = CachingFakeSupabase({'invoices': [
        {'_id': str(i), 'id': str(i), 'rank': i, 'status': 'imported'} for i in range(600)
    ]})
    hydrated = []
    async def hydrate(collection, docs, excluded=None):
        hydrated.extend(d['_id'] for d in docs)
        return docs
    monkeypatch.setattr('app.services.pdf_drive_only.hydrate_documents', hydrate)
    async def scenario():
        selector = {'id': {'$in': [str(i) for i in range(300)]}} if exact else {'status': 'imported'}
        result = await db['invoices'].find(selector).sort('rank', -1).skip(2).limit(4).to_list(1)
        assert len(result) == 1
        assert result[0]['rank'] == (297 if exact else 597)
        assert hydrated == [str(result[0]['rank'])]
    asyncio.run(scenario())


def test_fattura_import_fallito_non_diventa_duplicato(monkeypatch):
    from app.routers.invoices.fatture_upload import process_fattura_to_db
    db = FakeRestSupabase()
    parsed = {'supplier_vat': '12345678900', 'supplier_name': 'Prova', 'invoice_number': 'T1',
              'invoice_date': '2026-01-01', 'total_amount': 100, 'tipo_documento': 'TD01'}
    async def supplier(db, *args, **kwargs):
        await db['fornitori'].insert_one({'_id': 's', 'id': 's'})
        return {'supplier_id': 's', 'metodo_pagamento': 'banca'}
    monkeypatch.setattr('app.routers.invoices.fatture_upload.ensure_supplier_exists', supplier)
    failure = AsyncMock(side_effect=RuntimeError('errore successivo alla fattura'))
    monkeypatch.setattr('app.services.assegni_fattura_intent.collega_intento_assegno_a_fattura', failure)
    async def scenario():
        for _ in range(2):
            with pytest.raises(RuntimeError, match='errore successivo'):
                await process_fattura_to_db(db, parsed, xml_raw='<test/>')
            assert not db.remote.get('fornitori')
            assert not db.remote.get('invoices')
        assert failure.await_count == 2
    asyncio.run(scenario())
