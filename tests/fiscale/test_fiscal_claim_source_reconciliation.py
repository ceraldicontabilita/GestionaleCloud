import asyncio
from copy import deepcopy

import pytest

from app.db_collections import (
    COLL_DOCUMENTS_INBOX,
    COLL_F24,
    COLL_QUIETANZE_F24,
    COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_PAYMENTS,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_claim_source_reconciliation import (
    ALERT_REFUND,
    ALERT_RELIEF,
    apply_claim_source_plan,
    build_claim_source_plan,
    match_quietanza_for_obligation,
    match_f24_models_for_obligation,
    parse_inps_notice_lines,
)


INPS_TEXT = """
001       8050-Modello DM 10
CONTRIBUTI                           DA 06/2024 A 06/2024                2.485,00                   0,00               2.485,00
002      8055-Somme aggiuntive
SANZIONI MOROSITA'                    DA 06/2024 A 06/2024                    0,00                   0,00                  75,38
003       8050-Modello DM 10
CONTRIBUTI                           DA 07/2024 A 07/2024                1.476,00                   0,00               1.476,00
"""


def _run(coro):
    return asyncio.run(coro)


def test_avviso_inps_espone_periodi_importi_e_versato_zero():
    rows = parse_inps_notice_lines(INPS_TEXT)

    assert [(row["codice_tributo"], row["periodo_da"], row["importo_richiesto_cents"])
            for row in rows] == [
        ("8050", "06/2024", 248500),
        ("8055", "06/2024", 7538),
        ("8050", "07/2024", 147600),
    ]
    assert all(row["importo_versato_nell_avviso_cents"] == 0 for row in rows)


def test_quietanza_inps_richiede_matricola_periodo_e_importo_esatti():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    quietanza = {
        "id": "q-1", "protocollo_telematico": "PROTO-1", "data_pagamento": "2024-07-16",
        "sezione_inps": [{
            "causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "06/2024",
            "importo_debito_cents": 248500,
        }],
    }

    exact = match_quietanza_for_obligation(obligation, [quietanza])
    assert len(exact) == 1
    assert exact[0]["match_type"] == "EXACT"
    assert match_quietanza_for_obligation({**obligation, "importo_richiesto_cents": 248501}, [quietanza]) == []
    assert match_quietanza_for_obligation({**obligation, "matricola_inps": "ALTRA"}, [quietanza]) == []
    assert match_quietanza_for_obligation({**obligation, "periodo_da": "07/2024"}, [quietanza]) == []
    # Una quietanza DM10/RC01 aggregata non prova automaticamente le sanzioni 8055.
    assert match_quietanza_for_obligation({**obligation, "codice_tributo": "8055"}, [quietanza]) == []


def test_modello_f24_esatto_si_collega_ma_non_diventa_prova_di_pagamento():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    model = {
        "id": "f24-1", "filename": "F24 giugno 2024.pdf",
        "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "06/2024",
            "importo_debito_cents": 248500,
        }],
    }

    matches = match_f24_models_for_obligation(obligation, [model])

    assert len(matches) == 1
    assert matches[0]["f24_id"] == "f24-1"
    assert matches[0]["payment_evidence"] is False
    assert match_f24_models_for_obligation({**obligation, "importo_richiesto_cents": 248499}, [model]) == []


@pytest.mark.parametrize("source_field", ["testo_sorgente", "raw_text"])
def test_righe_inps_storiche_in_erario_usano_la_normalizzazione_canonica(source_field):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2003", "periodo_a": "07/2003",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    # Il vecchio parser aveva scambiato l'anno per il codice tributo Erario.
    historical_row = {
        "codice_tributo": "2003", "mese": "06", "anno": "2003",
        "importo_debito": "2.485,00",
        source_field: "5100 DM10 5124776507 06 2003 07 2003 2.485,00 , 0,00 ,",
    }
    model = {"id": "f24-storico", "sezione_erario": [historical_row]}
    receipt = {**model, "id": "q-storica", "protocollo_telematico": "PROTO-STORICO"}
    before = deepcopy((model, receipt))

    [model_match] = match_f24_models_for_obligation(obligation, [model])
    [payment_match] = match_quietanza_for_obligation(obligation, [receipt])

    assert model_match["model_amount_cents"] == 248500
    assert model_match["payment_evidence"] is False
    assert payment_match["paid_amount_cents"] == 248500
    assert payment_match["bank_verified"] is False
    assert payment_match["bank_movement_id"] is None
    assert (model, receipt) == before


