import asyncio
import json
import os
from pathlib import Path

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import ingredienti, lotti_fornitori, saima_ricettari as mod
from app.lotti.scripts.genera_ricette_saima import _parse_ingredients

_TEST_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_TEST_LOOP)


def run(coro):
    return _TEST_LOOP.run_until_complete(coro)


def source_bundle():
    path = Path(mod.__file__).resolve().parent.parent / "data" / "ricette_saima.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_tutti_i_ricettari_ufficiali_hanno_url_correnti_e_bundle():
    assert len(mod.RICETTARI_APPLICAZIONI) == 19
    urls = {item["id"]: item["url_pdf"] for item in mod.RICETTARI_APPLICAZIONI}
    assert urls["croissant-ricettario"].endswith("/2023/07/Ricettario-Croissant.pdf")
    assert urls["waldkorn-ricettario"].endswith("/2024/11/Ricettario-Waldkorn.pdf")
    bundle = source_bundle()
    assert bundle["meta"]["totale_ricettari"] == 19
    assert bundle["meta"]["totale_ricette"] >= 120
    assert len(bundle["ricette"]) == bundle["meta"]["totale_ricette"]
    assert all(item.get("pagina_fonte") for item in bundle["ricette"])
    assert any(item["nome"].lower().startswith("croissant") for item in bundle["ricette"])


def test_bundle_saima_assegna_dolci_e_salati_ai_reparti_corretti():
    items = {item["nome"]: item for item in source_bundle()["ricette"]}
    assert items["Caprese Al Limone"]["reparto"] == "pasticceria"
    assert items["Mela E Cannella"]["reparto"] == "pasticceria"
    assert items["Ciabatta Al Vino Rosso"]["reparto"] == "rosticceria"
    assert items["Grissini Al Vino"]["reparto"] == "rosticceria"


def test_dosi_italiane_con_punto_migliaia_non_diventano_decimali():
    rows = _parse_ingredients("Uova 1.300 g\nLatte 1,5 l")
    assert rows[0]["quantita"] == 1300
    assert rows[1]["quantita"] == 1.5


def test_disponibilita_usa_la_chiave_canonica_unica(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    monkeypatch.setattr(lotti_fornitori, "db", database)
    monkeypatch.setattr(ingredienti, "db", database)

    async def scenario():
        await database.ricette.insert_one({
            "id": "ricetta-interna-baccala",
            "nome": "Baccalà alla Napoletana",
            "porzioni": 1,
            "ingredienti_dettaglio": [
                {"nome": "Olio di arachidi per friggere", "quantita": 500, "unita_misura": "ml"},
                {"nome": "Prezzemolo fresco", "quantita": 10, "unita_misura": "g"},
                {"nome": "Capperi sotto sale", "quantita": 20, "unita_misura": "g"},
                {"nome": "Mèlange perfetto Gateaux", "quantita": 500, "unita_misura": "g"},
            ],
        })
        await database.lotti_fornitori.insert_many([
            {"id": "o1", "prodotto_nome": "Olio di girasole", "quantita_disponibile": 2, "unita_misura": "L", "fornitore": "Fornitore A", "esaurito": False},
            {"id": "p1", "prodotto_nome": "Prezzemolo", "quantita_disponibile": 100, "unita_misura": "g", "fornitore": "Fornitore A", "esaurito": False},
            {"id": "c1", "prodotto_nome": "Capperi", "quantita_disponibile": 100, "unita_misura": "g", "fornitore": "Fornitore A", "esaurito": False},
            {"id": "b1", "prodotto_nome": "Burro classico", "quantita_disponibile": 5, "unita_misura": "KG", "fornitore": "Fornitore A", "esaurito": False},
        ])
        return await mod.verifica_disponibilita_ricetta(
            "ricetta-interna-baccala", mod.VerificaDisponibilitaPayload(pezzi=1)
        )

    out = run(scenario())
    rows = {item["ingrediente"]: item for item in out["righe"]}
    assert rows["Olio di arachidi per friggere"]["stato"] == "disponibile"
    assert rows["Olio di arachidi per friggere"]["prodotto"]["nome"] == "Olio di girasole"
    assert rows["Prezzemolo fresco"]["stato"] == "disponibile"
    assert rows["Prezzemolo fresco"]["prodotto"]["nome"] == "Prezzemolo"
    assert rows["Capperi sotto sale"]["stato"] == "disponibile"
    assert rows["Capperi sotto sale"]["prodotto"]["nome"] == "Capperi"
    assert rows["Mèlange perfetto Gateaux"]["stato"] == "da_acquistare"
    assert not rows["Mèlange perfetto Gateaux"]["alternative"]
    assert out["totali"] == {"disponibili": 3, "sostituibili": 0, "da_acquistare": 1}


def test_ricettari_fornitore_non_scrivono_nelle_ricette_interne(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        listed = await mod.get_ricettari()
        return listed, await database.ricette.count_documents({})

    listed, count = run(scenario())
    assert len(listed) == 19
    assert count == 0
    assert not any(route.path.endswith("/importa-ricette") for route in mod.router.routes)


def test_lista_spesa_aggiunge_solo_veri_mancanti(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    monkeypatch.setattr(lotti_fornitori, "db", database)
    monkeypatch.setattr(ingredienti, "db", database)

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
