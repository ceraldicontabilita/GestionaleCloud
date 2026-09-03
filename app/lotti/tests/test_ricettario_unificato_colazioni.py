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


ARCHIVIO = {
    "recipes": [{
        "kind": "recipe", "id": "r-1", "number": 1, "name": "Biscotti Savoiardi",
        "source": "Ciocca", "ingredients": "Uova 30 pz\nZucchero 750 g\nFarina 375 g\n23",
        "procedure": "Montare e cuocere.", "notes": "", "provenance": {"sheet": "Ricette", "row": 23},
    }],
    "components": [],
}


def test_parser_archivio_esclude_pagine_e_conserva_dosi():
    from app.lotti.routers.ricette import _righe_ingredienti_archivio
    righe = _righe_ingredienti_archivio(ARCHIVIO["recipes"][0]["ingredients"])
    assert [r["nome"] for r in righe] == ["Uova", "Zucchero", "Farina"]
    assert righe[0]["quantita"] == 30
    assert righe[0]["unita_misura"] == "pz"
    assert righe[1]["quantita"] == 750


def test_lista_unificata_collega_senza_duplicare(monkeypatch):
    import app.lotti.routers.ricette as ricette
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)
    monkeypatch.setattr(ricette, "_carica_archivio_dolce", lambda: ARCHIVIO)
    run(database.ricette.insert_one({"id": "CER-1", "nome": "Biscotti savoiardi", "reparto": "pasticceria"}))

    risultato = run(ricette.get_ricette_unificate(search=None))

    assert len(risultato) == 1
    assert risultato[0]["id"] == "CER-1"
    assert risultato[0]["documentazione_archivio"]["procedure"] == "Montare e cuocere."


def test_promozione_archivio_e_idempotente(monkeypatch):
    import app.lotti.routers.ricette as ricette
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)
    monkeypatch.setattr(ricette, "_carica_archivio_dolce", lambda: ARCHIVIO)

    prima = run(ricette.rendi_ricetta_archivio_operativa("recipe", "r-1", _admin={}))
    seconda = run(ricette.rendi_ricetta_archivio_operativa("recipe", "r-1", _admin={}))

    assert prima["creata"] is True
    assert seconda["creata"] is False
    assert prima["ricetta"]["id"] == seconda["ricetta"]["id"]
    assert run(database.ricette.count_documents({})) == 1


def test_popolamento_quattro_stagioni_non_sovrascrive(monkeypatch):
    import app.lotti.routers.colazione as colazione
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(colazione, "db", database)

    async def garantisci_stagioni():
        for nome in colazione._STAGIONI_DEFAULT:
            await database.colazione_template.update_one(
                {"nome": nome}, {"$setOnInsert": {"nome": nome, "items": []}}, upsert=True)
        return []

    async def disponibili(catalogo=False, solo_acquistati=True):
        return [
            {"id": "A", "nome": "Cornetto", "fonte": "rivendita", "gia_acquistato": True},
            {"id": "A", "nome": "Cornetto duplicato nel catalogo", "fonte": "rivendita", "gia_acquistato": True},
            {"id": "CASA", "nome": "Pastiera", "fonte": "casa", "gia_acquistato": True},
        ]

    monkeypatch.setattr(colazione, "lista_preset", garantisci_stagioni)
    monkeypatch.setattr(colazione, "get_prodotti_disponibili", disponibili)
    run(database.colazione_template.insert_one({
        "nome": "Primavera",
        "items": [{"prodotto_id": "A", "prodotto_nome": "Cornetto", "pezzi": 11, "attivo": False}],
    }))

    prima = run(colazione.popola_quattro_stagioni(_admin={}))
    seconda = run(colazione.popola_quattro_stagioni(_admin={}))
    primavera = run(database.colazione_template.find_one({"nome": "Primavera"}))

    assert prima["totale_aggiunte"] == 3
    assert prima["prodotti_acquistati"] == 1
    assert seconda["totale_aggiunte"] == 0
    assert primavera["items"][0]["pezzi"] == 11
    assert primavera["items"][0]["attivo"] is False
    assert all(x["prodotto_id"] != "CASA" for x in primavera["items"])
