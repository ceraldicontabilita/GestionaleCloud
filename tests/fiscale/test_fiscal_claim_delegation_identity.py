"""Il ravvedimento DM10 richiede tutta la delega, non soltanto la riga INPS."""
from copy import deepcopy

import pytest

from app.services.fiscal_claim_source_reconciliation import (
    match_f24_models_for_obligation,
    match_quietanza_for_obligation,
)


OBLIGATION = {
    "codice_tributo": "8050", "periodo_da": "11/2024",
    "matricola_inps": "5124776507", "importo_richiesto_cents": 392100,
}


def _delegations(**sections):
    model = {
        "id": "model", "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "11/2024",
            "importo_debito_cents": 392100,
        }], **deepcopy(sections),
    }
    receipt = {**deepcopy(model), "id": "receipt", "protocollo_telematico": "PROTO-1"}
    receipt["sezione_inps"][0]["importo_debito_cents"] = 409000
    return model, receipt


def _inail():
    return {
        "codice_sede": "33400", "codice_ditta": "13882560", "cc": "53",
        "numero_riferimento": "902024", "causale": "P", "importo_debito_cents": 64990,
    }


def test_delega_mista_include_inail_senza_inventare_un_periodo_fiscale():
    model, receipt = _delegations(sezione_inail=[_inail()])
    # Il parser della quietanza usa l'altro nome per sede e controllo.
    row = receipt["sezione_inail"][0]
    row["codice_ufficio"] = row.pop("codice_sede")
    row["codice_controllo"] = row.pop("cc")

    [match] = match_quietanza_for_obligation(OBLIGATION, [receipt], [model])

    assert match["supporting_f24"]["f24_id"] == "model"
    assert match["ravvedimento"] is True
    assert match["bank_verified"] is False


@pytest.mark.parametrize("field,other", [
    ("codice_sede", "33500"), ("codice_ditta", "13882561"), ("cc", "54"),
    ("numero_riferimento", "902025"), ("causale", "E"), ("importo_debito_cents", 64989),
])
def test_riga_inail_diversa_impedisce_il_supporto_dm10(field, other):
    model, receipt = _delegations(sezione_inail=[_inail()])
    receipt["sezione_inail"][0][field] = other

    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []


@pytest.mark.parametrize("missing_from", ["model", "receipt"])
def test_riga_inail_presente_in_una_sola_delega_impedisce_il_supporto_dm10(missing_from):
    model, receipt = _delegations(sezione_inail=[_inail()])
    (model if missing_from == "model" else receipt).pop("sezione_inail")

    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []


@pytest.mark.parametrize("field", ["codice_sede", "codice_ditta", "cc", "numero_riferimento", "causale"])
def test_inail_incompleta_non_conferma_il_ravvedimento_anche_se_le_copie_coincidono(field):
    incomplete = _inail()
    incomplete.pop(field)
    model, receipt = _delegations(sezione_inail=[incomplete])

    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []


@pytest.mark.parametrize("year_field", ["periodo_riferimento", "anno_riferimento", "anno"])
def test_riga_annuale_di_una_delega_mista_non_blocca_il_ravvedimento(year_field):
    model, receipt = _delegations(sezione_erario=[{
        "codice_tributo": "6099", year_field: "2024", "importo_debito_cents": 50000,
    }])

    [match] = match_quietanza_for_obligation(OBLIGATION, [receipt], [model])

    assert match["ravvedimento"] is True
    receipt["sezione_erario"][0][year_field] = "2023"
    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []


def test_tributo_annuale_esatto_si_collega_senza_dare_al_modello_prova_di_pagamento():
    obligation = {"codice_tributo": "6099", "periodo": "2024", "importo_richiesto_cents": 50000}
    model = {
        "id": "annual-model", "sezione_erario": [{
            "codice_tributo": "6099", "anno": 2024, "importo_debito_cents": 50000,
        }],
    }
    receipt = {**model, "id": "annual-receipt", "protocollo_telematico": "ANNUAL-PROTO"}

    [payment] = match_quietanza_for_obligation(obligation, [receipt])
    [form] = match_f24_models_for_obligation(obligation, [model])

    assert payment["match_type"] == "EXACT"
    assert form["payment_evidence"] is False
    assert match_quietanza_for_obligation({**obligation, "periodo": "01/2024"}, [receipt]) == []


@pytest.mark.parametrize("section,entity_field,code,entity,other", [
    ("sezione_regioni", "codice_regione", "3802", "15", "16"),
    ("sezione_tributi_locali", "codice_comune", "3848", "F839", "H501"),
    ("sezione_tributi_locali", "codice_ente", "3848", "F839", "H501"),
])
def test_comune_o_regione_identificano_anche_le_righe_accessorie(section, entity_field, code, entity, other):
    model, receipt = _delegations(**{section: [{
        "codice_tributo": code, entity_field: entity,
        "periodo_riferimento": "11/2024", "importo_debito_cents": 10000,
    }]})
    assert len(match_quietanza_for_obligation(OBLIGATION, [receipt], [model])) == 1

    receipt[section][0][entity_field] = other
    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []

    receipt[section][0].pop(entity_field)
    model[section][0].pop(entity_field)
    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []


def test_credito_compensato_diverso_non_dimostra_che_si_tratta_della_stessa_delega():
    model, receipt = _delegations(sezione_erario=[{
        "codice_tributo": "1701", "periodo_riferimento": "2024", "importo_credito_cents": 10000,
    }])
    assert len(match_quietanza_for_obligation(OBLIGATION, [receipt], [model])) == 1

    receipt["sezione_erario"][0]["importo_credito_cents"] = 20000
    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []


def test_f24_originario_con_intervallo_inps_diverso_non_prova_il_dm10_aumentato():
    model, receipt = _delegations()
    model["sezione_inps"][0]["periodo_a"] = "12/2024"

    assert match_quietanza_for_obligation(OBLIGATION, [receipt], [model]) == []
