import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import ordini_fornitori as mod


def run(coro):
    return asyncio.run(coro)


def test_fattura_con_prezzo_maggiore_crea_evidenza_sull_ordine(monkeypatch):
    database = AsyncMongoMockClient()["Ordini_Riconciliazione_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ordini_fornitori.insert_one({
            "id": "ord-1", "numero_ordine": "ORD-20261013-0001",
            "stato": "inviato_fornitori", "inviato_at": "2026-10-13T08:00:00+00:00",
            "fornitore": "MEPA Alimentari", "prodotti": [{
                "prodotto_id": "cat_IRCA245", "codici": ["IRCA245"],
                "nome": "IRCA MIX AMERICAN COOKIES", "fornitore": "MEPA Alimentari",
                "prezzo_ordinato": 50.0, "quantita": 2,
            }],
        })
        esito = await mod.riconcilia_fattura_con_ordine(
            "MEPA Alimentari",
            [{"codice_articolo": "IRCA245", "descrizione": "AMERICAN COOKIES", "prezzo_unitario": 55.0}],
            "fatt-1", "14/10/2026",
        )
        ordine = await database.ordini_fornitori.find_one({"id": "ord-1"})
        alerts = await database.alert_prezzi.find({}).to_list(None)
        return esito, ordine, alerts

    esito, ordine, alerts = run(scenario())
    assert esito["scostamenti_prezzo"] == 1
    assert esito["alert_creato"] is True
    assert ordine["riconciliazione"]["scostamenti_prezzo"][0]["differenza_euro"] == 5.0
    assert len(alerts) == 1
    assert alerts[0]["tipo"] == "SCOSTAMENTO_ORDINE_FATTURA"
    assert "maggiore di € 5.00" in alerts[0]["descrizione"]


def test_prezzo_regolare_associa_fattura_senza_evidenze(monkeypatch):
    database = AsyncMongoMockClient()["Ordini_Riconciliazione_Regolare_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ordini_fornitori.insert_one({
            "id": "ord-2", "numero_ordine": "ORD-20261013-0002",
            "stato": "inviato_fornitori", "inviato_at": "2026-10-13T09:00:00+00:00",
            "fornitore": "MEPA Alimentari", "prodotti": [{
                "prodotto_id": "cat_IRCA245", "nome": "AMERICAN COOKIES",
                "fornitore": "MEPA Alimentari", "prezzo_ordinato": 50.0,
            }],
        })
        esito = await mod.riconcilia_fattura_con_ordine(
            "MEPA Alimentari",
            [{"codice_articolo": "IRCA245", "descrizione": "AMERICAN COOKIES", "prezzo_unitario": 50.0}],
            "fatt-2", "14/10/2026",
        )
        ordine = await database.ordini_fornitori.find_one({"id": "ord-2"})
        return esito, ordine, await database.alert_prezzi.count_documents({})

    esito, ordine, alerts = run(scenario())
    assert esito["scostamenti_prezzo"] == 0
    assert esito["alert_creato"] is False
    assert ordine["stato"] == "ricevuto"
    assert ordine["riconciliazione"]["ricevuti"][0]["confronto_prezzo"]["stato"] == "regolare"
    assert alerts == 0


def test_nome_solo_simile_non_associa_ordine_e_fattura(monkeypatch):
    database = AsyncMongoMockClient()["Ordini_Riconciliazione_Ambigua_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ordini_fornitori.insert_one({
            "id": "ord-3", "stato": "inviato_fornitori",
            "fornitore": "MEPA Alimentari", "prodotti": [{
                "prodotto_id": "ordine-senza-codice", "nome": "Crema cioccolato fondente",
                "fornitore": "MEPA Alimentari", "prezzo_ordinato": 40.0,
            }],
        })
        return await mod.riconcilia_fattura_con_ordine(
            "MEPA Alimentari",
            [{"descrizione": "Crema cioccolato al latte", "prezzo_unitario": 42.0}],
            "fatt-3", "14/10/2026",
        )

    esito = run(scenario())
    assert esito["ricevuti"] == 0
    assert esito["mancanti"] == 1
    assert esito["scostamenti_prezzo"] == 0
