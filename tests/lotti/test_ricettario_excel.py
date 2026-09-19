import asyncio
import os

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import ricette as mod

_TEST_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_TEST_LOOP)


def run(coro):
    return _TEST_LOOP.run_until_complete(coro)


def _bundle_minimo():
    return {
        "meta": {
            "bundle_sha256": "bundle-test",
            "sources": [{"file": f"fonte-{i}.xlsx"} for i in range(4)],
            "con_ingredienti": 2,
            "con_preparazione": 2,
        },
        "recipes": [
            {
                "chiave": "baba",
                "nome": "Babà",
                "reparto_hint": "pasticceria",
                "porzioni": 20,
                "ingredienti_dettaglio": [
                    {"nome": "Farina Manitoba", "quantita": 1000, "unita_misura": "g"},
                    {"nome": "Uova", "quantita": 12, "unita_misura": "pz"},
                ],
                "procedimento_testo": "Impastare e lasciare lievitare.",
                "note": "Ricetta laboratorio",
                "fonti_excel": [{"file": "fonte-1.xlsx", "sheet": "Babà", "row": 1}],
            },
            {
                "chiave": "savoiardi",
                "nome": "Savoiardi",
                "reparto_hint": "pasticceria",
                "porzioni": 30,
                "ingredienti_dettaglio": [
                    {"nome": "Albumi", "quantita": 180, "unita_misura": "g"},
                ],
                "procedimento_testo": "Montare e cuocere.",
                "note": "",
                "fonti_excel": [{"file": "fonte-2.xlsx", "sheet": "Savoiardi", "row": 1}],
            },
        ],
    }


def test_bundle_reale_contiene_le_quattro_fonti_e_le_preparazioni():
    bundle = mod._carica_ricettario_excel()
    assert len(bundle["meta"]["sources"]) == 4
    assert bundle["meta"]["ricette_uniche"] == 574
    assert bundle["meta"]["con_ingredienti"] == 535
    assert bundle["meta"]["con_preparazione"] == 306
    assert len(bundle["recipes"]) == 574


def test_import_idempotente_e_non_sovrascrive_ingredienti_manualizzati(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    monkeypatch.setattr(mod, "_carica_ricettario_excel", _bundle_minimo)

    async def scenario():
        await database.ricette.insert_one({
            "id": "manuale-baba",
            "nome": "Babà",
            "fonte": "manuale",
            "ingredienti": ["Farina personale"],
            "ingredienti_dettaglio": [
                {"nome": "Farina personale", "quantita": 777, "unita_misura": "g"},
            ],
            "porzioni": 10,
        })
        first = await mod._importa_ricettario_excel(False, {"nome": "Admin"})
        second = await mod._importa_ricettario_excel(False, {"nome": "Admin"})
        baba = await database.ricette.find_one({"id": "manuale-baba"}, {"_id": 0})
        savoiardi = await database.ricette.find_one({"nome": "Savoiardi"}, {"_id": 0})
        backups = await database.ricette_import_backup.count_documents({})
        return first, second, baba, savoiardi, backups

    first, second, baba, savoiardi, backups = run(scenario())
    assert first["create"] == 1
    assert first["aggiornate"] == 1
    assert second["create"] == 0
    assert second["aggiornate"] == 0
    assert second["invariate"] == 2
    assert baba["ingredienti_dettaglio"][0]["nome"] == "Farina personale"
    assert baba["procedimento_testo"] == "Impastare e lasciare lievitare."
    assert savoiardi["ingredienti_dettaglio"][0]["quantita"] == 180
    assert backups == 1


def test_eliminazione_salva_copia_recuperabile(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette.insert_one({"id": "r1", "nome": "Ricetta prova", "foto_url": "/foto.jpg"})
        result = await mod.delete_ricetta("r1", {"nome": "Admin"})
        live = await database.ricette.find_one({"id": "r1"})
        trash = await database.ricette_cestino.find_one({"ricetta_id": "r1"}, {"_id": 0})
        return result, live, trash

    result, live, trash = run(scenario())
    assert result["recuperabile"] is True
    assert live is None
    assert trash["ricetta"]["foto_url"] == "/foto.jpg"
    assert trash["eliminata_da"] == "Admin"