@pytest.mark.parametrize("identity", [None, "", "   ", " - "])
@pytest.mark.parametrize("causale, amount", [("DM10", 248500), ("RC01", 250000)])
def test_matricola_avviso_mancante_non_conferma_modelli_o_quietanze(identity, causale, amount):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": "06/2024",
        "matricola_inps": identity, "importo_richiesto_cents": 248500,
    }
    model = {
        "id": "f24-senza-identita-avviso", "sezione_inps": [{
            "causale": causale, "matricola": "5124776507",
            "periodo_riferimento": "06/2024", "importo_debito_cents": amount,
        }],
    }
    receipt = {**model, "id": "q-senza-identita-avviso", "protocollo_telematico": "PROTO-1"}

    assert match_f24_models_for_obligation(obligation, [model]) == []
    assert match_quietanza_for_obligation(obligation, [receipt], [model]) == []


INACTIVE_MODEL_MARKERS = [
    pytest.param({"status": "eliminato"}, id="eliminato"),
    pytest.param({"entity_status": "deleted"}, id="deleted"),
    pytest.param({"motivo_quarantena": "doppione", "doppione_di": "f24-vigente"}, id="doppione"),
    pytest.param({"motivo_quarantena": "verifica_manuale"}, id="quarantena"),
    pytest.param({"superato_da": "f24-vigente"}, id="superato"),
    pytest.param({
        "status": "eliminato", "sostituito": True, "sostituito_da_f24_id": "f24-vigente",
    }, id="sostituito"),
]


@pytest.mark.parametrize("inactive", INACTIVE_MODEL_MARKERS)
def test_modello_inattivo_non_si_collega_ne_supporta_una_quietanza_dm10_aumentata(inactive):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": "06/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    original_row = {
        "causale": "DM10", "matricola": "5124776507",
        "periodo_riferimento": "06/2024", "importo_debito_cents": 248500,
    }
    model = {"id": "f24-inattivo", "sezione_inps": [original_row], **inactive}
    receipt = {
        "id": "q-dm10-aumentata", "protocollo_telematico": "PROTO-1",
        "sezione_inps": [{**original_row, "importo_debito_cents": 250000}],
    }

    assert match_f24_models_for_obligation(obligation, [model]) == []
    assert match_quietanza_for_obligation(obligation, [receipt], [model]) == []


@pytest.mark.parametrize("causale, amount", [("DM10", 248500), ("RC01", 250000)])
@pytest.mark.parametrize("period_from, period_to, expected", [
    ("06/2024", "07/2024", True),
    ("2024-06", "072024", True),
    ("062024", "2024-07", True),
    ("06/2024", "06/2024", False),
    ("06/2024", "05/2024", False),
    ("06/2024", "08/2024", False),
    ("06/2024", None, False),
    ("06/2024", "illeggibile", False),
    ("05/2024", "07/2024", False),
])
def test_intero_periodo_contributivo_deve_coincidere_anche_nel_ravvedimento(
    causale, amount, period_from, period_to, expected,
):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": "07/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    row = {
        "causale": causale, "matricola": "5124776507",
        "periodo_riferimento": period_from, "periodo_da": period_from,
        "importo_debito_cents": amount,
    }
    if period_to is not None:
        row["periodo_a"] = period_to
    model = {"id": "f24-periodo", "sezione_inps": [row]}
    receipt = {**model, "id": "q-periodo", "protocollo_telematico": "PROTO-PERIODO"}

    model_matches = match_f24_models_for_obligation(obligation, [model])
    payment_matches = match_quietanza_for_obligation(obligation, [receipt])

    assert bool(model_matches) is expected
    assert bool(payment_matches) is expected
    if expected:
        assert model_matches[0]["payment_evidence"] is False
        assert payment_matches[0]["bank_verified"] is False


