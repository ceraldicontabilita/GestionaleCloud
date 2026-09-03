import asyncio
import hashlib
import os

import pytest
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


def csv_bytes(*rows):
    header = (
        "AZIONE;ID;Nome_Ricetta;Porzioni;Reparto;Note;Allergeni;"
        "Ingrediente_1;Quantita_1;Unita_1;Ingrediente_2;Quantita_2;Unita_2"
    )
    return ("\n".join((header, *rows)) + "\n").encode("utf-8")


def test_preview_skips_an_existing_normalized_name(context):
    module, database = context
    run(database.ricette.insert_one({"id": "esistente", "nome": "Babà Napoletano al Rum"}))
    payload = csv_bytes(
        "NUOVA;;  BABA NAPOLETANO AL RUM  ;20;pasticceria;Cottura 180°C;Glutine|Uova;Farina;500;g;;;"
    )

    result = run(module.import_csv_ricette(
        file=payload,
        anteprima=True,
        nome_file="ricette_napoletane_extra.csv",
        _admin={"nome": "Ceraldi Vincenzo"},
    ))

    assert result["nuove"] == 0
    assert result["saltate"] == 1
    assert result["dettaglio_saltate"][0]["id_esistente"] == "esistente"
    assert run(database.ricette.count_documents({})) == 1


def test_explicit_matching_name_update_preserves_photo_and_identity(context):
    module, database = context
    run(database.ricette.insert_one({
        "id": "esistente",
        "nome": "Graffa Napoletana",
        "foto_url": "/api/foto/graffa",
        "porzioni": 20,
        "note": "",
    }))
    payload = csv_bytes(
        "NUOVA;;Graffa Napoletana;15;pasticceria;Friggere a 170°C;Glutine|Uova|Latte;Farina;500;g;;;"
    )

    preview = run(module.import_csv_ricette(
        file=payload,
        anteprima=True,
        nome_file="ricette_napoletane_extra.csv",
        aggiorna_omonime=True,
        _admin={"nome": "Ceraldi Vincenzo"},
    ))
    applied = run(module.import_csv_ricette(
        file=payload,
        anteprima=False,
        nome_file="ricette_napoletane_extra.csv",
        aggiorna_omonime=True,
        _admin={"nome": "Ceraldi Vincenzo"},
    ))

    assert preview["nuove"] == 0
    assert preview["aggiornate"] == 1
    assert applied["aggiornate"] == 1
    assert run(database.ricette.count_documents({})) == 1
    saved = run(database.ricette.find_one({"id": "esistente"}, {"_id": 0}))
    assert saved["foto_url"] == "/api/foto/graffa"
    assert saved["porzioni"] == 15
    assert saved["note"] == "Friggere a 170°C"


def test_import_is_idempotent_and_preserves_source_data(context):
    module, database = context
    payload = csv_bytes(
        "NUOVA;;Babà Napoletano al Rum;20;pasticceria;Cottura 180°C;Glutine|Uova|Latte;Farina Manitoba;500;g;Rum;150;ml"
    )
    expected_hash = hashlib.sha256(payload).hexdigest()

    first = run(module.import_csv_ricette(
        file=payload,
        anteprima=False,
        nome_file="ricette_napoletane_extra.csv",
        _admin={"nome": "Ceraldi Vincenzo"},
    ))
    second = run(module.import_csv_ricette(
        file=payload,
        anteprima=False,
        nome_file="ricette_napoletane_extra.csv",
        _admin={"nome": "Ceraldi Vincenzo"},
    ))

    assert first["create"] == 1
    assert second["create"] == 0
    assert run(database.ricette.count_documents({})) == 1
    saved = run(database.ricette.find_one({"nome": "Babà Napoletano al Rum"}, {"_id": 0}))
    assert saved["porzioni"] == 20
    assert saved["reparto"] == "pasticceria"
    assert saved["note"] == "Cottura 180°C"
    assert saved["allergeni"] == ["Glutine", "Uova", "Latte"]
    assert saved["ingredienti_dettaglio"] == [
        {"nome": "Farina Manitoba", "quantita": 500.0, "unita_misura": "g", "unita": "g"},
        {"nome": "Rum", "quantita": 150.0, "unita_misura": "ml", "unita": "ml"},
    ]
    assert saved["provenienza_importazione"] == {
        "tipo": "csv",
        "nome_file": "ricette_napoletane_extra.csv",
        "sha256": expected_hash,
    }


def test_duplicate_name_in_same_file_is_not_created_twice(context):
    module, database = context
    payload = csv_bytes(
        "NUOVA;;Graffa Napoletana;15;pasticceria;Prima versione;Glutine;Farina;500;g;;;",
        "NUOVA;; graffa napoletana ;15;pasticceria;Seconda versione;Glutine;Farina;500;g;;;",
    )

    result = run(module.import_csv_ricette(
        file=payload,
        anteprima=False,
        nome_file="duplicati.csv",
        _admin={"nome": "Ceraldi Vincenzo"},
    ))

    assert result["create"] == 1
    assert run(database.ricette.count_documents({})) == 1
