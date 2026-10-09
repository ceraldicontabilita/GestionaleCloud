import asyncio

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_modifica_ingredienti_sincronizza_lista_e_allergeni(monkeypatch):
    import app.lotti.routers.ricette as ricette
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)
    run(database.ricette.insert_one({
        "id": "R1", "nome": "Biscotto", "ingredienti": ["Zucchero"],
        "ingredienti_dettaglio": [{"nome": "Zucchero", "quantita": 1}],
        "allergeni": [], "allergeni_auto": [],
    }))
    risultato = run(ricette.aggiorna_ingredienti_dettaglio("R1", [
        {"nome": " Farina di grano ", "quantita": 100, "unita_misura": "g"},
        {"nome": "", "quantita": 10},
    ]))
    assert risultato["ingredienti"] == ["Farina di grano"]
    assert risultato["ingredienti_dettaglio"][0]["nome"] == "Farina di grano"
    assert risultato["origine_ingredienti"] == "manuale"
    assert risultato["allergeni_auto"]
    assert risultato["allergeni"] == risultato["allergeni_auto"]
    assert risultato["allergeni_da_confermare"] is True
