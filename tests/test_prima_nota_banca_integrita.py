import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module import manutenzione
from app.routers.prima_nota_module import sync as sync_module
from app.services.collaudo_invarianti import check_ec_dangling_e_duplicati


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_collaudo_accetta_solo_ripartizione_multi_fattura_quadrata():
    async def scenario():
        db = AsyncMongoMockClient()["test_collaudo_multi"]
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-MULTI", "importo": -300.0, "riconciliato": True,
            "tipo_riconciliazione": "fatture_multiple_causale",
        })
        await db.prima_nota_banca.insert_many([
            {"id": "PN-1", "estratto_conto_id": "EC-MULTI", "importo": 100.0,
             "invoice_id": "F-1", "source": "ric_auto_multi_fattura_causale"},
            {"id": "PN-2", "estratto_conto_id": "EC-MULTI", "importo": 200.0,
             "invoice_id": "F-2", "source": "ric_auto_multi_fattura_causale"},
        ])

        esito = await check_ec_dangling_e_duplicati(db)
        assert esito["violazioni"] == 0

        await db.prima_nota_banca.update_one({"id": "PN-2"}, {"$set": {"importo": 190.0}})
        esito_non_quadrato = await check_ec_dangling_e_duplicati(db)
        assert esito_non_quadrato["violazioni"] == 1

    _run(scenario())


def test_dedup_conserva_riga_collegata_e_pagamenti_multi(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_dedup_sicuro"]
        monkeypatch.setattr(manutenzione.Database, "get_db", staticmethod(lambda: db))
        await db.estratto_conto_movimenti.insert_many([
            {"id": "EC-SINGOLO", "importo": -100.0, "riconciliato": True},
            {"id": "EC-LINK", "importo": -50.0, "riconciliato": True},
            {"id": "EC-MULTI", "importo": -300.0, "riconciliato": True,
             "tipo_riconciliazione": "fatture_multiple_causale"},
        ])
        await db.prima_nota_banca.insert_many([
            {"id": "PN-GENERICA", "estratto_conto_id": "EC-SINGOLO", "importo": 100.0,
             "source": "estratto_conto_auto", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "PN-FATTURA", "estratto_conto_id": "EC-SINGOLO", "importo": 100.0,
             "fattura_id": "F-SINGOLA", "source": "estratto_conto_auto",
             "created_at": "2026-01-02T00:00:00Z"},
            {"id": "PN-L1", "estratto_conto_id": "EC-LINK", "importo": 50.0,
             "invoice_id": "F-LINK", "source": "estratto_conto_auto",
             "created_at": "2026-01-01T00:00:00Z"},
            {"id": "PN-L2", "estratto_conto_id": "EC-LINK", "importo": 50.0,
             "fattura_id": "F-LINK", "source": "estratto_conto_auto",
             "created_at": "2026-01-02T00:00:00Z"},
            {"id": "PN-M1", "estratto_conto_id": "EC-MULTI", "importo": 100.0,
             "invoice_id": "F-M1", "source": "ric_auto_multi_fattura_causale"},
            {"id": "PN-M2", "estratto_conto_id": "EC-MULTI", "importo": 200.0,
             "invoice_id": "F-M2", "source": "ric_auto_multi_fattura_causale"},
        ])
        await db.invoices.insert_one({
            "id": "F-SINGOLA", "pagato": True, "paid": True,
            "prima_nota_id": "PN-FATTURA", "prima_nota_banca_id": "PN-FATTURA",
        })
        await db.invoices.insert_one({
            "id": "F-LINK", "pagato": True, "paid": True,
            "prima_nota_id": "PN-L2", "prima_nota_banca_id": "PN-L2",
        })

        esito = await manutenzione.dedup_righe_stesso_estratto_conto(dry_run=False)

        assert esito["duplicate"] == 2
        assert esito["multi_fattura_preservati"] == 1
        assert esito["ambigui_non_modificati"] == 0
        assert await db.prima_nota_banca.count_documents({
            "estratto_conto_id": "EC-SINGOLO", "status": {"$nin": ["deleted", "archived"]}
        }) == 1
        assert await db.prima_nota_banca.find_one({"id": "PN-FATTURA", "status": {"$ne": "deleted"}})
        assert await db.prima_nota_banca.find_one({"id": "PN-GENERICA", "status": "deleted"})
        assert await db.prima_nota_banca.count_documents({
            "estratto_conto_id": "EC-MULTI", "status": {"$nin": ["deleted", "archived"]}
        }) == 2
        fattura = await db.invoices.find_one({"id": "F-SINGOLA"}, {"_id": 0})
        assert fattura["pagato"] is True
        assert fattura["prima_nota_id"] == "PN-FATTURA"
        fattura_riagganciata = await db.invoices.find_one({"id": "F-LINK"}, {"_id": 0})
        assert fattura_riagganciata["pagato"] is True
        assert fattura_riagganciata["prima_nota_id"] == "PN-L1"
        assert fattura_riagganciata["prima_nota_banca_id"] == "PN-L1"

    _run(scenario())


def test_dedup_non_modifica_collegamenti_fattura_ambigui(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_dedup_ambiguo"]
        monkeypatch.setattr(manutenzione.Database, "get_db", staticmethod(lambda: db))
        await db.estratto_conto_movimenti.insert_one({"id": "EC-X", "importo": -100.0})
        await db.prima_nota_banca.insert_many([
            {"id": "PN-A", "estratto_conto_id": "EC-X", "importo": 100.0,
             "fattura_id": "F-A", "created_at": "2026-01-01"},
            {"id": "PN-B", "estratto_conto_id": "EC-X", "importo": 100.0,
             "fattura_id": "F-B", "created_at": "2026-01-02"},
        ])

        esito = await manutenzione.dedup_righe_stesso_estratto_conto(dry_run=False)

        assert esito["duplicate"] == 0
        assert esito["ambigui_non_modificati"] == 1
        assert await db.prima_nota_banca.count_documents({"status": {"$nin": ["deleted", "archived"]}}) == 2

    _run(scenario())


def test_registra_pagamento_promuove_riga_ec_generica(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_promozione_generica"]
        monkeypatch.setattr(sync_module.Database, "get_db", staticmethod(lambda: db))
        await db.prima_nota_banca.insert_one({
            "id": "PN-GENERICA", "estratto_conto_id": "EC-1",
            "importo": 120.0, "data": "2026-02-20",
            "source": "estratto_conto_auto", "status": "active",
        })
        fattura = {
            "id": "F-1", "invoice_number": "1/2026", "invoice_date": "2026-02-01",
            "supplier_name": "FORNITORE", "total_amount": 120.0,
        }

        esito = await sync_module.registra_pagamento_fattura(
            fattura, "bonifico", source="estratto_conto_auto",
            movimento_bancario={"id": "EC-1", "match_score": 0.99},
        )

        assert esito["banca"] == "PN-GENERICA"
        assert await db.prima_nota_banca.count_documents({}) == 1
        riga = await db.prima_nota_banca.find_one({"id": "PN-GENERICA"}, {"_id": 0})
        assert riga["fattura_id"] == "F-1"
        assert riga["riconciliato"] is True
        assert riga["data"] == "2026-02-20"

    _run(scenario())
