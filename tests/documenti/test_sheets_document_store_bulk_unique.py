import asyncio

import pytest

from app.services.sheets_document_store import DuplicateRecordError, SheetDatabase


def run(coro):
    return asyncio.run(coro)


def test_insert_many_valida_indici_univoci_senza_scansione_per_riga(monkeypatch):
    database = SheetDatabase("test")
    table = database["pos_transactions"]
    run(table.create_index([("operation_key", 1)], unique=True))
    run(table.insert_many([
        {"operation_key": f"POS-{index}", "payload": {"row": index}}
        for index in range(100)
    ]))

    def fail_per_row(*args, **kwargs):
        raise AssertionError("insert_many non deve usare il controllo O(n) per ogni riga")

    monkeypatch.setattr(table, "_check_unique", fail_per_row)
    result = run(table.insert_many([
        {"operation_key": f"POS-{index}", "payload": {"row": index}}
        for index in range(100, 350)
    ]))

    assert len(result.inserted_ids) == 250
    assert run(table.count_documents({})) == 350


def test_insert_many_rifiuta_duplicato_esistente_e_non_scrive_il_batch():
    database = SheetDatabase("test")
    table = database["pos_transactions"]
    run(table.create_index([("operation_key", 1)], unique=True))
    run(table.insert_one({"operation_key": "POS-1"}))

    with pytest.raises(DuplicateRecordError):
        run(table.insert_many([
            {"operation_key": "POS-2"},
            {"operation_key": "POS-1"},
        ]))

    assert run(table.count_documents({})) == 1


def test_insert_many_rifiuta_duplicato_nello_stesso_batch():
    database = SheetDatabase("test")
    table = database["pos_transactions"]
    run(table.create_index([("operation_key", 1)], unique=True))

    with pytest.raises(DuplicateRecordError):
        run(table.insert_many([
            {"operation_key": "POS-1"},
            {"operation_key": "POS-1"},
        ]))

    assert run(table.count_documents({})) == 0


def test_insert_many_rispetta_indice_sparse_e_valori_annidati():
    database = SheetDatabase("test")
    table = database["pos_transactions"]
    run(table.create_index([("external", 1)], unique=True, sparse=True))

    run(table.insert_many([
        {"description": "senza chiave"},
        {"description": "ancora senza chiave"},
        {"external": {"date": "2026-07-01", "amount": [10, 20]}},
    ]))

    with pytest.raises(DuplicateRecordError):
        run(table.insert_many([
            {"external": {"amount": [10, 20], "date": "2026-07-01"}},
        ]))


def test_in_query_gestisce_valori_scalari_e_array():
    database = SheetDatabase("test")
    table = database["records"]
    run(table.insert_many([
        {"id": "one", "key": "A", "tags": ["x", "y"]},
        {"id": "two", "key": "B", "tags": ["z"]},
    ]))

    by_key = run(
        table.find(
            {"key": {"$in": ["B", "C"]}}, {"_id": 0, "id": 1},
        ).to_list(10)
    )
    by_tag = run(
        table.find(
            {"tags": {"$in": ["y"]}}, {"_id": 0, "id": 1},
        ).to_list(10)
    )

    assert by_key == [{"id": "two"}]
    assert by_tag == [{"id": "one"}]
