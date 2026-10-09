import asyncio

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


def test_anteprima_non_unisce_varianti_e_segnala_composizioni_diverse(monkeypatch):
    from app.lotti.routers import ricette as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    run(database.ricette.insert_many([
        {"id": "p1", "nome": "Peperoni", "ingredienti": ["Peperoni", "Olio", "Sale"]},
        {"id": "p2", "nome": "Peperoni (Base)", "ingredienti": ["Peperoni"]},
        {"id": "v1", "nome": "Peperoni alla caprese", "ingredienti": ["Peperoni", "Mozzarella"]},
        {"id": "x1", "nome": "Pizza", "ingredienti": ["Farina", "Acqua"]},
        {"id": "x2", "nome": "Pizza (Base)", "ingredienti": ["Farina", "Lievito"]},
    ]))

    report = run(mod.deduplica_ricette_base(applica=False, _actor={"nome": "Admin"}))

    assert report["gruppi_da_unire"] == 1
    assert report["ricette_da_eliminare"] == 1
    assert report["gruppi"][0]["mantieni"]["id"] == "p1"
    assert report["gruppi"][0]["elimina"][0]["id"] == "p2"
    assert report["da_verificare"][0]["chiave"] == "pizza"


def test_applicazione_trasferisce_foto_ricollega_varianti_e_conserva_backup(monkeypatch):
    from app.lotti.routers import ricette as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    run(database.ricette.insert_many([
        {"id": "base-completa", "nome": "Arancini", "ingredienti": ["Riso", "Ragu", "Piselli"]},
        {"id": "base-povera", "nome": "Arancini (Base)", "ingredienti": ["Riso"], "foto_url": "/api/foto/arancini"},
        {"id": "variante", "nome": "Arancini funghi", "ricetta_base_id": "base-povera", "ingredienti": ["Riso", "Funghi"]},
    ]))

    report = run(mod.deduplica_ricette_base(applica=True, _actor={"nome": "Admin"}))
    tenuta = run(database.ricette.find_one({"id": "base-completa"}, {"_id": 0}))
    rimossa = run(database.ricette.find_one({"id": "base-povera"}, {"_id": 0}))
    variante = run(database.ricette.find_one({"id": "variante"}, {"_id": 0}))
    cestino = run(database.ricette_cestino.find_one({"ricetta_id": "base-povera"}, {"_id": 0}))
    backup = run(database.ricette_dedup_backup.find_one({"id": report["backup_id"]}, {"_id": 0}))

    assert report["ricette_eliminate"] == 1
    assert report["foto_trasferite"] == 1
    assert tenuta["foto_url"] == "/api/foto/arancini"
    assert rimossa is None
    assert variante["ricetta_base_id"] == "base-completa"
    assert cestino["unita_in"] == "base-completa"
    assert backup["tipo"] == "deduplica_nome_base"
