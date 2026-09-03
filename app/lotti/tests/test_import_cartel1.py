"""Importazione conservativa del ricettario Cartel1.xlsx."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture()
def context(monkeypatch):
    import app.lotti.routers.ricette as module
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    return module, database


def test_file_has_unique_recipes_and_valid_base_links():
    path = Path(__file__).resolve().parent.parent / "data" / "ricette_cartel1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    recipes = payload["recipes"]
    names = {item["nome"].casefold() for item in recipes}

    assert payload["source"]["sha256"] == "4D049B3DC8E849B68B10D0FF32CAEA94E26AAF1EBAED9746174DA56C67B5432C"
    assert len(recipes) == 106
    assert len(names) == 106
    assert sum(item["tipo"] == "base" for item in recipes) == 51
    assert sum(item["tipo"] == "variante" for item in recipes) == 55
    assert all(not item["ricetta_base_nome"] or item["ricetta_base_nome"].casefold() in names for item in recipes)
    assert all("0" not in item["ingredienti"] for item in recipes)


def test_preview_does_not_write(context):
    module, database = context
    run(database.ricette.insert_one({
        "id": "existing-brioche",
        "nome": "brioche",
        "ingredienti": ["Farina 0/man. caputo"],
        "ingredienti_dettaglio": [{"nome": "Farina 0/man. caputo", "quantita": 700, "unita_misura": "g"}],
        "foto_url": "/api/foto/brioche",
        "reparto": "pasticceria",
    }))

    result = run(module.importa_cartel1(anteprima=True, _admin={"nome": "Amministratore"}))

    assert result["anteprima"] is True
    assert result["totale_nel_foglio"] == 106
    assert result["create"] == 105
    assert result["aggiornate"] == 1
    assert run(database.ricette.count_documents({})) == 1
    assert run(database.ricette_import_backup.count_documents({})) == 0


def test_duplicate_current_name_stops_before_writing(context):
    module, database = context
    run(database.ricette.insert_many([
        {"id": "brioche-1", "nome": "Brioche"},
        {"id": "brioche-2", "nome": " brioche "},
    ]))

    with pytest.raises(HTTPException) as error:
        run(module.importa_cartel1(anteprima=False, _admin={"nome": "Amministratore"}))

    assert error.value.status_code == 409
    assert run(database.ricette.count_documents({})) == 2
    assert run(database.ricette_import_backup.count_documents({})) == 0


def test_apply_preserves_photo_quantity_and_is_idempotent(context):
    module, database = context
    run(database.ricette.insert_many([
        {
            "id": "existing-brioche",
            "nome": "brioche",
            "ingredienti": ["Farina 0/man. caputo"],
            "ingredienti_dettaglio": [
                {"nome": "Farina 0/man. caputo", "quantita": 700, "unita_misura": "g", "prodotto_id": "farina-1"}
            ],
            "foto_url": "/api/foto/brioche",
            "reparto": "pasticceria",
        },
        {
            "id": "manual-only",
            "nome": "Ricetta manuale non nel foglio",
            "ingredienti": ["Ingrediente privato"],
            "foto_url": "/api/foto/manuale",
        },
    ]))

    first = run(module.importa_cartel1(anteprima=False, _admin={"nome": "Ceraldi Vincenzo"}))

    assert first["create"] == 105
    assert first["aggiornate"] == 1
    assert first["backup_id"]
    assert run(database.ricette.count_documents({})) == 107
    assert run(database.ricette_import_backup.count_documents({})) == 1

    brioche = run(database.ricette.find_one({"id": "existing-brioche"}))
    assert brioche["foto_url"] == "/api/foto/brioche"
    farina = next(item for item in brioche["ingredienti_dettaglio"] if item["nome"].casefold().startswith("farina"))
    assert farina["quantita"] == 700
    assert farina["unita_misura"] == "g"
    assert farina["prodotto_id"] == "farina-1"
    latte = next(item for item in brioche["ingredienti_dettaglio"] if item["nome"].casefold().startswith("latte"))
    assert latte["quantita"] is None
    assert latte["unita_misura"] == ""

    treccia = run(database.ricette.find_one({"nome": "Treccia"}))
    assert treccia["ricetta_base_id"] == "existing-brioche"
    assert treccia["ricetta_base_nome"] == "brioche"

    manual = run(database.ricette.find_one({"id": "manual-only"}))
    assert manual["foto_url"] == "/api/foto/manuale"
    assert manual["ingredienti"] == ["Ingrediente privato"]

    second = run(module.importa_cartel1(anteprima=False, _admin={"nome": "Ceraldi Vincenzo"}))
    assert second["create"] == 0
    assert second["aggiornate"] == 0
    assert second["invariate"] == 106
    assert second["backup_id"] is None
    assert run(database.ricette_import_backup.count_documents({})) == 1
