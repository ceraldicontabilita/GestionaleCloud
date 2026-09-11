from app.services.canonical_email_senders import (
    canonical_sender_from_header,
    default_rule_for_sender,
    is_excluded_sender,
    rule_allows_document_type,
    sender_matches_rule,
)


def test_exact_sender_match_does_not_accept_substrings():
    assert sender_matches_rule("Rosaria Marotta <rosaria.marotta@email.it>", "rosaria.marotta@email.it")
    assert not sender_matches_rule(
        "fake-rosaria.marotta@email.it@example.com",
        "rosaria.marotta@email.it",
    )


def test_pec_wrapper_uses_per_conto_di_sender_not_relay():
    raw = (
        '"Per conto di: notifica.acc.campania@pec.agenziariscossione.gov.it" '
        'posta-certificata@legalmail.it'
    )
    assert canonical_sender_from_header(raw) == "notifica.acc.campania@pec.agenziariscossione.gov.it"
    assert sender_matches_rule(raw, "notifica.acc.campania@pec.agenziariscossione.gov.it")
    assert not sender_matches_rule(raw, "posta-certificata@legalmail.it")


def test_anthirat_is_explicitly_excluded():
    assert is_excluded_sender("Gestione Credito <gestionecredito@anthiratcontrol.it>")
    assert default_rule_for_sender("Gestione Credito <gestionecredito@anthiratcontrol.it>") is None


def test_rosaria_is_not_authorized_as_bank_statement_source():
    rule = default_rule_for_sender("Rosaria Marotta <rosaria.marotta@email.it>")
    assert rule is not None
    assert rule_allows_document_type(rule, "f24")
    assert not rule_allows_document_type(rule, "estratto_conto")


def test_company_mailbox_can_supply_outgoing_tax_documents():
    rule = default_rule_for_sender("Ceraldi <ceraldigroupsrl@gmail.com>")
    assert rule is not None
    assert rule_allows_document_type(rule, "avviso_bonario")
    assert rule_allows_document_type(rule, "cartella_esattoriale")
    assert rule_allows_document_type(rule, "rottamazione")


def test_partenopay_is_limited_to_pagopa_domain_documents():
    rule = default_rule_for_sender("Partenopay <partenopay@ext.comune.napoli.it>")
    assert rule is not None
    assert rule_allows_document_type(rule, "ricevuta_pagopa")
    assert not rule_allows_document_type(rule, "cedolino")
