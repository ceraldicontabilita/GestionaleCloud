import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import cataloghi_prezzi, catalogo_forno, food_cost


def run(coro):
    return asyncio.run(coro)


def test_prezzo_saima_resta_separato_dal_prezzo_fattura(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(cataloghi_prezzi, "db", database)
    run(database.dizionario_ingredienti.insert_one({
        "id": "saima-123",
        "fonte": "saima",
        "codice_articolo": "123",
        "prezzo_listino": 9.5,
        "prezzo_fonte": "fattura_xml",
    }))

    result = run(cataloghi_prezzi.salva_prezzo_fornitore(
        cataloghi_prezzi.PrezzoFornitoreUpdate(
            fonte="saima", prodotto_id="saima-123", prezzo=12.4,
        ),
        _admin={"nome": "Amministratore"},
    ))

    doc = run(database.dizionario_ingredienti.find_one({"id": "saima-123"}))
    assert result["prezzo_fornitore"] == 12.4
    assert doc["prezzo_fornitore"] == 12.4
    assert doc["prezzo_fornitore_fonte"] == "comunicato_dal_fornitore"
    assert doc["prezzo_fornitore_iva_esclusa"] is True
    assert doc["prezzo_listino"] == 9.5
    assert doc["prezzo_fonte"] == "fattura_xml"


def test_prezzo_catalogo_generico_usa_fornitore_e_codice(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(cataloghi_prezzi, "db", database)
    run(database.catalogo_forno_prodotti.insert_one({
        "fornitore": "bindi", "codice_articolo": "B-7", "nome": "Prodotto Bindi",
    }))

    run(cataloghi_prezzi.salva_prezzo_fornitore(
        cataloghi_prezzi.PrezzoFornitoreUpdate(
            fonte="bindi", fornitore="bindi", codice_articolo="B-7", prezzo=21.75,
        ),
        _admin={"nome": "Amministratore"},
    ))

    doc = run(database.catalogo_forno_prodotti.find_one({"codice_articolo": "B-7"}))
    assert doc["prezzo_fornitore"] == 21.75
    assert doc["prezzo_fornitore_data"]


def test_prezzo_alpha_si_salva_nel_catalogo_acquaviva(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(cataloghi_prezzi, "db", database)
    run(database.acquaviva_prodotti.insert_one({
        "id": "alpha-9", "fonte": "alpha", "codice": "A-9", "nome": "Prodotto Alfa",
    }))

    run(cataloghi_prezzi.salva_prezzo_fornitore(
        cataloghi_prezzi.PrezzoFornitoreUpdate(
            fonte="alpha", prodotto_id="alpha-9", codice_articolo="A-9", prezzo=7.25,
        ),
        _admin={"nome": "Amministratore"},
    ))

    doc = run(database.acquaviva_prodotti.find_one({"id": "alpha-9"}))
    assert doc["prezzo_fornitore"] == 7.25
    assert doc["prezzo_fornitore_iva_esclusa"] is True


def test_cataloghi_precaricati_si_completano_senza_duplicati(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(catalogo_forno, "db", database)
    run(database.catalogo_forno_prodotti.insert_one({
        "fornitore": "tremarie", "codice_articolo": "parziale", "nome": "Parziale",
    }))

    primo = run(catalogo_forno.inizializza_cataloghi_precaricati())
    totale_primo = run(database.catalogo_forno_prodotti.count_documents({}))
    secondo = run(catalogo_forno.inizializza_cataloghi_precaricati())
    totale_secondo = run(database.catalogo_forno_prodotti.count_documents({}))

    assert primo["pasticcere"]["importati"] == 111
    assert primo["tremarie"]["importati"] == 112
    assert primo["bindi"]["importati"] == 89
    assert totale_primo == totale_secondo
    assert secondo["pasticcere"]["gia_presenti"] == 111


def test_usa_in_ricetta_promuove_catalogo_saima_legacy(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(food_cost, "db", database)
    run(
        database.dizionario_ingredienti.insert_one(
            {
                "id": "saima-legacy-1",
                "fonte": "saima",
                "nome": "Croissant prova SAIMA",
                "codice_articolo": "S-1",
                "attivo": False,
            }
        )
    )

    result = run(
        food_cost.aggiorna_campi_dizionario(
            "saima-legacy-1",
            {"attivo": True, "is_saima": True},
            _admin={"nome": "Amministratore"},
        )
    )

    canonico = run(database.dizionario_prodotti.find_one({"id": "saima-legacy-1"}))
    assert result == {"status": "ok", "modificato": True}
    assert canonico["nome"] == "Croissant prova SAIMA"
    assert canonico["nome_normalizzato"] == "croissant prova saima"
    assert canonico["attivo"] is True
    assert canonico["is_saima"] is True

    # Una seconda pressione aggiorna lo stesso record, senza creare doppioni.
    run(
        food_cost.aggiorna_campi_dizionario(
            "saima-legacy-1",
            {"attivo": False, "is_saima": False},
            _admin={"nome": "Amministratore"},
        )
    )
    assert run(database.dizionario_prodotti.count_documents({"id": "saima-legacy-1"})) == 1
    assert run(database.dizionario_prodotti.find_one({"id": "saima-legacy-1"}))["attivo"] is False
