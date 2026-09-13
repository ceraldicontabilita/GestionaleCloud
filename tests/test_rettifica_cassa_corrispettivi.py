import asyncio

from app.services.rettifica_cassa_corrispettivi import analizza, applica
from app.services.sheets_document_store import MemorySheetsClient


def _run(value):
    return asyncio.run(value)


def _db():
    db = MemorySheetsClient()["rettifica-cassa"]
    _run(db["corrispettivi"].insert_many([
        {"id": "corr-1", "data": "2026-08-03", "totale": 2181.40,
         "pagato_contanti": 551.90, "pagato_elettronico": 1629.50},
        {"id": "corr-2", "data": "2026-08-04", "totale": 100.0,
         "pagato_contanti": 30.0, "pagato_elettronico": 70.0},
        {"id": "corr-amb", "data": "2026-08-05", "totale": 50.0},
    ]))
    _run(db["prima_nota_cassa"].insert_many([
        {"id": "pn-1", "corrispettivo_id": "corr-1", "data": "2026-08-03",
         "tipo": "entrata", "categoria": "Corrispettivi", "importo": 2181.40},
        {"id": "pn-2", "corrispettivo_id": "corr-2", "data": "2026-08-04",
         "tipo": "entrata", "categoria": "Corrispettivi", "importo": 30.0},
        {"id": "pn-amb", "corrispettivo_id": "corr-amb", "data": "2026-08-05",
         "tipo": "entrata", "categoria": "Corrispettivi", "importo": 50.0},
    ]))
    return db


def test_anteprima_non_scrive_e_separa_ambigui():
    db = _db()
    out = _run(analizza(db, 2026))
    assert out["da_rettificare"] == 1
    assert out["gia_corrette"] == 1
    assert out["da_verificare"] == 1
    assert _run(db["prima_nota_cassa"].find_one({"id": "pn-1"}))["importo"] == 2181.40


def test_applica_preserva_originale_audit_e_link_bidirezionale():
    db = _db()
    out = _run(applica(db, 2026, {"sub": "tester"}))
    row = _run(db["prima_nota_cassa"].find_one({"id": "pn-1"}))
    corr = _run(db["corrispettivi"].find_one({"id": "corr-1"}))
    audit = _run(db["rettifiche_contabili_audit"].find_one(
        {"prima_nota_cassa_id": "pn-1"}))
    assert out["righe_rettificate"] == 1
    assert row["importo"] == 551.90
    assert row["rettifica_cassa_originale"]["importo"] == 2181.40
    assert corr["prima_nota_cassa_id"] == "pn-1"
    assert audit["corrispettivo_id"] == "corr-1"
    assert out["cancellazioni"] == 0


def test_seconda_esecuzione_non_duplica_e_non_rettifica():
    db = _db()
    _run(applica(db, 2026))
    second = _run(applica(db, 2026))
    assert second["righe_rettificate"] == 0
    assert second["audit_creati"] == 0
    assert _run(db["rettifiche_contabili_audit"].count_documents({})) == 1


def test_non_usa_data_o_importo_per_associare():
    db = _db()
    _run(db["prima_nota_cassa"].insert_one({
        "id": "senza-link", "data": "2026-08-03", "tipo": "entrata",
        "categoria": "Corrispettivi", "importo": 2181.40,
    }))
    _run(applica(db, 2026))
    row = _run(db["prima_nota_cassa"].find_one({"id": "senza-link"}))
    assert row["importo"] == 2181.40
    assert "rettifica_cassa_originale" not in row
