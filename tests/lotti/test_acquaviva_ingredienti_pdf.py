import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import acquaviva


def run(coro):
    return asyncio.run(coro)


def test_lista_ingredienti_usa_solo_codice_e_propaga_alla_ricetta(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(acquaviva, "db", database)
    prodotto = {
        "id": "aqv-60976", "fonte": "acquaviva", "codice_aqv_2026": "60976",
        "nome": "Treccina nocciola", "foto_url": "https://example.invalid/foto.jpg",
    }
    run(database.acquaviva_prodotti.insert_one(prodotto))
    run(database.dizionario_prodotti.insert_one({**prodotto, "attivo": True}))
    run(database.dizionario_ingredienti.insert_one({**prodotto, "attivo": True}))
    run(database.ricette.insert_one({
        "id": "ricetta-1", "nome": "Colazione",
        "ingredienti_dettaglio": [{"nome": "Treccina", "prodotto_id": "aqv-60976"}],
        "allergeni": ["Uova"], "allergeni_auto": ["Uova"],
        "allergeni_da_confermare": False,
    }))

    esito = run(acquaviva._applica_lista_ingredienti([{
        "codice": "60976", "nome_documento": "Nome diverso nel PDF",
        "ingredienti_str": "Farina di FRUMENTO, LATTE, NOCCIOLE, lecitina di SOIA",
        "pagina": 17,
    }], "AQV LISTA INGREDIENTI 2026.pdf"))

    assert esito["prodotti_aggiornati"] == 1
    assert esito["ricette_aggiornate"] == 1
    catalogo = run(database.acquaviva_prodotti.find_one({"id": "aqv-60976"}))
    assert catalogo["allergeni"] == ["Glutine", "Soia", "Latte", "Frutta a guscio"]
    assert catalogo["allergeni_fonte"]["codice"] == "60976"
    ricetta = run(database.ricette.find_one({"id": "ricetta-1"}))
    assert ricetta["allergeni"] == ["Uova", "Glutine", "Soia", "Latte", "Frutta a guscio"]
    assert ricetta["allergeni_da_confermare"] is True


def test_lista_ingredienti_non_forza_nome_e_blocca_codice_ambiguo(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(acquaviva, "db", database)
    run(database.acquaviva_prodotti.insert_many([
        {"id": "uno", "fonte": "acquaviva", "codice": "111", "nome": "Stesso nome"},
        {"id": "due", "fonte": "vandemoortele", "codice": "111", "nome": "Altro"},
        {"id": "tre", "fonte": "acquaviva", "codice": "333", "nome": "Nome PDF"},
    ]))
    righe = [
        {"codice": "111", "nome_documento": "Altro", "ingredienti_str": "LATTE", "pagina": 1},
        {"codice": "222", "nome_documento": "Nome PDF", "ingredienti_str": "UOVA", "pagina": 1},
    ]

    esito = run(acquaviva._applica_lista_ingredienti(righe, "fonte.pdf"))

    assert esito["prodotti_aggiornati"] == 0
    assert [x["codice"] for x in esito["ambigui"]] == ["111"]
    assert [x["codice"] for x in esito["non_trovati"]] == ["222"]
    assert run(database.acquaviva_prodotti.find_one({"id": "tre"})).get("ingredienti_str") is None


def test_cartelli_bar_restituisce_solo_prodotti_con_lista(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(acquaviva, "db", database)
    run(database.acquaviva_prodotti.insert_many([
        {"id": "con", "fonte": "acquaviva", "codice": "1", "nome": "Con lista",
         "ingredienti_str": "Farina", "allergeni": ["Glutine"]},
        {"id": "senza", "fonte": "acquaviva", "codice": "2", "nome": "Senza lista"},
        {"id": "altro", "fonte": "alpha", "codice": "3", "nome": "Altra fonte",
         "ingredienti_str": "Latte"},
    ]))
    run(database.dizionario_prodotti.insert_one({"id": "con", "attivo": True}))

    esito = run(acquaviva.get_cartelli_bar(search=None, solo_in_ricette=False))

    assert esito["totale"] == 1
    assert esito["prodotti"][0]["id"] == "con"
    assert esito["prodotti"][0]["in_ricette"] is True
