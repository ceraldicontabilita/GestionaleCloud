from app.services.document_destination_registry import destination_for_document_type


def test_same_destination_is_used_independently_of_source_layer():
    assert destination_for_document_type("f24").area == "f24"
    assert destination_for_document_type("cedolino").area == "cedolini"
    assert destination_for_document_type("cartella_esattoriale").area == "cartelle_esattoriali"
    assert destination_for_document_type("avviso_bonario").area == "avvisi_bonari"


def test_pagopa_receipts_route_to_sibling_of_verbali_auto():
    route = destination_for_document_type("ricevuta_pagopa")
    assert route.area == "verbali_auto"
    assert route.sibling_name == "PAGAMENTI_E_BOLLETTINI_VERBALI"


def test_employee_special_folders_are_resolved_as_siblings():
    assert destination_for_document_type("certificazione_unica").sibling_name == "CERTIFICAZIONI UNICHE"
    assert destination_for_document_type("inps").sibling_name == "INPS"
    assert destination_for_document_type("inail").sibling_name == "INAIL"


def test_mortgage_documents_share_financing_destination():
    assert destination_for_document_type("mutuo").area == "noleggio"
    assert destination_for_document_type("avviso_pagamento_mutuo").area == "noleggio"
