import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import lotti_produzione, ordini_fornitori


def run(coro):
    return asyncio.run(coro)


def test_ingrediente_xml_associato_ma_assente_entra_nella_bozza(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(lotti_produzione, "db", database)
    chiamate = []

    async def fake_aggiungi(**kwargs):
        chiamate.append(kwargs)
        return {"ok": True, "ordine_id": "ordine-1"}

    monkeypatch.setattr(ordini_fornitori, "aggiungi_a_bozza_riordino", fake_aggiungi)

    esito = run(lotti_produzione._riordini_post_produzione(
        [],
        "Girella con scarola",
        [{
            "nome": "Scarola",
            "prodotto_fattura_id": "fattura-abc",
            "prodotto_fattura_nome": "SCAROLA RICCIA CASSETTA",
            "prodotto_fattura_fornitore": "Orto Fornitore",
            "associazione_prodotto_stato": "confermata",
            "quantita_mancante": 400,
            "unita_mancante": "g",
            "motivo_riordino": "nessun lotto disponibile",
        }],
    ))

    assert len(chiamate) == 1
    assert chiamate[0]["prodotto_id"] == "fattura-abc"
    assert chiamate[0]["nome"] == "SCAROLA RICCIA CASSETTA"
    assert chiamate[0]["fornitore_preferito"] == "Orto Fornitore"
    assert chiamate[0]["quantita"] == 1
    assert chiamate[0]["unita"] == "conf."
    assert esito[0]["prodotto"] == "SCAROLA RICCIA CASSETTA"


def test_ingrediente_non_associato_non_genera_ordine_inventato(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(lotti_produzione, "db", database)
    chiamate = []

    async def fake_aggiungi(**kwargs):
        chiamate.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(ordini_fornitori, "aggiungi_a_bozza_riordino", fake_aggiungi)
    esito = run(lotti_produzione._riordini_post_produzione(
        [], "Ricetta", [{"nome": "Ingrediente ambiguo", "quantita_mancante": 1}],
    ))

    assert chiamate == []
    assert esito == []


def test_scarico_espone_ingrediente_assente_come_da_ordinare(monkeypatch):
    async def nessun_lotto(_ingrediente):
        return [], []

    monkeypatch.setattr(lotti_produzione, "_candidati_lotti_fifo", nessun_lotto)
    risultato = run(lotti_produzione.scala_lotti_fornitori_per_ricetta(
        {"ingredienti_dettaglio": [{
            "nome": "Scarola",
            "quantita": 400,
            "unita_misura": "g",
            "prodotto_fattura_id": "fattura-abc",
            "prodotto_fattura_nome": "SCAROLA RICCIA CASSETTA",
            "associazione_prodotto_stato": "confermata",
        }]},
        1,
        "LOT-1",
    ))

    assert risultato["ingredienti_non_trovati"] == ["Scarola"]
    assert risultato["ingredienti_da_ordinare"][0]["prodotto_fattura_id"] == "fattura-abc"
    assert risultato["ingredienti_da_ordinare"][0]["quantita_mancante"] == 400

