import asyncio
import hashlib

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


def test_collega_asset_una_sola_volta_e_non_duplica(monkeypatch, tmp_path):
    from app.lotti.servizi import foto_ricette_generate as module

    database = AsyncMongoMockClient()["Gestionale_Test"]
    run(database.ricette.insert_one({
        "id": "r-tramezzino",
        "nome": "Tramezzino al Prosciutto",
        "foto_url": "/api/foto/vecchia",
    }))
    asset = tmp_path / "tramezzino.png"
    asset.write_bytes(b"png-con-alpha")
    monkeypatch.setattr(module, "ASSET_DIR", tmp_path)
    chiamate_menu = []

    async def sync(ricetta_id):
        chiamate_menu.append(ricetta_id)
        return {"esito": "aggiornato"}

    manifest = (("Tramezzino al Prosciutto", "tramezzino.png"),)
    prima = run(module.collega_illustrazioni_generate(database, sync, manifest))
    seconda = run(module.collega_illustrazioni_generate(database, sync, manifest))

    assert len(prima["collegate"]) == 1
    assert seconda["gia_applicate"] == ["Tramezzino al Prosciutto"]
    assert chiamate_menu == ["r-tramezzino"]
    assert run(database.foto_files.count_documents({})) == 1
    salvata = run(database.ricette.find_one({"id": "r-tramezzino"}))
    assert salvata["foto_source"] == "illustrazione_ai"
    assert salvata["foto_sha256"] == hashlib.sha256(b"png-con-alpha").hexdigest()


def test_nome_assente_resta_in_attesa_senza_scritture(monkeypatch, tmp_path):
    from app.lotti.servizi import foto_ricette_generate as module

    database = AsyncMongoMockClient()["Gestionale_Test"]
    (tmp_path / "bagna.png").write_bytes(b"bagna")
    monkeypatch.setattr(module, "ASSET_DIR", tmp_path)

    esito = run(module.collega_illustrazioni_generate(
        database,
        manifest=(("Bagna Curitiba", "bagna.png"),),
    ))

    assert esito["in_attesa"] == [{"nome": "Bagna Curitiba", "motivo": "ricetta assente"}]
    assert run(database.foto_files.count_documents({})) == 0
    assert run(database.sistema_stato.count_documents({})) == 0


def test_errore_menu_non_marca_completato_e_viene_ritentato(monkeypatch, tmp_path):
    from app.lotti.servizi import foto_ricette_generate as module

    database = AsyncMongoMockClient()["Gestionale_Test"]
    run(database.ricette.insert_one({"id": "r-curitiba", "nome": "CURITIBA"}))
    (tmp_path / "curitiba.png").write_bytes(b"curitiba")
    monkeypatch.setattr(module, "ASSET_DIR", tmp_path)
    tentativi = []

    async def sync(ricetta_id):
        tentativi.append(ricetta_id)
        return {"esito": "errore", "errore": "menu non disponibile"}

    manifest = (("CURITIBA", "curitiba.png"),)
    prima = run(module.collega_illustrazioni_generate(database, sync, manifest))
    seconda = run(module.collega_illustrazioni_generate(database, sync, manifest))

    assert len(prima["errori_menu"]) == len(seconda["errori_menu"]) == 1
    assert tentativi == ["r-curitiba", "r-curitiba"]
    assert run(database.foto_files.count_documents({})) == 1
    assert run(database.sistema_stato.count_documents({})) == 0
