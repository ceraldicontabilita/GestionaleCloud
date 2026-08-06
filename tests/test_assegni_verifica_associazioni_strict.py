import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import assegni as assegni_router


async def _scenario_importo_diverso_di_un_centesimo(monkeypatch):
    db = AsyncMongoMockClient()["test_assegni_verifica_centesimo"]
    await db["assegni"].insert_one({
        "id": "a1",
        "numero": "0208770985",
        "anno": 2026,
        "fattura_id": "f1",
        "numero_fattura": "27",
        "importo": 9760.00,
        "beneficiario": "Fornitore Uno",
    })
    await db["invoices"].insert_one({
        "id": "f1",
        "invoice_number": "27",
        "total_amount": 9760.01,
        "supplier_name": "Fornitore Uno",
    })
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    esito = await assegni_router.verifica_associazioni_assegni(anno=2026)

    assert esito["statistiche"]["problemi_importo"] == 1
    assert esito["statistiche"]["associazioni_corrette"] == 0


async def _scenario_suggerimento_richiede_numero_e_importo(monkeypatch):
    db = AsyncMongoMockClient()["test_assegni_verifica_riferimento"]
    await db["assegni"].insert_one({
        "id": "a1",
        "numero": "0208770985",
        "anno": 2026,
        "fattura_id": "fattura-mancante",
        "numero_fattura": "27",
        "importo": 9760.00,
    })
    await db["invoices"].insert_many([
        {
            "id": "f-corretta",
            "invoice_number": "27",
            "total_amount": 9760.00,
            "supplier_name": "Fornitore Uno",
        },
        {
            "id": "f-stesso-importo-numero-diverso",
            "invoice_number": "99",
            "total_amount": 9760.00,
            "supplier_name": "Fornitore Due",
        },
        {
            "id": "f-stesso-numero-importo-diverso",
            "invoice_number": "27",
            "total_amount": 9759.99,
            "supplier_name": "Fornitore Uno",
        },
    ])
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    esito = await assegni_router.verifica_associazioni_assegni(anno=2026)

    assert esito["totale_problemi"] == 1
    assert [riga["fattura_id"] for riga in esito["problemi"][0]["suggerimenti"]] == [
        "f-corretta"
    ]


def test_verifica_segnala_anche_un_centesimo_di_differenza(monkeypatch):
    asyncio.run(_scenario_importo_diverso_di_un_centesimo(monkeypatch))


def test_suggerimento_richiede_numero_fattura_e_importo_esatti(monkeypatch):
    asyncio.run(_scenario_suggerimento_richiede_numero_e_importo(monkeypatch))
