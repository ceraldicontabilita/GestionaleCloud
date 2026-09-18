import asyncio

from app.services.sheets_document_store import MemorySheetsClient


def test_cambio_metodo_scrive_una_volta_e_restituisce_valore_persistito(monkeypatch):
    asyncio.run(_test_cambio_metodo_scrive_una_volta_e_restituisce_valore_persistito(monkeypatch))


async def _test_cambio_metodo_scrive_una_volta_e_restituisce_valore_persistito(monkeypatch):
    from app.database import Database
    from app.routers.suppliers_module import base
    from app.utils import iva_calculator

    db = MemorySheetsClient()["supplier_update_exact"]
    await db["fornitori"].insert_one({
        "id": "supplier-1",
        "partita_iva": "04518411212",
        "ragione_sociale": "Fornitore prova",
        "metodo_pagamento": "cassa",
    })

    writes = 0
    original_update = db["fornitori"].update_one

    async def counted_update(*args, **kwargs):
        nonlocal writes
        writes += 1
        return await original_update(*args, **kwargs)

    cleared = []

    async def clear_pattern(pattern):
        cleared.append(pattern)

    async def save_dictionary(*args, **kwargs):
        return True

    def discard_background(coro):
        coro.close()
        return None

    monkeypatch.setattr(db["fornitori"], "update_one", counted_update)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    monkeypatch.setattr(base.cache, "clear_pattern", clear_pattern)
    monkeypatch.setattr(iva_calculator, "save_supplier_payment_method", save_dictionary)
    monkeypatch.setattr(asyncio, "create_task", discard_background)

    result = await base.update_supplier("supplier-1", {"metodo_pagamento": "banca"})

    assert writes == 1
    assert cleared == [base.SUPPLIERS_CACHE_KEY]
    assert result["supplier"]["metodo_pagamento"] == "banca"
    assert result["supplier"]["storico_metodi_pagamento"][0]["metodo"] == "banca"


def test_lista_filtrata_usa_cache_per_la_vista_standard(monkeypatch):
    asyncio.run(_test_lista_filtrata_usa_cache_per_la_vista_standard(monkeypatch))


async def _test_lista_filtrata_usa_cache_per_la_vista_standard(monkeypatch):
    from app.routers.suppliers_module import base

    captured = {}

    async def fake_list_suppliers(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(base, "list_suppliers", fake_list_suppliers)
    result = await base.list_suppliers_filtered()

    assert captured["use_cache"] is True
    assert result["items"] == []
