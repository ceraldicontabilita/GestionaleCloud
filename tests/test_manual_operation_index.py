import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.database import Database
from app.db_collections import (
    COLL_BANK_OPERATION_INDEX,
    COLL_ENTITY_RELATIONS,
    COLL_ESTRATTO_CONTO,
)
from app.routers.prima_nota_module.operation_index import (
    ManualIndexDecisionIn,
    list_manual_operation_candidates,
    list_manual_operation_index,
    save_manual_operation_decision,
)


USER = {"user_id": "operatore-test", "email": "operatore@example.test"}


def run(coro):
    return asyncio.run(coro)


def test_indice_elenca_la_fonte_senza_generare_proposte_o_scritture():
    db = AsyncMongoMockClient()["manual-operation-index-list"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({
        "id": "mov-1",
        "data": "2026-08-03",
        "tipo": "uscita",
        "importo": "1500,00",
        "descrizione": "STIPENDIO CERALDI VALERIO LUGLIO 2026",
        "fingerprint": "fp-mov-1",
    }))

    with patch.object(Database, "get_db", return_value=db):
        result = run(list_manual_operation_index(
            anno=2026, tipo=None, stato=None, search="", limit=100, offset=0, _user=USER,
        ))

    assert result["automation"] == "disabled_for_manual_index"
    assert result["total_rows"] == 1
    assert result["rows"][0]["index_status"] == "da_classificare"
    assert result["rows"][0]["amount_cents"] == 150000
    assert {item["id"] for item in result["categories"]} >= {
        "fornitore", "fattura", "cedolino", "f24", "noleggio", "verbale", "altro",
    }
    assert run(db[COLL_BANK_OPERATION_INDEX].count_documents({})) == 0


def test_indice_include_anche_un_movimento_storico_con_solo_object_id():
    db = AsyncMongoMockClient()["manual-operation-index-object-id"]
    inserted = run(db[COLL_ESTRATTO_CONTO].insert_one({
        "data": "2026-08-02",
        "tipo": "uscita",
        "importo": "10,00",
        "descrizione": "IMPORT STORICO SENZA ID APPLICATIVO",
    }))

    with patch.object(Database, "get_db", return_value=db):
        listing = run(list_manual_operation_index(
            anno=2026, tipo=None, stato=None, search="", limit=100, offset=0, _user=USER,
        ))
        saved = run(save_manual_operation_decision(
            str(inserted.inserted_id),
            ManualIndexDecisionIn(category="altro", note="Classificazione manuale", expected_version=0),
            USER,
        ))

    assert listing["rows"][0]["id"] == str(inserted.inserted_id)
    assert saved["source_unchanged"] is True
    assert saved["decision"]["movement_id"] == str(inserted.inserted_id)


def test_scelta_manual_invoice_crea_indice_e_relazione_ma_non_marca_pagato():
    db = AsyncMongoMockClient()["manual-operation-index-save"]
    source = {
        "id": "mov-invoice",
        "data": "2026-08-03",
        "tipo": "uscita",
        "importo": 832.25,
        "descrizione": "SDD ARVAL SERVICE LEASE ITALIA SPA",
        "fingerprint": "fp-arval",
        "riconciliato": False,
    }
    run(db[COLL_ESTRATTO_CONTO].insert_one(source.copy()))
    run(db["invoices"].insert_one({
        "id": "invoice-arval",
        "supplier_name": "ARVAL SERVICE LEASE ITALIA SPA",
        "invoice_number": "FT0014095324",
        "invoice_date": "2026-06-11",
        "total_amount": 832.25,
    }))

    with patch.object(Database, "get_db", return_value=db):
        result = run(save_manual_operation_decision(
            "mov-invoice",
            ManualIndexDecisionIn(category="fattura", target_id="invoice-arval", expected_version=0),
            USER,
        ))

    assert result["saved"] is True
    assert result["source_unchanged"] is True
    assert result["payment_status_changed"] is False
    decision = run(db[COLL_BANK_OPERATION_INDEX].find_one({"movement_id": "mov-invoice"}))
    assert decision["category"] == "fattura"
    assert decision["target_label"] == "ARVAL SERVICE LEASE ITALIA SPA - fattura FT0014095324"
    assert decision["amount_cents"] == 83225
    relation = run(db[COLL_ENTITY_RELATIONS].find_one({"relation_key": result["relation_key"]}))
    assert relation["status"] == "confirmed"
    assert relation["source"] == {"type": "bank_movement", "id": "mov-invoice"}
    assert relation["target"] == {"type": "invoice", "id": "invoice-arval"}
    unchanged = run(db[COLL_ESTRATTO_CONTO].find_one({"id": "mov-invoice"}, {"_id": 0}))
    assert unchanged == source


