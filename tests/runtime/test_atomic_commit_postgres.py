"""Contratto SQL reale. GC_TEST_POSTGRES_DSN deve indicare un server locale isolato."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid

import asyncpg
import pytest

from tests.runtime.test_supabase_runtime_database import FakeRestSupabase


@pytest.mark.skipif(not os.getenv('GC_TEST_POSTGRES_DSN'), reason='richiede PostgreSQL locale isolato')
def test_commit_postgres_concorrenza_rollback_duplicati_e_autorizzazione():
    dsn = os.environ['GC_TEST_POSTGRES_DSN']
    assert urlparse(dsn).hostname in {'127.0.0.1', 'localhost', '::1'}
    async def scenario():
        admin = await asyncpg.connect(dsn)
        # Ruoli delle RPC Supabase, nel solo server locale della suite.
        for role in ('anon', 'authenticated', 'service_role'):
            if not await admin.fetchval('select exists(select 1 from pg_roles where rolname=$1)', role):
                await admin.execute(f'create role {role}')
        name = 'gc_test_' + uuid.uuid4().hex
        await admin.execute(f'create database {name}')
        pool = None
        try:
            pool = await asyncpg.create_pool(dsn, database=name, min_size=1, max_size=4)
            root = Path(__file__).resolve().parents[2]
            async with pool.acquire() as con:
                await con.execute('''create schema gestionale;
                    create table gestionale.documents(collection text, id text, data jsonb,
                    updated_at timestamptz not null default now(), primary key(collection,id));
                    create function public.gc_assert_runtime_secret() returns void language plpgsql as $$
                    begin if current_setting('test.runtime_secret',true) is distinct from 'test-secret'
                    then raise insufficient_privilege; end if; end $$;''')
                await con.execute((root/'supabase/migrations/20260903_idempotency_key.sql').read_text())
                await con.execute('''
                    create function gestionale.consenti_cancellazione() returns void language sql as $$
                      select set_config('gestionale.cancellazione_autorizzata', '1', true); $$;
                    create function gestionale.test_delete_guard() returns trigger language plpgsql as $$
                    begin
                      if current_setting('gestionale.cancellazione_autorizzata', true) is distinct from '1'
                      then raise exception 'delete non autorizzata'; end if;
                      return old;
                    end $$;
                    create trigger test_delete_guard before delete on gestionale.documents
                    for each row execute function gestionale.test_delete_guard();''')
                await con.execute(next((root/'supabase/migrations').glob('*_runtime_atomic_commit.sql')).read_text())
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await con.fetchval("select public.gc_commit_documents('[]')")

            class SQLRuntime(FakeRestSupabase):
                async def _rpc(self, function, payload):
                    async with pool.acquire() as con:
                        if function == 'gc_commit_documents':
                            async with con.transaction():
                                await con.execute("set local test.runtime_secret = 'test-secret'")
                                return json.loads(await con.fetchval('select public.gc_commit_documents($1::jsonb)', json.dumps(payload['p_changes'])))
                        rows = await con.fetch('select collection,id,data from gestionale.documents')
                    self.remote = {}
                    for row in rows:
                        self.remote.setdefault(row['collection'], {})[row['id']] = {**json.loads(row['data']), '_id': row['id']}
                    return await super()._rpc(function, payload)

            one, two = SQLRuntime(), SQLRuntime()
            await one['counters'].insert_one({'_id': 'c', 'n': 0})
            await asyncio.gather(*[db['counters'].update_one({'_id': 'c'}, {'$inc': {'n': 1}}) for db in [one,two]*2])
            assert (await one['counters'].find_one({'_id': 'c'}))['n'] == 4
            claims = await asyncio.gather(*[db['counters'].find_one_and_update(
                {'_id': 'c', 'claim': {'$exists': False}}, {'$set': {'claim': True}}, return_document=True) for db in [one,two]])
            assert sum(c is not None for c in claims) == 1
            await one['z_payments'].insert_one({'_id': 'old', 'idempotency_key': 'unique'})
            from app.services.supabase_runtime_database import DocumentoDuplicatoRemoto
            with pytest.raises(DocumentoDuplicatoRemoto):
                async with one.transaction():
                    await one['a_invoices'].insert_one({'_id': 'invoice'})
                    await one['z_payments'].insert_one({'_id': 'new', 'idempotency_key': 'unique'})
            assert await one['a_invoices'].find_one({'_id': 'invoice'}) is None
            assert await one['z_payments'].count_documents({}) == 1
            with pytest.raises(ValueError):
                async with one.transaction():
                    await one['a_invoices'].insert_one({'_id': 'invoice'})
                    raise ValueError('fallimento import')
            assert await one['a_invoices'].count_documents({}) == 0
            async with one.transaction():
                await one['a_invoices'].insert_one({'_id': 'invoice', 'n': 1})
                await one['a_invoices'].update_one({'_id': 'invoice'}, {'$inc': {'n': 2}})
            assert (await two['a_invoices'].find_one({'_id': 'invoice'}))['n'] == 3
            await one['a_invoices'].delete_one({'_id': 'invoice'})
            assert await two['a_invoices'].find_one({'_id': 'invoice'}) is None
        finally:
            if pool:
                await pool.close()
            await admin.execute(f'drop database {name} with (force)')
            await admin.close()
    asyncio.run(scenario())
