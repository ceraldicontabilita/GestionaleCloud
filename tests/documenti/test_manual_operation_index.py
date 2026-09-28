import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.database import Database
from app.db_collections import (
    COLL_BANK_OPERATION_INDEX,
    COLL_ENTITY_RELATIONS,
    COLL_ESTRATTO_CONTO,
    COLL_SUPPLIERS,
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
    db = ClientArchivioMemoria()["manual-operation-index-list"]
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


def test_indice_non_richiede_scelta_manual_per_movimento_gia_riconciliato():
    db = ClientArchivioMemoria()["manual-operation-index-bank-proof"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({
        "id": "mov-proof", "data": "2026-08-03", "tipo": "uscita", "importo": -100,
        "riconciliato": True, "riconciliato_con": "assegno", "assegno_id": "assegno-1",
        "riconciliato_at": "2026-08-04T10:00:00+00:00",
    }))

    with patch.object(Database, "get_db", return_value=db):
        result = run(list_manual_operation_index(
            anno=2026, tipo=None, stato=None, search="", limit=100, offset=0, _user=USER,
        ))

    row = result["rows"][0]
    assert row["index_status"] == "riconciliato_banca"
    assert row["bank_evidence"] == {
        "kind": "assegno", "invoice_id": None, "invoice_ids": [], "cheque_id": "assegno-1",
        "reconciled_at": "2026-08-04T10:00:00+00:00",
    }


def test_indice_include_anche_un_movimento_storico_con_solo_object_id():
    db = ClientArchivioMemoria()["manual-operation-index-object-id"]
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
    db = ClientArchivioMemoria()["manual-operation-index-save"]
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
    db = ClientArchivioMemoria()["manual-operation-index-edit"]
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
    db = ClientArchivioMemoria()["manual-operation-index-lock"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({"id": "mov-lock", "data": "2026-08-03", "tipo": "uscita", "importo": 1}))
    run(db[COLL_BANK_OPERATION_INDEX].insert_one({"movement_id": "mov-lock", "version": 2, "status": "classified"}))

    with patch.object(Database, "get_db", return_value=db):
        with pytest.raises(HTTPException) as exc:
            run(save_manual_operation_decision(
                "mov-lock", ManualIndexDecisionIn(category="altro", expected_version=1), USER,
            ))
    assert exc.value.status_code == 409


def test_candidati_cedolino_sono_solo_elenco_manual_selectable():
    db = ClientArchivioMemoria()["manual-operation-index-candidates"]
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


def test_candidato_fattura_mostra_metodo_fornitore_senza_riconciliare():
    db = ClientArchivioMemoria()["manual-operation-index-supplier-method"]
    run(db[COLL_ESTRATTO_CONTO].insert_one({"id": "mov-invoice", "data": "2026-08-03", "tipo": "uscita", "importo": -120}))
    run(db["invoices"].insert_one({
        "id": "invoice-1", "supplier_vat": "IT01234567890", "supplier_name": "Fornitore Banca",
        "invoice_number": "42", "invoice_date": "2026-07-30", "total_amount": 120,
    }))
    run(db[COLL_SUPPLIERS].insert_one({
        "id": "supplier-1", "partita_iva": "01234567890", "metodo_pagamento": "banca",
    }))

    with patch.object(Database, "get_db", return_value=db):
        result = run(list_manual_operation_candidates(
            "mov-invoice", category="fattura", search="", limit=50, _user=USER,
        ))

    assert result["matching"] == "manual_only"
    assert result["candidates"][0]["details"]["payment_method"] == "banca"
    assert run(db[COLL_ESTRATTO_CONTO].find_one({"id": "mov-invoice"})).get("riconciliato") is None


def test_stato_e_carta_filtrati_prima_di_contare_e_paginare():
    """Lo stato si decide nella query: filtrarlo dopo lo skip lasciava pagine
    vuote e un totale sbagliato; le operazioni carta Nexi non sono righe banca."""
    db = ClientArchivioMemoria()["manual-operation-index-stato"]
    run(db[COLL_ESTRATTO_CONTO].insert_many([
        {"id": f"mov-{i:02d}", "data": f"2026-08-{i + 1:02d}", "tipo": "uscita",
         "importo": -10 - i, "descrizione": f"MOVIMENTO {i}"}
        for i in range(6)
    ] + [
        {"id": "mov-ec", "data": "2026-08-20", "tipo": "uscita", "importo": -5,
         "riconciliato": True},
        {"id": "carta-1", "data": "2026-08-21", "tipo": "carta_credito", "importo": 9.99,
         "descrizione": "AMZN MKTP IT"},
    ]))
    run(db[COLL_BANK_OPERATION_INDEX].insert_many([
        {"movement_id": "mov-00", "category": "fattura", "target_id": "F-1", "status": "active"},
        {"movement_id": "mov-01", "category": "altro", "target_id": None, "status": "active"},
        {"movement_id": "mov-02", "category": "altro", "target_id": None, "status": "revoked"},
    ]))

    def elenca(stato, limit=100, offset=0):
        with patch.object(Database, "get_db", return_value=db):
            return run(list_manual_operation_index(
                anno=2026, tipo=None, stato=stato, search="", limit=limit, offset=offset,
                _user=USER,
            ))

    tutte = elenca(None)
    assert tutte["total_rows"] == 7
    assert "carta-1" not in {r["id"] for r in tutte["rows"]}

    da_classificare = elenca("da_classificare", limit=2, offset=2)
    assert da_classificare["total_rows"] == 4  # mov-02 (decisione revocata) .. mov-05
    assert [r["id"] for r in da_classificare["rows"]] == ["mov-03", "mov-02"]
    assert {r["index_status"] for r in da_classificare["rows"]} == {"da_classificare"}

    assert [r["id"] for r in elenca("collegato_indice")["rows"]] == ["mov-00"]
    assert [r["id"] for r in elenca("classificato")["rows"]] == ["mov-01"]
    assert [r["id"] for r in elenca("riconciliato_banca")["rows"]] == ["mov-ec"]
    assert elenca("all")["total_rows"] == 7

    with pytest.raises(HTTPException) as exc:
        elenca("inventato")
    assert exc.value.status_code == 400


def test_famiglia_causale_ignora_numeri_e_dettagli():
    from app.routers.prima_nota_module.operation_index import famiglia_causale

    assert famiglia_causale("VERS. CONTANTI - VVVVV") == "VERS. CONTANTI"
    assert famiglia_causale("COMMISSIONI - Comm.sdd: 3F3811A21532878") == "COMMISSIONI"
    assert famiglia_causale("COMMISSIONI - Comm.sdd: PK)K,TLYRBPN8") == "COMMISSIONI"
    # PDF ufficiale: senza il prefisso, conta cio' che precede i due punti.
    assert famiglia_causale("SDD CORE: 4360740000000700913195 FORNITORE UNO") == "SDD CORE"
    assert famiglia_causale("") == ""


def test_scelta_senza_documento_si_applica_ai_simili_solo_se_richiesto():
    """Titolare, 28/09/2026: classificato un versamento, tutti i versamenti
    ancora da classificare ricevono la stessa scelta; un movimento gia' deciso,
    riconciliato o di un'altra famiglia no. Ogni riga ha la sua decisione."""
    from app.routers.prima_nota_module.operation_index import list_manual_operation_similar

    db = ClientArchivioMemoria()["manual-operation-index-simili"]
    righe = [
        ("v-1", "2026-09-18", "entrata", 2760, "VERS. CONTANTI - VVVVV"),
        ("v-2", "2026-09-07", "entrata", 2600, "VERS. CONTANTI - VVVVV"),
        ("v-3", "2026-09-02", "entrata", 3500, "VERS. CONTANTI"),
        ("v-deciso", "2026-08-30", "entrata", 1000, "VERS. CONTANTI - VVVVV"),
        ("v-riconciliato", "2026-08-20", "entrata", 900, "VERS. CONTANTI - VVVVV"),
        ("v-2025", "2025-12-30", "entrata", 800, "VERS. CONTANTI - VVVVV"),
        ("c-1", "2026-09-15", "uscita", -1, "COMMISSIONI - Comm.sdd: 73029412064789"),
    ]
    for mid, data, tipo, importo, descr in righe:
        run(db[COLL_ESTRATTO_CONTO].insert_one({
            "id": mid, "data": data, "tipo": tipo, "importo": importo, "descrizione": descr,
            "fingerprint": f"fp-{mid}", **({"riconciliato": True} if mid == "v-riconciliato" else {}),
        }))
    run(db[COLL_BANK_OPERATION_INDEX].insert_one({
        "id": "bank-operation-index:v-deciso", "movement_id": "v-deciso",
        "category": "altro", "status": "classified", "version": 1,
    }))

    with patch.object(Database, "get_db", return_value=db):
        anteprima = run(list_manual_operation_similar("v-1", _user=USER))
        assert anteprima["family"] == "VERS. CONTANTI"
        assert [r["id"] for r in anteprima["samples"]] == ["v-2", "v-3"]

        # Senza richiesta: una riga sola.
        esito = run(save_manual_operation_decision(
            "c-1", ManualIndexDecisionIn(category="commissione_bancaria"), current_user=USER,
        ))
        assert esito["applied_to_similar"] == 0
        assert run(db[COLL_BANK_OPERATION_INDEX].count_documents({})) == 2

        esito = run(save_manual_operation_decision(
            "v-1", ManualIndexDecisionIn(category="trasferimento", note="cassa in banca",
                                         applica_a_simili=True), current_user=USER,
        ))

    assert esito["applied_to_similar"] == 2
    assert sorted(esito["applied_movement_ids"]) == ["v-2", "v-3"]
    decisioni = {d["movement_id"]: d for d in run(db[COLL_BANK_OPERATION_INDEX].find({}).to_list(None))}
    assert decisioni["v-2"]["category"] == "trasferimento"
    assert decisioni["v-2"]["note"] == "cassa in banca"
    assert decisioni["v-2"]["applied_from_movement_id"] == "v-1"
    assert decisioni["v-2"]["amount_cents"] == 260000
    assert "applied_from_movement_id" not in decisioni["v-1"]
    assert decisioni["v-deciso"]["category"] == "altro"
    assert "v-riconciliato" not in decisioni and "v-2025" not in decisioni
    # Nessuna scrittura contabile e nessun «pagato»: solo l'indice.
    assert run(db[COLL_ENTITY_RELATIONS].count_documents({})) == 0


def test_una_natura_con_documento_non_si_applica_mai_ai_simili():
    db = ClientArchivioMemoria()["manual-operation-index-simili-target"]
    for mid in ("f-1", "f-2"):
        run(db[COLL_ESTRATTO_CONTO].insert_one({
            "id": mid, "data": "2026-09-10", "tipo": "uscita", "importo": -50,
            "descrizione": "ADDEBITO DIRETTO SDD - SDD CORE: X FORNITORE", "fingerprint": mid,
        }))
    run(db[COLL_SUPPLIERS].insert_one({"id": "sup-1", "ragione_sociale": "FORNITORE UNO"}))

    with patch.object(Database, "get_db", return_value=db):
        esito = run(save_manual_operation_decision(
            "f-1", ManualIndexDecisionIn(category="fornitore", target_id="sup-1", applica_a_simili=True),
            current_user=USER,
        ))

    assert esito["applied_to_similar"] == 0
    assert run(db[COLL_BANK_OPERATION_INDEX].count_documents({})) == 1
