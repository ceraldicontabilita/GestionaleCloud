import asyncio
from unittest.mock import AsyncMock
from mongomock_motor import AsyncMongoMockClient
from app.menu.routes import warehouse_routes as routes
from app.menu.models.warehouse_models import MovementCreate, WarehouseItemUpdate


def test_items_read_canonical_stock_without_public_staging(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()['warehouse']
        monkeypatch.setattr(routes, 'lotti_db', db)
        await db.magazzino_bar_prodotti.insert_one({'id': 'p1', 'nome': 'Farina', 'stock': 12})
        items = await routes.list_items(username='admin')
        assert items[0]['id'] == 'p1'
        assert items[0]['quantity'] == 12
        await routes.update_item('p1', WarehouseItemUpdate(name='Farina bio'), username='admin')
        doc = await db.magazzino_bar_prodotti.find_one({'id': 'p1'})
        assert doc['stock'] == 12 and doc['nome'] == 'Farina bio'
    asyncio.run(scenario())


def test_movements_delegate_to_single_stock_writer(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()['warehouse']
        monkeypatch.setattr(routes, 'lotti_db', db)
        await db.magazzino_bar_prodotti.insert_one({'id': 'p1', 'nome': 'Farina', 'stock': 12})
        async def writer(prod, delta, kind, username, note, extra):
            await db.magazzino_bar_prodotti.update_one({'id': prod['id']}, {'$inc': {'stock': delta}})
            return 12 + delta, {}
        canonical = AsyncMock(side_effect=writer)
        monkeypatch.setattr(routes, 'applica_movimento_stock', canonical)
        await asyncio.gather(*[routes.register_movement('p1', MovementCreate(type='scarico', quantity=2), username='admin') for _ in range(2)])
        assert (await db.magazzino_bar_prodotti.find_one({'id': 'p1'}))['stock'] == 8
        assert canonical.await_count == 2
        assert canonical.call_args.args[1] == -2
    asyncio.run(scenario())
