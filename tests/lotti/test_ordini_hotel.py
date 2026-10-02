import asyncio

from mongomock_motor import AsyncMongoMockClient
import pytest

from app.lotti.servizi import ordini_hotel as servizio


def run(coro):
    return asyncio.run(coro)


def test_ordine_hotel_conserva_prezzi_allergeni_ricetta_e_fattura(monkeypatch):
    db = AsyncMongoMockClient()["ordini_hotel_test"]
    monkeypatch.setattr(servizio, "db", db)
    run(db.prodotti_vendita.insert_one({"id": "pv-1", "ricetta_id": "ric-1"}))
    run(db.ricette.insert_one({"id": "ric-1", "reparto": "pasticceria", "allergeni": ["Glutine", "Uova"]}))
    run(db.fatture.insert_one({
        "id": "fat-1", "fornitore": "Vandemoortele Europe", "numero_fattura": "V-77",
        "data_fattura": "2026-09-20", "prodotti": [{"descrizione": "Croissant vuoto 80 g", "quantita": 24}],
    }))
    chiave_vdm = "vandemoortele:" + servizio._digest_vdm("Croissant vuoto 80 g")
    catalogo = {
        "interno:pv-1": {"chiave": "interno:pv-1", "origine": "produzione_interna", "nome": "Brioche crema", "prezzo": 2.5, "allergeni": ["Latte"]},
        chiave_vdm: {"chiave": chiave_vdm, "origine": "vandemoortele", "nome": "Croissant vuoto", "descrizione": "Croissant vuoto 80 g", "prezzo": 1.2, "allergeni": ["Glutine"]},
    }

    ordine = run(servizio.crea_ordine(
        struttura_id="hotel-1", struttura_nome="Hotel Vesuvio", data_consegna="2026-10-02",
        catalogo=catalogo,
        righe=[{"chiave": "interno:pv-1", "quantita": 3}, {"chiave": chiave_vdm, "quantita": 5}],
        nota="entro le 7", idempotenza="prova-1",
    ))

    assert ordine["totale"] == 13.5
    interna, acquistata = ordine["righe"]
    assert interna["ricetta_id"] == "ric-1"
    assert interna["tracciabilita_stato"] == "produzione_da_registrare"
    assert set(interna["allergeni"]) == {"Glutine", "Uova", "Latte"}
    assert acquistata["fatture_origine"][0]["numero_fattura"] == "V-77"
    assert acquistata["tracciabilita_stato"] == "lotto_fornitore_da_associare"

    ripetuto = run(servizio.crea_ordine(
        struttura_id="hotel-1", struttura_nome="Hotel Vesuvio", data_consegna="2026-10-02",
        catalogo=catalogo, righe=[{"chiave": "interno:pv-1", "quantita": 99}],
        idempotenza="prova-1",
    ))
    assert ripetuto["id"] == ordine["id"]
    assert run(db.ordini_hotel.count_documents({})) == 1


def test_lotto_reale_e_incasso_si_associano_all_ordine(monkeypatch):
    db = AsyncMongoMockClient()["ordini_hotel_lotti_test"]
    monkeypatch.setattr(servizio, "db", db)
    run(db.prodotti_vendita.insert_one({"id": "pv-1", "ricetta_id": "ric-1"}))
    run(db.ricette.insert_one({"id": "ric-1", "allergeni": []}))
    catalogo = {"interno:pv-1": {"chiave": "interno:pv-1", "origine": "produzione_interna", "nome": "Treccia", "prezzo": 2, "allergeni": []}}
    ordine = run(servizio.crea_ordine(
        struttura_id="hotel-1", struttura_nome="Hotel Vesuvio", data_consegna="2026-10-02",
        catalogo=catalogo, righe=[{"chiave": "interno:pv-1", "quantita": 2}], idempotenza="prova-2",
    ))
    run(db.lotti.insert_one({"id": "lot-1", "numero_lotto": "TRE-20261002-01", "prodotto": "Treccia"}))

    collegato = run(servizio.associa_lotto(ordine["id"], "interno:pv-1", "TRE-20261002-01", da="Enzo"))
    assert collegato["righe"][0]["tracciabilita_stato"] == "lotto_associato"
    assert collegato["righe"][0]["lotti_associati"][0]["id"] == "lot-1"

    aggiornato = run(servizio.aggiorna_ordine(ordine["id"], stato="consegnato", pagamento="incassato", da="Enzo"))
    assert aggiornato["stato"] == "consegnato"
    assert aggiornato["pagamento"] == "incassato"
    assert len(aggiornato["audit"]) == 3


def test_non_scambia_lotto_fornitore_con_lotto_di_produzione(monkeypatch):
    db = AsyncMongoMockClient()["ordini_hotel_tipo_lotto_test"]
    monkeypatch.setattr(servizio, "db", db)
    run(db.ordini_hotel.insert_one({
        "id": "OH-TIPO",
        "righe": [{
            "chiave": "interno:p1",
            "tracciabilita_tipo": "lotto_produzione",
            "lotti_associati": [],
        }],
    }))
    run(db.lotti_fornitori.insert_one({
        "id": "forn-1", "numero_lotto": "VDM-001", "prodotto": "Croissant",
    }))

    with pytest.raises(ValueError, match="Lotto reale di produzione non trovato"):
        run(servizio.associa_lotto("OH-TIPO", "interno:p1", "VDM-001", da="test"))


def test_menu_unico_conserva_tracciabilita_solo_quando_documentata(monkeypatch):
    db = AsyncMongoMockClient()["ordini_hotel_menu_unico_test"]
    monkeypatch.setattr(servizio, "db", db)
    run(db.ricette.insert_one({
        "id": "ric-menu", "reparto": "pasticceria", "allergeni": ["Uova"],
    }))
    catalogo = {
        "menu:prodotto-ricetta": {
            "chiave": "menu:prodotto-ricetta", "nome": "Treccia",
            "prezzo": 2.5, "allergeni": ["Latte"], "lotti_ref": "ricetta:ric-menu",
        },
        "menu:prodotto-generico": {
            "chiave": "menu:prodotto-generico", "nome": "Bibita", "prezzo": 2,
        },
    }

    ordine = run(servizio.crea_ordine(
        struttura_id="hotel-1", struttura_nome="Hotel Vesuvio", data_consegna="2026-10-03",
        catalogo=catalogo,
        righe=[
            {"chiave": "menu:prodotto-ricetta", "quantita": 1},
            {"chiave": "menu:prodotto-generico", "quantita": 1},
        ],
    ))

    produzione, generico = ordine["righe"]
    assert produzione["menu_prodotto_id"] == "prodotto-ricetta"
    assert produzione["ricetta_id"] == "ric-menu"
    assert produzione["tracciabilita_tipo"] == "lotto_produzione"
    assert set(produzione["allergeni"]) == {"Latte", "Uova"}
    assert generico["tracciabilita_tipo"] == "da_classificare"
    assert generico["tracciabilita_stato"] == "origine_da_verificare"
