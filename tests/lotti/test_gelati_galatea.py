"""Il pannello Galatea legge righe di fattura, senza inventare cataloghi."""

import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import gelati


def run(coro):
    return asyncio.run(coro)


def test_righe_galatea_da_fattura_reale_con_identita_fiscale(monkeypatch):
    database = AsyncMongoMockClient()["Gelati_Test"]
    monkeypatch.setattr(gelati, "db", database)

    async def scenario():
        await database.fatture.insert_many([
            {
                "id": "fattura-gelinova", "fornitore": "GELINOVA GROUP SRL società unipersonale",
                "piva": "03762010266", "numero_fattura": "001852/2",
                "data_fattura": "14/05/2026", "gestionale_source_id": "1785230041203",
                "prodotti": [
                    {"codice_articolo": "71004", "descrizione": "SET_CORE VELLUTO 540 KG 2X8", "quantita": "32.00000000", "prezzo": "13.20000000"},
                    {"codice_articolo": "60407", "descrizione": "CARAFFA 5LT GALATEA", "quantita": "4.00000000", "prezzo": "7.30000000"},
                ],
            },
            {"id": "altro", "fornitore": "Altro", "piva": "00000000000", "prodotti": [{"descrizione": "Non Galatea"}]},
            {"id": "annullata", "fornitore": "GELINOVA", "piva": "03762010266", "annullata": True, "prodotti": [{"descrizione": "Non acquistato"}]},
        ])
        return await gelati.prodotti_galatea_acquistati()

    esito = run(scenario())
    assert esito["fatture"] == 1
    assert esito["righe"] == 2
    assert [r["codice_articolo"] for r in esito["prodotti"]] == ["71004", "60407"]
    assert esito["prodotti"][0]["fattura_id"] == "fattura-gelinova"
    assert esito["prodotti"][0]["gestionale_source_id"] == "1785230041203"
    assert esito["prodotti"][0]["prezzo_unitario"] == "13.20000000"
    assert "allergeni" not in esito["prodotti"][0]


def test_senza_fatture_non_inventa_prodotti(monkeypatch):
    database = AsyncMongoMockClient()["Gelati_Test"]
    monkeypatch.setattr(gelati, "db", database)
    esito = run(gelati.prodotti_galatea_acquistati())
    assert esito["fatture"] == esito["righe"] == 0
    assert esito["prodotti"] == []
