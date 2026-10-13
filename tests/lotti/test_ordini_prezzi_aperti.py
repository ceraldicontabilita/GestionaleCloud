import asyncio
from mongomock_motor import AsyncMongoMockClient
from app.lotti.routers import ordini_fornitori as ordini
from app.lotti.routers.ordini_fornitori import _riga_con_prezzo_fattura


def test_aggiornamento_prezzo_aperto_calcola_confezione_iva_e_storico():
    riga = {"prodotto_id": "cat_saima-N031", "nome": "Crema nocciola", "unita": "13 KG",
            "prezzo_ultimo": 4.11, "iva_pct": 0}
    articolo = {"prezzo": 4.50, "unita_confezione": "KG", "iva_pct": 10}
    aggiornata, cambiata = _riga_con_prezzo_fattura(riga, articolo, "2026-10-13T06:30:00Z")
    assert cambiata is True
    assert aggiornata["prezzo_unitario_fattura"] == 4.50
    assert aggiornata["prezzo_ultimo"] == 58.50
    assert aggiornata["iva_pct"] == 10
    assert aggiornata["prezzo_precedente"] == 4.11
    assert aggiornata["storico_prezzi"][-1]["da"] == 4.11


def test_prezzo_invariato_non_crea_un_falso_aggiornamento():
    riga = {"nome": "Prodotto", "unita": "1 PZ", "prezzo_ultimo": 5, "iva_pct": 10}
    aggiornata, cambiata = _riga_con_prezzo_fattura(
        riga, {"prezzo": 5, "unita_confezione": "PZ", "iva_pct": 10}, "oggi")
    assert cambiata is False and aggiornata == riga


def test_recupero_bozza_nel_carrello_e_annullamento_conservano_lo_storico(monkeypatch):
    async def scenario():
        database = AsyncMongoMockClient().lotti
        monkeypatch.setattr(ordini, "db", database)
        await database.ordini_fornitori.insert_one({"id": "o1", "stato": "bozza", "prodotti": [
            {"prodotto_id": "cat_saima-N031", "nome": "Crema", "fornitore": "SAIMA",
             "quantita": 2, "unita": "13 KG", "prezzo_ultimo": 53.43, "iva_pct": 10}]})
        recuperato = await ordini.riporta_ordine_al_carrello("o1", _admin=True)
        assert recuperato["righe"][0]["id"] == "saima-N031"
        assert (await database.ordini_fornitori.find_one({"id": "o1"}))["stato"] == "in_modifica"
        await ordini.elimina_ordine("o1", _admin=True)
        assert (await database.ordini_fornitori.find_one({"id": "o1"}))["stato"] == "annullato"
        assert await database.ordini_fornitori.count_documents({"id": "o1"}) == 1
    asyncio.run(scenario())
