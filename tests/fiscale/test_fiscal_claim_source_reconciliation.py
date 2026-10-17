import asyncio

from app.db_collections import (
    COLL_DOCUMENTS_INBOX,
    COLL_F24,
    COLL_QUIETANZE_F24,
    COLL_TAX_COLLECTION_CLAIMS,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_claim_source_reconciliation import (
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

    assert len(match_quietanza_for_obligation(obligation, [quietanza])) == 1
    assert match_quietanza_for_obligation({**obligation, "importo_richiesto_cents": 248499}, [quietanza]) == []
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


def test_modello_f24_senza_quietanza_resta_non_pagato_e_non_genera_sgravio():
    async def scenario():
        db = ClientArchivioMemoria()["claim-source-model-only"]
        await db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
            "id": "claim-model", "company_id": "04523831214",
            "collection_number": "37120240006692253000", "business_status": "PAYABLE",
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
            "filename": "F24 giugno 2024.pdf", "sezione_inps": [{
                "causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "06/2024",
                "importo_debito_cents": 248500,
            }],
        })

        plan = await build_claim_source_plan(db, company_id="04523831214")
        row = plan[0]["source_obligation_links"][0]["tax_lines"][0]

        assert len(row["f24_model_matches"]) == 1
        assert row["payment_evidence_status"] == "NO_PAYMENT_EVIDENCE"
        assert plan[0]["remediation_alert"] is None

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
