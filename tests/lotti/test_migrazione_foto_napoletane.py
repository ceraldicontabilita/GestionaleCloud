import asyncio
import hashlib
import json

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import migrazione_foto_napoletane as migrazione


def run(coro):
    return asyncio.run(coro)


def test_migrazione_usa_solo_id_esatti_ed_e_idempotente(monkeypatch, tmp_path):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    asset = tmp_path / "sfogliatella.png"
    asset.write_bytes(b"png-canonico")
    mapping = tmp_path / "mappatura.json"
    mapping.write_text(json.dumps([{
        "id": "ricetta-esatta",
        "file": str(asset),
        "sostituisci_esistente": True,
    }]), encoding="utf-8")
    monkeypatch.setattr(migrazione, "MAPPATURA", mapping)
    run(database.ricette.insert_one({
        "id": "ricetta-esatta", "nome": "Nome irrilevante",
        "foto_sha256": "vecchio", "foto_source": "upload_manuale",
    }))
    chiamate = []

    async def upload_foto(ricetta_id, file, foto_source, cestina_precedente):
        contenuto = await file.read()
        digest = hashlib.sha256(contenuto).hexdigest()
        chiamate.append((ricetta_id, file.filename, foto_source, cestina_precedente))
        await database.ricette.update_one({"id": ricetta_id}, {"$set": {
            "foto_sha256": digest, "foto_source": foto_source,
        }})
        return {
            "foto_sha256": digest, "foto_url": "/api/foto/nuova",
            "backup_id": "backup-1", "foto_precedente_cestinata": True,
            "menu_sync": {"esito": "aggiornato"},
        }

    import app.lotti.routers.ricette as ricette
    monkeypatch.setattr(ricette, "upload_foto", upload_foto)
    async def sincronizza_menu(_ricetta_id):
        return {"esito": "aggiornato"}
    monkeypatch.setattr(ricette, "_sincronizza_menu", sincronizza_menu)
    monkeypatch.setattr(ricette, "db", database)

    primo = run(migrazione.migra_foto_napoletane(database))
    secondo = run(migrazione.migra_foto_napoletane(database))

    assert primo["stato"] == "completata"
    assert primo["caricate"] == 1 and primo["errori"] == []
    assert secondo["gia_completata"] is True
    assert chiamate == [(
        "ricetta-esatta", "sfogliatella.png",
        "catalogo_napoletano_verificato", True,
    )]


def test_migrazione_non_inventa_ricette_mancanti(monkeypatch, tmp_path):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    asset = tmp_path / "foto.png"
    asset.write_bytes(b"foto")
    mapping = tmp_path / "mappatura.json"
    mapping.write_text(json.dumps([{
        "id": "ricetta-assente", "file": str(asset),
    }]), encoding="utf-8")
    monkeypatch.setattr(migrazione, "MAPPATURA", mapping)

    esito = run(migrazione.migra_foto_napoletane(database))

    assert esito["stato"] == "errore"
    assert esito["caricate"] == 0
    assert esito["errori"][0]["id"] == "ricetta-assente"
    assert run(database.ricette.count_documents({})) == 0


def test_migrazione_riprova_il_menu_quando_la_foto_e_gia_canonica(monkeypatch, tmp_path):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    asset = tmp_path / "foto.png"
    asset.write_bytes(b"foto-canonica")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    mapping = tmp_path / "mappatura.json"
    mapping.write_text(json.dumps([{
        "id": "ricetta-esatta", "file": str(asset),
    }]), encoding="utf-8")
    monkeypatch.setattr(migrazione, "MAPPATURA", mapping)
    run(database.ricette.insert_one({
        "id": "ricetta-esatta", "foto_sha256": digest,
        "foto_source": "catalogo_napoletano_verificato",
    }))

    import app.lotti.routers.ricette as ricette
    esiti = iter([
        {"esito": "errore", "errore": "storage temporaneamente indisponibile"},
        {"esito": "aggiornato"},
    ])
    chiamate = []

    async def sincronizza_menu(ricetta_id):
        chiamate.append(ricetta_id)
        return next(esiti)

    async def upload_foto(*_args, **_kwargs):
        raise AssertionError("La foto canonica non deve essere ricaricata")

    monkeypatch.setattr(ricette, "_sincronizza_menu", sincronizza_menu)
    monkeypatch.setattr(ricette, "upload_foto", upload_foto)
    monkeypatch.setattr(ricette, "db", database)

    primo = run(migrazione.migra_foto_napoletane(database))
    secondo = run(migrazione.migra_foto_napoletane(database))

    assert primo["stato"] == "errore"
    assert secondo["stato"] == "completata"
    assert secondo["gia_presenti"] == 1
    assert chiamate == ["ricetta-esatta", "ricetta-esatta"]
