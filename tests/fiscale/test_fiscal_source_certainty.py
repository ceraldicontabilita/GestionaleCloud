from app.services.fiscal_source_certainty import (
    AMBIGUOUS, CERTAIN, DIFFERENT, MISSING_ACCOUNTANT, MISSING_OFFICIAL,
    annotate_declaration_certainty, group_model_rows, reconcile_f24_sources,
)


def _drive(document_id, code="6099", debit=0, credit=1604.90, period="2025-01"):
    return {
        "document_id": document_id, "filename": f"{document_id}.pdf",
        "protocol": f"P-{document_id}", "tax_code": code,
        "reference_period": period, "section": "ERARIO", "entity": "",
        "debit_amount": debit, "credit_amount": credit,
    }


def _accountant(document_id, code="6099", debit=0, credit=1604.90, period="2025-01"):
    return {
        "id": document_id, "file_name": f"{document_id}.pdf",
        "normalized_tax_rows": [{
            "tax_code": code, "reference_period": period, "section": "ERARIO",
            "entity_code": "", "debit_amount": debit, "credit_amount": credit,
        }],
    }


def test_exact_composite_fiscal_identity_is_certain_and_bidirectional():
    result = reconcile_f24_sources([_drive("Q1")], [_accountant("F1")])
    assert result["all_certain"] is True
    assert result["items"][0]["status"] == CERTAIN
    assert result["items"][0]["official_document"]["document_id"] == "Q1"
    assert result["semantics"]["amount_only_match_allowed"] is False


def test_same_amount_with_different_tax_code_is_not_a_match():
    result = reconcile_f24_sources([_drive("Q1", code="3918", debit=1604.90, credit=0)], [
        _accountant("F1", code="6099", debit=1604.90, credit=0),
    ])
    statuses = {item["status"] for item in result["items"]}
    assert DIFFERENT in statuses
    assert MISSING_ACCOUNTANT in statuses
    assert result["certain"] == 0


def test_missing_sources_are_explicit_in_both_directions():
    missing_receipt = reconcile_f24_sources([], [_accountant("F1")])
    missing_accountant = reconcile_f24_sources([_drive("Q1")], [])
    assert missing_receipt["items"][0]["status"] == MISSING_OFFICIAL
    assert missing_accountant["items"][0]["status"] == MISSING_ACCOUNTANT


def test_duplicate_exact_receipts_are_ambiguous_not_confirmed():
    result = reconcile_f24_sources([_drive("Q1"), _drive("Q2")], [_accountant("F1")])
    assert result["items"][0]["status"] == AMBIGUOUS
    assert result["items"][0]["candidate_count"] == 2
    assert result["certain"] == 0


def test_duplicate_accountant_documents_are_ambiguous_not_confirmed():
    result = reconcile_f24_sources(
        [_drive("Q1")], [_accountant("F1"), _accountant("F2")],
    )
    assert result["certain"] == 0
    assert result["requires_review"] == 2
    assert {item["status"] for item in result["items"]} == {AMBIGUOUS}


def test_drive_model_rows_are_grouped_without_becoming_receipts():
    documents = group_model_rows([
        {"document_id": "MODEL-1", "filename": "commercialista.pdf", "tax_code": "2003",
         "reference_period": "2024", "debit_amount": 1000, "credit_amount": 0},
        {"document_id": "MODEL-1", "filename": "commercialista.pdf", "tax_code": "3800",
         "reference_period": "2024", "debit_amount": 500, "credit_amount": 0},
    ])

    assert len(documents) == 1
    assert documents[0]["id"] == "MODEL-1"
    assert documents[0]["source"] == "MODELLO_F24_DRIVE"
    assert len(documents[0]["normalized_tax_rows"]) == 2


def test_accountant_model_without_receipt_remains_due():
    result = reconcile_f24_sources([], [_accountant("F1")])
    assert result["items"][0]["erario_state"] == "F24_COMMERCIALISTA_IN_ATTESA_QUIETANZA"


def test_receipt_without_accountant_model_is_paid_but_source_review_remains():
    result = reconcile_f24_sources([_drive("Q1")], [])
    assert result["items"][0]["status"] == MISSING_ACCOUNTANT
    assert result["items"][0]["erario_state"] == "NULLA_DOVUTO_ERARIO_DOCUMENTATO"


def test_same_declaration_type_and_tax_year_are_not_double_counted_without_identity():
    declarations = [{
        "document_id": "REDDITI-ORIGINALE", "document_type": "REDDITI_SC",
        "tax_year": 2022,
        "relation_state": "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO",
    }, {
        "document_id": "REDDITI-INTEGRATIVA", "document_type": "REDDITI_SC",
        "tax_year": 2022,
        "relation_state": "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO",
    }]

    result = annotate_declaration_certainty(declarations)

    assert {item["field_check_status"] for item in result} == {
        "PRONTO_PER_VERIFICA_IDENTITA_VERSIONE",
    }
    assert {item["version_resolution_status"] for item in result} == {
        "IDENTITA_DICHIARANTE_E_VERSIONE_DA_VERIFICARE",
    }
    assert all(item["declaration_set_status"] ==
               "PIU_DICHIARAZIONI_STESSO_TIPO_E_ANNO_IMPOSTA" for item in result)
    assert result[0]["related_document_ids"] == ["REDDITI-INTEGRATIVA"]


def test_unique_supported_declaration_remains_ready_for_field_check():
    result = annotate_declaration_certainty([{
        "document_id": "IRAP-2024", "document_type": "DICHIARAZIONE_IRAP",
        "tax_year": 2024,
        "relation_state": "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO",
    }])

    assert result[0]["field_check_status"] == "PRONTO_PER_VERIFICA_CAMPI"
    assert result[0]["declaration_set_status"] == "UNICA_PER_TIPO_E_ANNO_IMPOSTA"


def test_multiple_lipe_same_year_remain_separate_periodic_declarations():
    result = annotate_declaration_certainty([{
        "document_id": f"LIPE-{quarter}", "document_type": "LIPE", "tax_year": 2024,
        "relation_state": "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO",
    } for quarter in range(1, 5)])

    assert all(item["field_check_status"] == "PRONTO_PER_VERIFICA_CAMPI" for item in result)
