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
    run(database.ricette.insert_one({
        "id": "r-cartello", "nome": "Ricetta cartello",
        "ingredienti_dettaglio": [{"nome": "Con lista", "prodotto_id": "con"}],
    }))

    esito = run(acquaviva.get_cartelli_bar(search=None, solo_in_ricette=False))

    assert esito["totale"] == 1
    assert esito["prodotti"][0]["id"] == "con"
    assert esito["prodotti"][0]["in_ricette"] is True


def test_bonifica_catalogo_ricalcola_solo_da_lista_e_distingue_uso_ricetta(monkeypatch):
    database = AsyncMongoMockClient()["catalogo_bonifica"]
    monkeypatch.setattr(acquaviva, "db", database)
    run(database.acquaviva_prodotti.insert_many([
        {"id": "p1", "fonte": "acquaviva", "codice": "57245", "nome": "Con lista",
         "ingredienti_str": "Farina di FRUMENTO, LATTE", "allergeni": ["Pesce"],
         "foto_url": "https://example.invalid/1.jpg"},
        {"id": "p2", "fonte": "acquaviva", "codice": "NO-LISTINO", "nome": "Senza lista",
         "allergeni": ["Pesce"], "foto_url": "https://example.invalid/2.jpg"},
    ]))
    run(database.dizionario_prodotti.insert_many([
        {"id": "p1", "attivo": True}, {"id": "p2", "attivo": True},
    ]))
    run(database.ricette.insert_one({
        "id": "r1", "nome": "Ricetta", "ingredienti_dettaglio": [
            {"nome": "Prodotto", "prodotto_id": "p1"},
        ], "allergeni": [], "allergeni_auto": [],
    }))

    anteprima = run(acquaviva.bonifica_allergeni_cartelli(
        dry_run=True, conferma="", _admin={},
    ))
    assert anteprima["con_lista"] == 1 and anteprima["senza_lista"] == 1
    assert anteprima["in_ricette"] == 1 and anteprima["disponibili_ricette"] == 2

    esito = run(acquaviva.bonifica_allergeni_cartelli(
        dry_run=False, conferma="BONIFICA_CATALOGO", _admin={},
    ))
    assert esito["aggiornati"] == 2 and esito["ricette_aggiornate"] == 1
    p1 = run(database.acquaviva_prodotti.find_one({"id": "p1"}))
    p2 = run(database.acquaviva_prodotti.find_one({"id": "p2"}))
    assert p1["allergeni"] == ["Glutine", "Latte"]
    assert p1["cartello_stampabile"] is True and p1["in_ricette"] is True
    assert p2["allergeni"] == []
    assert p2["allergeni_precedenti_non_verificati"] == ["Pesce"]
    assert p2["cartello_stampabile"] is False and p2["in_ricette"] is False

    # La bonifica e' idempotente e non perde la precedente dichiarazione dubbia.
    run(acquaviva.bonifica_allergeni_cartelli(
        dry_run=False, conferma="BONIFICA_CATALOGO", _admin={},
    ))
    p2 = run(database.acquaviva_prodotti.find_one({"id": "p2"}))
    assert p2["allergeni_precedenti_non_verificati"] == ["Pesce"]
