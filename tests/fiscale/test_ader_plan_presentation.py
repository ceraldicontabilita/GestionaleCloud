import asyncio

from app.db_collections import COLL_ADER_POSITION_SNAPSHOTS, COLL_FISCAL_DOCUMENTS
from app.services.ader_plan_presentation import enrich_rate_plans
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


COMPANY = "04523831214"


def test_vista_piano_spiega_email_tributi_e_base_del_collegamento_f24():
    db = ClientArchivioMemoria()["ader_plan_presentation"]

    async def scenario():
        await db[COLL_FISCAL_DOCUMENTS].insert_many([
            {
                "id": "doc-piano", "company_id": COMPANY, "filename": "accoglimento.pdf",
                "source": "posta", "source_metadata": {
                    "email_account": "fiscale@example.it", "email_from": "ader@example.it",
                    "email_subject": "Accoglimento rateizzazione", "email_date": "2025-09-20",
                },
            },
            {"id": "doc-f24", "company_id": COMPANY, "filename": "rata-1.pdf", "source": "drive"},
        ])
        await db[COLL_ADER_POSITION_SNAPSHOTS].insert_one({
            "id": "snap", "company_id": COMPANY, "document_number": "07120250145650421000",
            "snapshot_date": "2026-10-06", "source_document_id": "doc-tributi",
            "document_type": "CARTELLA_ESATTORIALE", "creditor": "AGENZIA ENTRATE",
            "notification_date": "2025-09-19", "calculated_business_status": "ACTIVE_DEBT",
            "lines": [{
                "codice_tributo": "380A", "descrizione": "IRAP", "anno": 2022,
                "ente_impositore": "AGENZIA ENTRATE", "rateizzato": True,
                "iniziale_cents": 404064, "residuo_cents": 125514,
            }],
        })
        return await enrich_rate_plans(db, company_id=COMPANY, plans=[{
            "id": "piano", "company_id": COMPANY, "plan_reference": "AR071904285",
            "source_document_id": "doc-piano", "source_filename": "accoglimento.pdf",
            "documents": [{"printed_reference": "07120250145650421", "amount_cents": 749040}],
            "document_references": [{
                "printed_reference": "07120250145650421",
                "document_number": "07120250145650421000",
            }],
            "payment_modules": [{
                "id": "modulo", "plan_reference": "AR071904285",
                "document_number": "07198308127062530701", "source_document_id": "doc-f24",
                "installment_numbers": [1], "installments": [{"number": 1, "amount": 1272.66}],
                "payment_evidence": True,
            }],
        }])

    plan = asyncio.run(scenario())[0]
    assert plan["source_provenance"]["email_sources"][0]["email_account"] == "fiscale@example.it"
    assert plan["source_provenance"]["email_sources"][0]["email_from"] == "ader@example.it"
    assert plan["related_claims"][0]["link_status"] == "CONFIRMED_WITH_TAX_DETAIL"
    assert plan["related_claims"][0]["tributes"][0]["tax_code"] == "380A"
    assert plan["related_claims"][0]["tributes"][0]["year"] == 2022
    assert plan["f24_link_status"] == "CONFIRMED_BY_EXACT_PLAN_REFERENCE"
    assert plan["payment_modules"][0]["link_basis"] == "EXACT_PLAN_REFERENCE"
    # Un modulo predisposto non diventa prova di pagamento in questa vista.
    assert plan["payment_modules"][0]["payment_evidence"] is False


def test_vista_piano_non_inventa_email_o_f24_mancanti():
    db = ClientArchivioMemoria()["ader_plan_missing_evidence"]
    plan = asyncio.run(enrich_rate_plans(db, company_id=COMPANY, plans=[{
        "id": "piano", "company_id": COMPANY, "plan_reference": "AR071904285",
        "source_filename": "Accoglimento_AR071904285.pdf",
        "document_references": [{"printed_reference": "07120250145650421", "document_number": None}],
        "payment_modules": [],
    }]))[0]

    assert plan["source_provenance"]["status"] == "NOT_RECORDED"
    assert plan["f24_link_status"] == "NOT_FOUND_WITH_EXACT_PLAN_REFERENCE"
    assert plan["related_claims"][0]["link_status"] == "UNRESOLVED_REFERENCE"
    assert plan["related_claims"][0]["tributes"] == []


def test_vista_legge_anche_la_provenienza_email_dell_inbox():
    from app.services.ader_plan_presentation import _email_provenance

    provenienza = _email_provenance({
        "filename": "accoglimento.pdf", "source": "upload_automatico",
        "source_context": {
            "email_from": "inps@example.it", "email_subject": "Dilazione amministrativa",
            "email_date": "2026-02-26", "gmail_message_id": "gmail-1",
        },
    }, None)

    assert provenienza["status"] == "RECORDED"
    assert provenienza["email_sources"] == [{
        "email_from": "inps@example.it", "email_subject": "Dilazione amministrativa",
        "email_date": "2026-02-26", "email_message_id": "gmail-1",
    }]
