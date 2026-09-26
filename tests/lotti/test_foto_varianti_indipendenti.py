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
        "foto_source": "catalogo_napoletano_verificato",
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
    assert photo["fonte"] == "catalogo_napoletano_verificato"
    assert created["foto_source"] == "catalogo_napoletano_verificato"


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


def test_variante_di_una_ricetta_con_foto_su_storage_riceve_una_copia_su_storage(monkeypatch):
    """Una base con foto su Supabase Storage non lascia la variante senza foto."""
    import app.lotti.routers.ricette as module
    from app.lotti.servizi import supabase_foto_ricette

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    archivio = {"lotti/ricette/base.webp": b"foto-storage"}

    def leggi(percorso):
        return archivio[percorso]

    def carica(*, ricetta_id, contenuto, mime, filename=None):
        percorso = f"lotti/ricette/{ricetta_id}-copia.webp"
        archivio[percorso] = contenuto
        return {"id": f"{ricetta_id}-copia", "bucket": "menu-images", "path": percorso,
                "sha256": "x", "filename": filename}

    monkeypatch.setattr(supabase_foto_ricette, "leggi", leggi)
    monkeypatch.setattr(supabase_foto_ricette, "carica", carica)
    run(database.ricette.insert_one({
        "id": "base", "nome": "Babà", "reparto": "pasticceria",
        "foto_url": "/api/foto/base-storage?v=1", "foto_id": "base-storage",
        "foto_storage_path": "lotti/ricette/base.webp", "foto_content_type": "image/webp",
        "foto_filename": "baba.webp",
    }))
    run(database.ricette.insert_one({"id": "variante", "nome": "Babà al limone"}))

    foto_url = run(module._clona_foto_tra_ricette("base", "variante", fonte="test"))

    assert foto_url.startswith("/api/foto/variante-copia?v=")
    variante = run(database.ricette.find_one({"id": "variante"}))
    assert variante["foto_storage_path"] == "lotti/ricette/variante-copia.webp"
    assert variante["foto_content_type"] == "image/webp"
    assert "foto_drive_id" not in variante
    assert archivio["lotti/ricette/variante-copia.webp"] == b"foto-storage"
