from app.services.expectation_policy import (
    OPEN_EXPECTATION_STATES,
    TERMINAL_POSITIVE_STATES,
    expectation_evidence_fields,
    expectation_fields,
    mandatory_expectations_closed,
)


def test_un_fatto_crea_un_attesa_aperta_con_owner():
    fields = expectation_fields(
        expectation_type="quietanza_f24",
        owner="f24",
        source_fact_id="f24-1",
    )
    assert fields["expectation_status"] == "ATTESO"
    assert fields["expectation_owner"] == "f24"


def test_l_evidenza_soddisfa_o_lascia_da_verificare():
    assert expectation_evidence_fields(
        satisfied=True, evidence_ids=["ec-1", "ec-1", "ec-2"],
    ) == {
        "expectation_status": "SODDISFATTO",
        "expectation_evidence_ids": ["ec-1", "ec-2"],
    }
    assert expectation_evidence_fields(
        satisfied=False, evidence_ids=["ec-3"],
    )["expectation_status"] == "DA_VERIFICARE"


def test_chiusura_richiede_tutte_le_attese_obbligatorie_positive():
    assert mandatory_expectations_closed([
        {"expectation_status": "SODDISFATTO"},
        {"expectation_status": "NON_APPLICABILE"},
        {"expectation_status": "SUPERATO"},
    ]) is True
    assert mandatory_expectations_closed([
        {"expectation_status": "SODDISFATTO"},
        {"expectation_status": "ATTESO"},
    ]) is False
    assert mandatory_expectations_closed([]) is False
    assert "ATTESO" in OPEN_EXPECTATION_STATES
    assert "SODDISFATTO" in TERMINAL_POSITIVE_STATES
