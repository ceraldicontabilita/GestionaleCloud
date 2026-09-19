import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import food_cost


def run(coro):
    return asyncio.run(coro)


def test_dizionario_esclude_fornitori_senza_expr_non_supportato(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(food_cost, "db", database)

    run(database.fornitori.insert_one({"nome": "Fornitore Escluso", "escluso": True}))
    run(database.dizionario_prodotti.insert_many([
        {
            "id": "escluso",
            "nome_originale": "Prodotto da nascondere",
            "nome_normalizzato": "prodotto da nascondere",
            "fornitore": "  FORNITORE ESCLUSO  ",
            "ultima_fattura_data": "2026-08-29",
        },
        {
            "id": "visibile",
            "nome_originale": "Prodotto valido",
            "nome_normalizzato": "prodotto valido",
            "fornitore": "Fornitore Attivo",
            "ultima_fattura_data": "2026-08-29",
        },
    ]))

    risultato = run(food_cost.get_dizionario(
        search=None,
        escludi_fornitori=True,
        senza_canonico=False,
        solo_completi=False,
        solo_esclusi=False,
        proponi_canonici=False,
        skip=0,
        limit=2000,
    ))

    assert risultato["totale"] == 1
    assert [p["id"] for p in risultato["prodotti"]] == ["visibile"]
