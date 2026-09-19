import asyncio
import os
from pathlib import Path

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import saima_ricettari as mod
from app.lotti.scripts.genera_ricette_saima import _parse_ingredients

_TEST_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_TEST_LOOP)


def run(coro):
    return _TEST_LOOP.run_until_complete(coro)


def test_tutti_i_ricettari_ufficiali_hanno_url_correnti_e_bundle():
    assert len(mod.RICETTARI_APPLICAZIONI) == 19
    urls = {item["id"]: item["url_pdf"] for item in mod.RICETTARI_APPLICAZIONI}
    assert urls["croissant-ricettario"].endswith("/2023/07/Ricettario-Croissant.pdf")
    assert urls["waldkorn-ricettario"].endswith("/2024/11/Ricettario-Waldkorn.pdf")
    bundle = mod._bundle_saima()
    assert bundle["meta"]["totale_ricettari"] == 19
    assert bundle["meta"]["totale_ricette"] >= 120
    assert len(bundle["ricette"]) == bundle["meta"]["totale_ricette"]
    assert all(item.get("pagina_fonte") for item in bundle["ricette"])
    assert any(item["nome"].lower().startswith("croissant") for item in bundle["ricette"])
    assert Path(mod._BUNDLE_RICETTE).exists()


def test_dosi_italiane_con_punto_migliaia_non_diventano_decimali():
    rows = _parse_ingredients("Uova 1.300 g\nLatte 1,5 l")
    assert rows[0]["quantita"] == 1300
    assert rows[1]["quantita"] == 1.5


def test_sostituzioni_solo_nella_stessa_famiglia(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette.insert_one({
            "id": "saima:test:croissant",
            "nome": "Croissant pistacchio",
            "porzioni": 40,
            "ingredienti_dettaglio": [
                {"nome": "Lievito di birra", "quantita": 40, "unita_misura": "g"},
                {"nome": "Mèlange perfetto Gateaux", "quantita": 500, "unita_misura": "g"},
                {"nome": "Acqua", "quantita": 450, "unita_misura": "g"},
                {"nome": "Pasta mandarino tardivo", "quantita": 50, "unita_misura": "g"},
            ],
        })
        await database.lotti_fornitori.insert_many([
            {"id": "b1", "prodotto_nome": "Burro classico", "prodotto_nome_norm": "burro classico", "quantita_disponibile": 5, "unita_misura": "KG", "fornitore": "Fornitore A", "esaurito": False},
            {"id": "a1", "prodotto_nome": "Aroma arancia", "prodotto_nome_norm": "aroma arancia", "quantita_disponibile": 2, "unita_misura": "KG", "fornitore": "Fornitore B", "esaurito": False},
            {"id": "a2", "prodotto_nome": "Aroma zuppa inglese", "prodotto_nome_norm": "aroma zuppa inglese", "quantita_disponibile": 1, "unita_misura": "KG", "fornitore": "Fornitore B", "esaurito": False},
        ])
        return await mod.verifica_disponibilita_ricetta(
            "saima:test:croissant", mod.VerificaDisponibilitaPayload(pezzi=80)
        )

    out = run(scenario())
    rows = {item["ingrediente"]: item for item in out["righe"]}
    assert rows["Acqua"]["stato"] == "disponibile"
    assert rows["Lievito di birra"]["stato"] == "da_acquistare"
    assert not rows["Lievito di birra"]["alternative"]
    assert rows["Mèlange perfetto Gateaux"]["stato"] == "sostituibile"
    assert rows["Mèlange perfetto Gateaux"]["alternative"][0]["nome"] == "Burro classico"
    assert rows["Pasta mandarino tardivo"]["stato"] == "sostituibile"
    assert any("arancia" in item["nome"].lower() for item in rows["Pasta mandarino tardivo"]["alternative"])
    assert rows["Lievito di birra"]["richiesta"]["valore"] == 80


def test_import_bundle_e_idempotente(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        first = await mod._importa_bundle_saima()
        await database.ricette.update_one(
            {"id": "saima:croissant-ricettario:croissant-oreo:p5"},
            {"$set": {"porzioni": 42}},
        )
        second = await mod._importa_bundle_saima()
        edited = await database.ricette.find_one({"id": "saima:croissant-ricettario:croissant-oreo:p5"})
        return first, second, edited, await database.ricette.count_documents({})

    first, second, edited, count = run(scenario())
    assert first["inserite"] == first["totale_bundle"]
    assert second["inserite"] == 0
    assert count == first["totale_bundle"]
    assert edited["porzioni"] == 42
    assert edited["visibile_tablet"] is False
    assert edited["ricetta_operativa"] is False


def test_lista_spesa_aggiunge_solo_veri_mancanti(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette.insert_one({
            "id": "saima:test:semplice", "nome": "Impasto",
            "ingredienti_dettaglio": [
                {"nome": "Lievito di birra", "quantita": 30, "unita_misura": "g"},
                {"nome": "Acqua", "quantita": 500, "unita_misura": "g"},
            ],
        })
        first = await mod.aggiungi_mancanti_carrello("saima:test:semplice", mod.ListaSpesaPayload())
        second = await mod.aggiungi_mancanti_carrello("saima:test:semplice", mod.ListaSpesaPayload())
        saved = await database.carrello_sospesi.find_one({"_id": "default"})
        return first, second, saved

    first, second, saved = run(scenario())
    assert first["aggiunti"] == 1
    assert second["aggiunti"] == 0
    assert len(saved["righe"]) == 1
    assert saved["righe"][0]["nome"] == "Lievito di birra"
    assert saved["righe"][0]["prezzo"] == 0