def test_periodo_singolo_non_corrisponde_a_un_modello_che_si_estende_ad_altri_mesi():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    model = {
        "id": "f24-periodo-esteso", "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507",
            "periodo_da": "06/2024", "periodo_a": "07/2024",
            "importo_debito_cents": 248500,
        }],
    }
    receipt = {**model, "id": "q-periodo-esteso", "protocollo_telematico": "PROTO-1"}

    assert match_f24_models_for_obligation(obligation, [model]) == []
    assert match_quietanza_for_obligation(obligation, [receipt]) == []


@pytest.mark.parametrize("end", ["05/2024", "illeggibile"])
def test_periodo_avviso_invalido_non_conferma_modelli_o_quietanze(end):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": end,
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    model = {
        "id": "f24-periodo-avviso-invalido", "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507",
            "periodo_riferimento": "06/2024", "importo_debito_cents": 248500,
        }],
    }
    receipt = {**model, "id": "q-periodo-avviso-invalido", "protocollo_telematico": "PROTO-1"}

    assert match_f24_models_for_obligation(obligation, [model]) == []
    assert match_quietanza_for_obligation(obligation, [receipt]) == []


def test_rc01_maggiore_collega_il_ravvedimento_senza_fingere_un_pagamento_del_modello():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "11/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 392100,
    }
    model = {
        "id": "f24-rc01", "filename": "F24 ravvedimento novembre.pdf",
        "sezione_inps": [{
            "causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "11/2024",
            "importo_debito_cents": 408454,
        }],
    }

    matches = match_f24_models_for_obligation(obligation, [model])

    assert len(matches) == 1
    assert matches[0]["match_type"] == "RAVVEDIMENTO"
    assert matches[0]["increase_cents"] == 16354
    assert matches[0]["payment_evidence"] is False


def test_quietanza_rc01_maggiore_prova_il_ravvedimento_e_conserva_la_banca_separata():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "11/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 392100,
    }
    quietanza = {
        "id": "q-rc01", "protocollo_telematico": "25062535540243459/000001",
        "data_pagamento": "2025-06-25",
        "riscontro_banca": {"stato": "RISCONTRATO_BANCA", "movimento_id": "bank-4090"},
        "sezione_inps": [{
            "causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "11/2024",
            "importo_debito_cents": 409000,
        }],
    }

    matches = match_quietanza_for_obligation(obligation, [quietanza])

    assert len(matches) == 1
    assert matches[0]["basis"] == "QUIETANZA_RAVVEDIMENTO_RC01_IDENTITY_PERIOD_HIGHER_AMOUNT"
    assert matches[0]["increase_cents"] == 16900
    assert matches[0]["bank_verified"] is True
    assert matches[0]["bank_movement_id"] == "bank-4090"


def test_dm10_aumentato_e_ravvedimento_solo_se_f24_e_quietanza_hanno_tutte_le_righe_uguali():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "11/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 392100,
    }
    model = {
        "id": "f24-dm10-originale", "filename": "F24 originario.pdf",
        "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "11/2024",
            "importo_debito_cents": 392100,
        }],
    }
    quietanza = {
        "id": "q-dm10-aumentata", "protocollo_telematico": "PROTO-DM10",
        "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "11/2024",
            "importo_debito_cents": 409000,
        }],
    }

    matches = match_quietanza_for_obligation(obligation, [quietanza], [model])

    assert len(matches) == 1
    assert matches[0]["basis"] == "QUIETANZA_RAVVEDIMENTO_WRONG_DM10_SAME_CODES_HIGHER_AMOUNTS"
    assert matches[0]["supporting_f24"]["f24_id"] == "f24-dm10-originale"
    assert match_quietanza_for_obligation(obligation, [quietanza], []) == []
    model_con_riga_diversa = {
        **model,
        "id": "f24-non-coerente",
        "sezione_inps": [
            *model["sezione_inps"],
            {
                "causale": "DM10", "matricola": "5124776507",
                "periodo_riferimento": "10/2024", "importo_debito_cents": 10000,
            },
        ],
    }
    assert match_quietanza_for_obligation(
        obligation, [quietanza], [model_con_riga_diversa],
    ) == []


