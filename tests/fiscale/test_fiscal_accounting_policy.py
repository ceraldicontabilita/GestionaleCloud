from app.services.fiscal_accounting_policy import (
    POLICY_VERSION,
    build_journal_proposal,
    tax_code_rule,
)
from app.engines.tributi_engine import classifica_riga
from app.routers.fiscalita_italiana import F24Create, registra_f24


def _f24(*rows, saldo_netto_cents=None):
    by_section = {"sezione_erario": [], "sezione_regioni": [], "sezione_tributi_locali": []}
    for row in rows:
        section = row.pop("section", "sezione_erario")
        by_section.setdefault(section, []).append(row)
    if saldo_netto_cents is None:
        saldo_netto_cents = sum(
            int(row.get("importo_debito_cents") or 0)
            - int(row.get("importo_credito_cents") or 0)
            for values in by_section.values()
            for row in values
        )
    return {**by_section, "totali": {"saldo_netto_cents": saldo_netto_cents}, "pdf_hash": "sha-test"}


def test_codice_1075_e_sospeso_dall_archivio_ufficiale():
    rule = tax_code_rule("1075", period="2026-04")
    assert rule["status"] == "INVALID_OFFICIAL_REGISTER"
    assert rule["balance_sheet_account"] is None

    proposal = build_journal_proposal(
        _f24({"codice_tributo": "1075", "importo_debito_cents": 2666}),
        document_type="F24_MODELLO",
    )
    assert proposal["posting_allowed"] is False
    assert "CODICE_TRIBUTO_NON_VALIDATO:1075" in proposal["blockers"]
    assert proposal["definitive_posting_created"] is False
    assert classifica_riga("ERARIO", "1075")["stato_codice"] == "INVALID_OFFICIAL_REGISTER"


def test_modello_1040_non_crea_scrittura_ma_indica_d12():
    proposal = build_journal_proposal(
        _f24({"codice_tributo": "1040", "importo_debito_cents": 21000}),
        document_type="F24_MODELLO",
    )
    assert proposal["journal_proposal_status"] == "BLOCKED_REVIEW"
    assert proposal["posting_allowed"] is False
    assert "D12_DEBITI_TRIBUTARI_RITENUTE" in proposal["balance_sheet_candidates"]
    assert proposal["bilancio_candidates"][0]["stato_patrimoniale"] == "PASSIVO_D12_DEBITI_TRIBUTARI"
    assert proposal["bilancio_candidates"][0]["conto_economico"] is None
    assert proposal["deducibilita"][0]["ires"] == "NON_APPLICABILE_NON_E_UN_COSTO"


def test_quietanza_1040_prova_pagamento_documentale_banca_separata():
    proposal = build_journal_proposal(
        _f24({"codice_tributo": "1040", "importo_debito_cents": 28400}),
        document_type="F24_QUIETANZA",
        evidence_state={"quietanza_validata": True, "pagato_documentalmente": True},
        bank_state={"verified": False},
    )
    assert proposal["payment_evidence"] == {
        "documental": True,
        "bank_verified": False,
        "status": "PAGATO_DOCUMENTALE",
    }
    assert proposal["posting_allowed"] is True
    assert proposal["balanced"] is True
    assert proposal["lines"][-1]["account_code"] == "BANCA_C_C_DA_RICONCILIARE"
    assert any("banca ancora da verificare" in item for item in proposal["assumptions"])


def test_crediti_1701_1704_non_diventano_iva_ne_costi():
    proposal = build_journal_proposal(
        _f24(
            {"codice_tributo": "1701", "importo_credito_cents": 9863},
            {"codice_tributo": "1704", "importo_credito_cents": 62391},
        ),
        document_type="F24_MODELLO",
    )
    assert "ORIGINE_CREDITO_DA_ASSOCIARE:1701" in proposal["blockers"]
    assert "ORIGINE_CREDITO_DA_ASSOCIARE:1704" in proposal["blockers"]
    assert all(item["ires"] == "NON_APPLICABILE_CREDITO" for item in proposal["deducibilita"])


def test_avviso_pagopa_non_e_prova_e_sanzione_resta_da_verificare():
    proposal = build_journal_proposal(
        {"id": "notice-1", "pdf_hash": "sha-notice"},
        document_type="AVVISO_PAGOPA",
    )
    assert proposal["payment_evidence"]["documental"] is False
    assert proposal["posting_allowed"] is False
    assert "AVVISO_NON_PROVA_PAGAMENTO" in proposal["blockers"]
    assert POLICY_VERSION == proposal["policy_version"]


def test_endpoint_registra_f24_non_scrive_da_solo_modello():
    result = __import__("asyncio").run(registra_f24(F24Create(
        data_versamento="2026-05-16",
        data_scadenza="2026-05-16",
        tributi=[{"codice_tributo": "1040", "importo": "284,00", "periodo_riferimento": "06/2026"}],
        totale_versato=284.00,
    )))
    assert result["blocked"] is True
    assert result["action"] == "JOURNAL_PROPOSAL_ONLY"
    assert result["journal_proposal"]["definitive_posting_created"] is False