def test_modifica_revoca_vecchio_collegamento_e_conserva_la_versione():
    db = AsyncMongoMockClient()["manual-operation-index-edit"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({
        "id": "mov-edit", "data": "2026-08-03", "tipo": "uscita", "importo": 1500,
    }))
    run(db["invoices"].insert_one({"id": "invoice-1", "supplier_name": "Fornitore", "invoice_number": "1"}))
    run(db["cedolini"].insert_one({"id": "payslip-1", "dipendente_nome": "Valerio Ceraldi", "periodo": "2026-07"}))

    with patch.object(Database, "get_db", return_value=db):
        first = run(save_manual_operation_decision(
            "mov-edit", ManualIndexDecisionIn(category="fattura", target_id="invoice-1", expected_version=0), USER,
        ))
        second = run(save_manual_operation_decision(
            "mov-edit", ManualIndexDecisionIn(category="cedolino", target_id="payslip-1", expected_version=1), USER,
        ))

    assert first["decision"]["version"] == 1
    assert second["decision"]["version"] == 2
    current = run(db[COLL_BANK_OPERATION_INDEX].find_one({"movement_id": "mov-edit"}))
    assert current["target_id"] == "payslip-1"
    assert len(current["history"]) == 1
    old_relation = run(db[COLL_ENTITY_RELATIONS].find_one({"target.id": "invoice-1"}))
    new_relation = run(db[COLL_ENTITY_RELATIONS].find_one({"target.id": "payslip-1"}))
    assert old_relation["status"] == "revoked"
    assert new_relation["status"] == "confirmed"


def test_versione_obsoleta_blocca_la_sovrascrittura():
    db = AsyncMongoMockClient()["manual-operation-index-lock"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({"id": "mov-lock", "data": "2026-08-03", "tipo": "uscita", "importo": 1}))
    run(db[COLL_BANK_OPERATION_INDEX].insert_one({"movement_id": "mov-lock", "version": 2, "status": "classified"}))

    with patch.object(Database, "get_db", return_value=db):
        with pytest.raises(HTTPException) as exc:
            run(save_manual_operation_decision(
                "mov-lock", ManualIndexDecisionIn(category="altro", expected_version=1), USER,
            ))
    assert exc.value.status_code == 409


def test_candidati_cedolino_sono_solo_elenco_manual_selectable():
    db = AsyncMongoMockClient()["manual-operation-index-candidates"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({"id": "mov-salary", "data": "2026-08-03", "tipo": "uscita", "importo": 1500}))
    run(db["cedolini"].insert_many([
        {"id": "p1", "dipendente_nome": "Valerio Ceraldi", "periodo": "2026-07", "netto": 1500},
        {"id": "p2", "dipendente_nome": "Mario Rossi", "periodo": "2026-07", "netto": 1400},
    ]))

    with patch.object(Database, "get_db", return_value=db):
        result = run(list_manual_operation_candidates(
            "mov-salary", category="cedolino", search="Valerio", limit=50, _user=USER,
        ))

    assert result["matching"] == "manual_only"
    assert [item["id"] for item in result["candidates"]] == ["p1"]
    assert result["candidates"][0]["label"] == "Valerio Ceraldi - 2026-07"
