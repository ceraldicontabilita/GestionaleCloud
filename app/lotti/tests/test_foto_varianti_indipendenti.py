import asyncio
import os

from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")


def run(coro):
    return asyncio.run(coro)


def test_creazione_variante_clona_foto_in_un_id_autonomo(monkeypatch):
    import app.lotti.routers.ricette as module
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    run(database.ricette.insert_one({
        "id": "base-coda", "nome": "Coda di aragosta",
        "foto_url": "/api/foto/foto-base?v=1", "reparto": "pasticceria",
    }))
    run(database.foto_files.insert_one({
        "_id": "foto-base", "mime": "image/webp", "data": b"foto-base",
    }))

    created = run(module.create_ricetta(module.RicettaCreate(
        nome="Coda di aragosta al pistacchio",
        reparto="pasticceria",
        ricetta_base_id="base-coda",
        ricetta_base_nome="Coda di aragosta",
    )))

    assert created["foto_url"].startswith("/api/foto/ricetta_")
    assert "foto-base" not in created["foto_url"]
    photo_id = module._foto_id_da_url(created["foto_url"])
    photo = run(database.foto_files.find_one({"_id": photo_id}))
    assert photo["data"] == b"foto-base"
    assert photo["ricetta_id"] == created["id"]
    assert photo["copiata_da_foto_id"] == "foto-base"


def test_migrazione_separa_solo_varianti_che_usano_la_base(monkeypatch):
    import app.lotti.routers.ricette as module
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    run(database.ricette.insert_many([
        {"id": "base", "nome": "Base", "foto_url": "/api/foto/base-photo?v=1"},
        {"id": "v-senza", "nome": "Variante senza", "ricetta_base_id": "base"},
        {"id": "v-condivisa", "nome": "Variante condivisa", "ricetta_base_id": "base", "foto_url": "/api/foto/base-photo?v=1"},
        {"id": "v-propria", "nome": "Variante propria", "ricetta_base_id": "base", "foto_url": "/api/foto/own-photo?v=1"},
    ]))
    run(database.foto_files.insert_many([
        {"_id": "base-photo", "mime": "image/jpeg", "data": b"base"},
        {"_id": "own-photo", "mime": "image/jpeg", "data": b"own"},
    ]))

    preview = run(module.separa_foto_varianti(applica=False, _admin={"nome": "Admin"}))
    assert preview["da_separare"] == 2
    applied = run(module.separa_foto_varianti(applica=True, _admin={"nome": "Admin"}))
    assert applied["aggiornate"] == 2
    assert applied["backup_id"]
    assert run(database.ricette.find_one({"id": "v-propria"}))["foto_url"] == "/api/foto/own-photo?v=1"
    assert module._foto_id_da_url(run(database.ricette.find_one({"id": "v-senza"}))["foto_url"]) != "base-photo"
    assert run(database.ricette_foto_backup.count_documents({})) == 1