def test_supporto_dm10_richiede_anche_la_fine_periodo_delle_altre_righe():
    obligation = {
        "codice_tributo": "8050", "periodo_da": "11/2024", "periodo_a": "11/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 392100,
    }
    target_row = {
        "causale": "DM10", "matricola": "5124776507",
        "periodo_riferimento": "11/2024", "importo_debito_cents": 392100,
    }
    other_row = {
        "causale": "DM10", "matricola": "5124776507",
        "periodo_da": "06/2024", "periodo_a": "07/2024", "importo_debito_cents": 10000,
    }
    model = {"id": "f24-originario", "sezione_inps": [target_row, other_row]}
    receipt = {
        "id": "q-dm10", "protocollo_telematico": "PROTO-DM10-PERIODO",
        "sezione_inps": [
            {**target_row, "importo_debito_cents": 409000},
            {**other_row, "periodo_a": "08/2024"},
        ],
    }

    assert match_quietanza_for_obligation(obligation, [receipt], [model]) == []
    receipt["sezione_inps"][1]["periodo_a"] = "07/2024"
    [match] = match_quietanza_for_obligation(obligation, [receipt], [model])
    assert match["ravvedimento"] is True
    assert match["supporting_f24"]["f24_id"] == "f24-originario"
    assert match["bank_verified"] is False


@pytest.mark.parametrize("amount_fields, expected", [
    ({}, False),
    ({"importo_debito": None}, False),
    ({"importo_debito": ""}, False),
    ({"importo_debito": "illeggibile"}, False),
    ({"importo_debito_cents": "illeggibile"}, False),
    ({"importo_debito": 0}, True),
    ({"importo_debito_cents": 0}, True),
])
def test_supporto_dm10_non_scambia_un_importo_illeggibile_per_zero(amount_fields, expected):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": "06/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 248500,
    }
    target_row = {
        "causale": "DM10", "matricola": "5124776507",
        "periodo_riferimento": "06/2024", "importo_debito_cents": 248500,
    }
    other_row = {
        "codice_tributo": "1001", "periodo_riferimento": "06/2024", **amount_fields,
    }
    model = {
        "id": "f24-importo-da-verificare", "sezione_inps": [target_row],
        "sezione_erario": [other_row],
    }
    receipt = {
        "id": "q-importo-da-verificare", "protocollo_telematico": "PROTO-IMPORTO",
        "sezione_inps": [{**target_row, "importo_debito_cents": 250000}],
        "sezione_erario": [dict(other_row)],
    }

    matches = match_quietanza_for_obligation(obligation, [receipt], [model])

    assert bool(matches) is expected
    if expected:
        assert matches[0]["ravvedimento"] is True
        assert matches[0]["supporting_f24"]["f24_id"] == "f24-importo-da-verificare"
        assert matches[0]["bank_verified"] is False


@pytest.mark.parametrize("amount_fields", [
    {}, {"importo_debito": None}, {"importo_debito": ""},
    {"importo_debito": "illeggibile"}, {"importo_debito_cents": "illeggibile"},
])
def test_importo_assente_o_invalido_non_corrisponde_a_un_obbligo_zero(amount_fields):
    obligation = {
        "codice_tributo": "8050", "periodo_da": "06/2024", "periodo_a": "06/2024",
        "matricola_inps": "5124776507", "importo_richiesto_cents": 0,
    }
    model = {
        "id": "f24-senza-importo", "sezione_inps": [{
            "causale": "DM10", "matricola": "5124776507",
            "periodo_riferimento": "06/2024", **amount_fields,
        }],
    }
    receipt = {**model, "id": "q-senza-importo", "protocollo_telematico": "PROTO-ZERO"}

    assert match_f24_models_for_obligation(obligation, [model]) == []
    assert match_quietanza_for_obligation(obligation, [receipt]) == []


