import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.f24 import f24_public, f24_riconciliazione


def test_elenco_quietanze_pagato_senza_banca_e_senza_contare_anche_il_modello(monkeypatch):
    db = AsyncMongoMockClient()["quietanze-viste"]
    monkeypatch.setattr(f24_public.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db.quietanze_f24.insert_many([
            {"id": "q1", "data_pagamento": "2026-04-16", "protocollo_telematico": "P1",
             "saldo": 100, "created_at": "2026-04-16"},
            {"id": "q2", "data_pagamento": "2026-04-16", "protocollo_telematico": "P1",
             "saldo": 50, "created_at": "2026-04-16"},
        ])
        await db.f24_unificato.insert_one({"id": "f1", "quietanza_id": "q1", "status": "da_pagare",
                                          "data_versamento": "2026-04-16", "totali": {"saldo_netto": 100}})
        return await f24_public.list_f24_models()

    risultato = asyncio.run(scenario())
    assert risultato["count"] == 2
    assert risultato["totale_pagato"] == 150
    assert risultato["totale_da_pagare"] == 0
    assert all(f["pagato"] and not f["pagamento_verificato_banca"] for f in risultato["f24s"])


def test_ripetere_la_riconciliazione_conserva_i_collegamenti_dei_modelli_pagati(monkeypatch):
    db = AsyncMongoMockClient()["quietanze-ripetute"]
    monkeypatch.setattr(f24_riconciliazione.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db.quietanze_f24.insert_one({"id": "q1", "f24_associati": ["f1"]})
        await db.f24_unificato.insert_one({"id": "f1", "quietanza_id": "q1", "status": "pagato"})
        for _ in range(2):
            esito = await f24_riconciliazione.riconcilia_tutto()
            assert esito["riepilogo"]["quietanze_usate"] == 1
        assert (await db.quietanze_f24.find_one({"id": "q1"}))["f24_associati"] == ["f1"]

    asyncio.run(scenario())
