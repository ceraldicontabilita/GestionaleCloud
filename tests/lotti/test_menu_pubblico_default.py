import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import menu_backfill, menu_pubblico_default


def run(coro):
    return asyncio.run(coro)


def test_attiva_tutte_le_ricette_una_sola_volta(monkeypatch):
    db = AsyncMongoMockClient()["menu_pubblico_default_test"]
    run(db.ricette.insert_many([
        {"id": "r1", "nome": "Uno"},
        {"id": "r2", "nome": "Due", "menu_pubblico": False},
        {"id": "r3", "nome": "Tre", "menu_pubblico": True},
    ]))
    chiamate = []

    async def ripubblica(_db, *, dry_run=False):
        chiamate.append(dry_run)
        return {"ok": True, "errori": 0, "troncato": False, "aggiornate": 3}

    monkeypatch.setattr(menu_backfill, "ripubblica_menu", ripubblica)
    primo = run(menu_pubblico_default.applica(db))
    secondo = run(menu_pubblico_default.applica(db))

    assert primo["ricette_attivate"] == 2
    assert secondo == primo
    assert chiamate == [False]
    assert run(db.ricette.count_documents({"menu_pubblico": True})) == 3