def test_quietanza_ravveduta_su_pretesa_esigibile_genera_verifica_sgravio():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-ravvedimento"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-ravv", "company_id": "04523831214",
            "collection_number": "37120250002792001000", "business_status": "PAYABLE",
        })
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-ravv", "tax_collection_claim_id": "claim-ravv",
            "parsed_metadata": {
                "numero_atto": "37120250002792001000", "matricola_inps": "5124776507",
                "testo_estratto": """
001       8050-Modello DM 10
CONTRIBUTI                           DA 11/2024 A 11/2024                3.921,00                   0,00               3.921,00
""",
            },
        })
        await db[COLL_QUIETANZE_F24].insert_one({
            "id": "q-ravv", "codice_fiscale": "04523831214",
            "protocollo_telematico": "25062535540243459/000001",
            "data_pagamento": "2025-06-25",
            "riscontro_banca": {"stato": "RISCONTRATO_BANCA", "movimento_id": "bank-4090"},
            "sezione_inps": [{
                "causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "11/2024",
                "importo_debito_cents": 409000,
            }],
        })

        result = await apply_claim_source_plan(db, company_id="04523831214", actor="test")
        claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-ravv"})

        assert result["alerts_created"] == 1
        assert claim["remediation_alert"]["action"] == "VERIFY_RELIEF_REQUEST"
        row = claim["source_obligation_links"][0]["tax_lines"][0]
        assert row["payment_evidence_status"] == "PAID_DOCUMENTED"
        assert row["payment_matches"][0]["ravvedimento"] is True

    _run(scenario())


def test_ravvedimento_e_rate_cartella_documentate_generano_verifica_rimborso_anche_se_sgravata():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-ravvedimento-double-payment"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-ravv-paid", "company_id": "04523831214",
            "collection_number": "37120250002792001000", "business_status": "RELIEVED",
            "portal_status": "SALDATI", "residual_cents": 0,
            "linked_payment_ids": ["taxpayment-rata-1"],
        })
        await db[COLL_TAX_PAYMENTS].insert_one({
            "id": "taxpayment-rata-1", "company_id": "04523831214",
            "source_type": "RICEVUTA_CBILL", "source_id": "ricevuta-rata-1",
            "operation_amount": "1272.66", "payment_date": "2025-10-13",
            "documentary_evidence": True, "bank_verified": False,
        })
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-ravv-paid", "tax_collection_claim_id": "claim-ravv-paid",
            "parsed_metadata": {
                "numero_atto": "37120250002792001000", "matricola_inps": "5124776507",
                "testo_estratto": """
001       8050-Modello DM 10
CONTRIBUTI                           DA 11/2024 A 11/2024                3.921,00                   0,00               3.921,00
""",
            },
        })
        await db[COLL_QUIETANZE_F24].insert_one({
            "id": "q-ravv-paid", "codice_fiscale": "04523831214",
            "protocollo_telematico": "25062535540243459/000001",
            "data_pagamento": "2025-06-25",
            "riscontro_banca": {"stato": "RISCONTRATO_BANCA", "movimento_id": "bank-4090"},
            "sezione_inps": [{
                "causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "11/2024",
                "importo_debito_cents": 409000,
            }],
        })

        result = await apply_claim_source_plan(db, company_id="04523831214", actor="test")
        claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-ravv-paid"})
        alert = await db["alerts"].find_one({"entita_id": "claim-ravv-paid", "codice": ALERT_REFUND})

        assert result["alerts_created"] == 1
        assert claim["remediation_alert"]["action"] == "VERIFY_REFUND_REQUEST"
        assert claim["remediation_alert"]["direct_collection_payments"] == [{
            "payment_id": "taxpayment-rata-1",
            "source_type": "RICEVUTA_CBILL",
            "source_id": "ricevuta-rata-1",
            "document_id": None,
            "amount": "1272.66",
            "payment_date": "2025-10-13",
            "bank_verified": False,
        }]
        assert alert["stato"] == "aperto"

    _run(scenario())


def test_residuo_portale_zero_senza_prova_della_cartella_non_inventa_un_rimborso():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-portal-zero-not-payment"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-portal-zero", "company_id": "04523831214",
            "collection_number": "37120250002792001000", "business_status": "RELIEVED",
            "portal_status": "SALDATI", "residual_cents": 0,
        })
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-portal-zero", "tax_collection_claim_id": "claim-portal-zero",
            "parsed_metadata": {
                "numero_atto": "37120250002792001000", "matricola_inps": "5124776507",
                "testo_estratto": """
001       8050-Modello DM 10
CONTRIBUTI                           DA 11/2024 A 11/2024                3.921,00                   0,00               3.921,00
""",
            },
        })
        await db[COLL_QUIETANZE_F24].insert_one({
            "id": "q-portal-zero", "codice_fiscale": "04523831214",
            "protocollo_telematico": "25062535540243459/000001",
            "sezione_inps": [{
                "causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "11/2024",
                "importo_debito_cents": 409000,
            }],
        })

        plan = await build_claim_source_plan(db, company_id="04523831214")

        assert plan[0]["remediation_alert"] is None

    _run(scenario())


