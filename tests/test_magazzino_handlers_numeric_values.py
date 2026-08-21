import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.handlers.magazzino_handlers import on_fattura_righe_magazzino


def _run(coro):
    return asyncio.run(coro)


def test_righe_magazzino_normalizzano_numeri_italiani(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["magazzino_numeric_values"]
        await db.warehouse_inventory.insert_one({
            "id": "PROD-1",
            "nome": "CAFFE TEST",
            "nome_normalizzato": "caffe test",
            "unita_misura": "PZ",
        })

        async def no_audit(**_kwargs):
            return None

        monkeypatch.setattr("app.services.audit_logger.log_evento", no_audit)
        result = await on_fattura_righe_magazzino({
            "fattura_id": "INV-1",
            "fornitore_id": "FORN-1",
            "righe": [{
                "descrizione": "CAFFE TEST",
                "quantita": "2,00",
                "prezzo_unitario": "1.234,56",
                "unita_misura": "PZ",
            }],
        }, db)
        product = await db.warehouse_inventory.find_one({"id": "PROD-1"})
        purchase = await db.acquisti_prodotti.find_one({"fattura_id": "INV-1"})
        return result, product, purchase

    result, product, purchase = _run(scenario())
    assert result["risultati"]["risolte"] == 1
    assert product["ultimo_prezzo"] == 1234.56
    assert purchase["quantita"] == 2.0
    assert purchase["prezzo_unitario"] == 1234.56