def test_modello_f24_senza_quietanza_resta_non_pagato_e_non_genera_sgravio():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-model-only"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-model", "company_id": "04523831214",
            "collection_number": "37120240006692253000", "business_status": "PAYABLE",
            "documentary_payment_status": "NO_PAYMENT_EVIDENCE",
            "residual_cents": 248500, "linked_payment_ids": [],
        })
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-model", "tax_collection_claim_id": "claim-model",
            "parsed_metadata": {
                "numero_atto": "37120240006692253000", "matricola_inps": "5124776507",
                "testo_estratto": INPS_TEXT.split("002", 1)[0],
            },
        })
        await db[COLL_F24].insert_one({
            "id": "f24-model", "dati_generali": {"codice_fiscale": "04523831214"},
            "pagato": False, "status": "da_pagare",
            "filename": "F24 giugno 2024.pdf", "sezione_inps": [{
                "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "06/2024",
                "importo_debito_cents": 248500,
            }],
        })

        model_before = await db[COLL_F24].find_one({"id": "f24-model"})
        for index, marker in enumerate((
            {"status": "eliminato"}, {"entity_status": "deleted"},
            {"motivo_quarantena": "doppione", "doppione_di": "f24-model"},
            {"superato_da": "f24-model"},
        )):
            await db[COLL_F24].insert_one({
                **{key: value for key, value in model_before.items() if key != "_id"},
                "id": f"f24-escluso-{index}", **marker,
            })

        result = await apply_claim_source_plan(db, company_id="04523831214", actor="test")
        claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-model"})
        row = claim["source_obligation_links"][0]["tax_lines"][0]

        assert [match["f24_id"] for match in row["f24_model_matches"]] == ["f24-model"]
        assert row["f24_model_matches"][0]["payment_evidence"] is False
        assert row["payment_matches"] == []
        assert row["payment_evidence_status"] == "NO_PAYMENT_EVIDENCE"
        assert claim["source_reconciliation_status"] == "LINKED_NO_ACTION_WITHOUT_PAYMENT_EVIDENCE"
        assert claim["remediation_alert"] is None
        assert claim["business_status"] == "PAYABLE"
        assert claim["documentary_payment_status"] == "NO_PAYMENT_EVIDENCE"
        assert claim["residual_cents"] == 248500
        assert claim["linked_payment_ids"] == []
        assert result["alerts_created"] == 0
        assert await db[COLL_F24].find_one({"id": "f24-model"}) == model_before
        assert await db[COLL_TAX_PAYMENTS].find({}).to_list(10) == []

    _run(scenario())


@pytest.mark.parametrize("notice_identity", [None, "   "])
def test_avviso_senza_matricola_non_diventa_pagato_neppure_con_quietanza_e_banca(notice_identity):
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-missing-identity"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-no-identity", "company_id": "04523831214",
            "collection_number": "37120240006692253000", "business_status": "PAYABLE",
            "residual_cents": 248500,
        })
        metadata = {
            "numero_atto": "37120240006692253000",
            "testo_estratto": INPS_TEXT.split("002", 1)[0],
        }
        if notice_identity is not None:
            metadata["matricola_inps"] = notice_identity
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-no-identity", "tax_collection_claim_id": "claim-no-identity",
            "parsed_metadata": metadata,
        })
        model = {
            "id": "f24-no-identity", "codice_fiscale": "04523831214",
            "sezione_inps": [{
                "causale": "DM10", "matricola": "5124776507",
                "periodo_riferimento": "06/2024", "importo_debito_cents": 248500,
            }],
        }
        await db[COLL_F24].insert_one(model)
        await db[COLL_QUIETANZE_F24].insert_one({
            **model, "id": "q-no-identity", "protocollo_telematico": "PROTO-NO-IDENTITY",
            "riscontro_banca": {"stato": "RISCONTRATO_BANCA", "movimento_id": "bank-2485"},
        })

        result = await apply_claim_source_plan(db, company_id="04523831214", actor="test")
        claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-no-identity"})
        row = claim["source_obligation_links"][0]["tax_lines"][0]

        assert row["payment_evidence_status"] == "NO_PAYMENT_EVIDENCE"
        assert row["f24_model_matches"] == []
        assert row["payment_matches"] == []
        assert claim["business_status"] == "PAYABLE"
        assert claim["residual_cents"] == 248500
        assert claim["remediation_alert"] is None
        assert result["alerts_created"] == 0
        assert await db[COLL_TAX_PAYMENTS].find({}).to_list(10) == []

    _run(scenario())


def test_avviso_collegato_senza_quietanza_non_inventa_sgravio():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-no-payment"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-1", "company_id": "04523831214",
            "collection_number": "37120240006692253000", "business_status": "PAYABLE",
        })
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-1", "tax_collection_claim_id": "claim-1",
            "filename": "avviso.pdf", "drive_file_id": "drive-1",
            "parsed_metadata": {
                "numero_atto": "37120240006692253000", "matricola_inps": "5124776507",
                "testo_estratto": INPS_TEXT,
            },
        })

        plan = await build_claim_source_plan(db, company_id="04523831214")

        assert len(plan) == 1
        assert plan[0]["remediation_alert"] is None
        link = plan[0]["source_obligation_links"][0]
        assert link["relation_status"] == "CONFIRMED"
        assert {row["payment_evidence_status"] for row in link["tax_lines"]} == {"NO_PAYMENT_EVIDENCE"}

    _run(scenario())


def test_quietanza_esatta_su_pretesa_esigibile_salva_collegamento_e_alert_sgravio():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-paid"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-1", "company_id": "04523831214",
            "collection_number": "37120240006692253000", "business_status": "PAYABLE",
        })
        await db[COLL_DOCUMENTS_INBOX].insert_one({
            "id": "notice-1", "tax_collection_claim_id": "claim-1",
            "parsed_metadata": {
                "numero_atto": "37120240006692253000", "matricola_inps": "5124776507",
                "testo_estratto": INPS_TEXT.split("002", 1)[0],
            },
        })
        await db[COLL_QUIETANZE_F24].insert_one({
            "id": "q-1", "codice_fiscale": "04523831214", "protocollo_telematico": "PROTO-1",
            "data_pagamento": "2024-07-16", "sezione_inps": [{
                "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "06/2024",
                "importo_debito_cents": 248500,
            }],
        })

        result = await apply_claim_source_plan(db, company_id="04523831214", actor="test")
        claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": "claim-1"})
        alert = await db["alerts"].find_one({"entita_id": "claim-1", "codice": ALERT_RELIEF})

        assert result["alerts_created"] == 1
        assert claim["remediation_alert"]["action"] == "VERIFY_RELIEF_REQUEST"
        assert claim["source_obligation_links"][0]["tax_lines"][0]["payment_evidence_status"] == "PAID_DOCUMENTED"
        assert alert["stato"] == "aperto"

    _run(scenario())


def test_verbale_stampato_in_cartella_non_si_aggancia_per_sola_targa():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-verbale"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-v", "company_id": "04523831214",
            "collection_number": "07120260117439961000", "business_status": "PAYABLE",
        })
        await db["cartelle_pagamento"].insert_one({
            "id": "cartella:07120260117439961000", "tax_collection_claim_id": "claim-v",
            "verbali": [{"numero_verbale": "3773/V/2025", "targa": "GX037HJ"}],
            "righe": [{"codice_tributo": "5242", "numero_verbale": "3773/V/2025",
                       "targa": "GX037HJ", "importo": "86.50"}],
        })
        await db["verbali_noleggio"].insert_one({
            "id": "wrong", "numero_verbale": "A25111540620", "targa": "GX037HJ",
        })

        plan = await build_claim_source_plan(db, company_id="04523831214")
        link = plan[0]["source_obligation_links"][0]

        assert link["relation_status"] == "SOURCE_DOCUMENT_MISSING"
        assert link["matched_documents"] == []

    _run(scenario())
