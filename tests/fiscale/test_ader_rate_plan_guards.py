"""Synthetic debtors and contradictory letters; no real archive content."""
import asyncio
import hashlib

import pytest

from app.db_collections import (
    COLL_FISCAL_DOCUMENTS, COLL_FISCAL_LINKS, COLL_TAX_COLLECTION_DOCUMENTS,
    COLL_TAX_PAYMENTS, COLL_TAX_RATE_PLANS,
)
from app.services import ader_snapshot_import as ader
from app.services.ader_rate_plan_guards import (
    plan_can_reconcile, plan_taxpayer_identity, plan_terms_signature,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_payment_reconciliation import find_ader_payment_target


COMPANY = "01234567890"
PERSON = "RSSMRA80A01H501U"
NUMBER = "07120260000000000001"


@pytest.mark.parametrize("text,expected", [
    (f"Presentata dal C.F. {COMPANY}. Rappresentante codice fiscale {PERSON}", "CONFIRMED"),
    (f"Presentata dal C.F. {PERSON}. Rappresenta societa {COMPANY}", "MISMATCH"),
    (f"Presentata dal C.F. {COMPANY}. Prospetto del piano di ammortamento C.F.: {PERSON}", "AMBIGUOUS"),
    (f"Rappresentante codice fiscale {PERSON}. Denominazione PROVA SRL", "MISSING"),
    (f"Prospetto del piano di ammortamento C.F.: {COMPANY}", "CONFIRMED"),
])
def test_taxpayer_is_the_applicant_and_plan_debtor_not_the_representative(text, expected):
    assert plan_taxpayer_identity(text, COMPANY)["status"] == expected


@pytest.mark.parametrize("owner,expected", [(COMPANY, "CONFIRMED"), (PERSON, "MISMATCH"), (None, "MISSING")])
def test_parser_retains_identity_result_and_never_confirms_an_unowned_letter(monkeypatch, owner, expected):
    text = ("Oggetto Accoglimento istanza con identificativo 071123456 del 01/01/2026 "
            + (f"presentata dal C.F. {owner} " if owner else "")
            + "Numero rate accordato: 2 NAPOLI, 10/01/2026")
    monkeypatch.setattr(ader, "_pdf_text", lambda _content: text)
    result = ader.parse_rate_plan(content=b"synthetic", filename="Accoglimento_AR071123456.pdf",
                                  company_id=COMPANY, document_numbers=[], dataset_sha256="a" * 64)
    assert result["taxpayer_identity_status"] == expected
    assert result["requires_review"] is (expected != "CONFIRMED")
    assert result["application_date"] == "2026-01-01"
    assert result["document_date"] == "2026-01-10"


def plan(*, filename="letter-a.pdf", count=2, identity="CONFIRMED"):
    return {
        "id": "plan-test", "company_id": COMPANY, "plan_reference": "AR071123456",
        "application_date": "2026-01-01", "document_date": "2026-01-10",
        "installment_count": count, "total_plan_cents": 20000, "total_plan_amount": 200,
        "rateizzato_cents": 20000, "first_installment_due_date": "2026-01-31",
        "first_installment_amount": 100, "documents": [{"printed_reference": NUMBER[:17], "amount_cents": 20000}],
        "document_references": [{"printed_reference": NUMBER[:17], "document_number": NUMBER}],
        "installments": [], "source_filename": filename, "requires_review": identity != "CONFIRMED",
        "taxpayer_identity_status": identity, "taxpayer_identity": {"status": identity},
    }


def archive(item, content=b"letter-a"):
    return {"id": "archive-test", "company_id": COMPANY, "source_archive_id": "archive-source",
            "dataset_sha256": "a" * 64, "analytics": [], "rate_plans": [item], "settlements": [],
            "payment_modules": [], "counts": {}, "pdfs": [{"filename": item["source_filename"],
              "content": content, "sha256": hashlib.sha256(content).hexdigest()}]}


@pytest.fixture
def db_and_ingestor(monkeypatch):
    db = ClientArchivioMemoria()["rate-plan-guards-test"]

    class Ingestor:
        def __init__(self, database, company_id):
            self.db, self.company_id = database, company_id

        async def ingest(self, *, content, filename, **_kwargs):
            doc_id = "doc-" + hashlib.sha256(content).hexdigest()
            await self.db[COLL_FISCAL_DOCUMENTS].update_one(
                {"id": doc_id, "company_id": self.company_id},
                {"$setOnInsert": {"id": doc_id, "company_id": self.company_id, "filename": filename,
                                  "document_type": "PIANO_RATEIZZAZIONE"}}, upsert=True,
            )
            return {"document_id": doc_id, "version_id": "version-" + doc_id, "status": "created"}

    from app.services import pdf_drive_only
    monkeypatch.setattr(ader, "FiscalDocumentIngestionService", Ingestor)
    monkeypatch.setattr(pdf_drive_only, "verified_drive_source", lambda *_args: {})
    return db


@pytest.mark.parametrize("identity", ["MISSING", "MISMATCH", "AMBIGUOUS"])
def test_unverified_debtor_keeps_original_as_review_document_without_claim_or_plan_links(db_and_ingestor, identity):
    async def scenario():
        db = db_and_ingestor
        result = await ader.apply_ader_archive_plan(db=db, plan=archive(plan(identity=identity)))
        assert result["identity_review_documents"] == 1 and result["requires_review"] is True
        assert result["existing_rate_plans"] == 0
        assert await db[COLL_FISCAL_DOCUMENTS].count_documents({}) == 1
        assert await db[COLL_TAX_RATE_PLANS].count_documents({}) == 0
        assert await db[COLL_FISCAL_LINKS].count_documents({}) == 0
        assert await db[COLL_TAX_PAYMENTS].count_documents({}) == 0
        review = await db[COLL_TAX_COLLECTION_DOCUMENTS].find_one({})
        assert review["taxpayer_identity_status"] == identity
        assert review["source_document_id"] and not review.get("linked_rate_plan_id")
    asyncio.run(scenario())


def test_same_protocol_conflicting_terms_preserves_both_originals_without_selecting_latest(db_and_ingestor):
    async def scenario():
        db = db_and_ingestor
        await ader.apply_ader_archive_plan(db=db, plan=archive(plan()))
        result = await ader.apply_ader_archive_plan(db=db, plan=archive(
            plan(filename="apparently-final.pdf", count=4), content=b"letter-b"))
        saved = await db[COLL_TAX_RATE_PLANS].find_one({"id": "plan-test"})
        assert saved["terms_conflict"] is True and saved["requires_review"] is True
        assert saved["installment_count"] == 2  # Original assertion retained, not a chosen final plan.
        assert {variant["installment_count"] for variant in saved["source_variants"]} == {2, 4}
        assert len(saved["source_document_ids"]) == 2
        assert len({variant["source_document_id"] for variant in saved["source_variants"]}) == 2
        assert {variant["document_date"] for variant in saved["source_variants"]} == {"2026-01-10"}
        assert result["conflicting_rate_plan_ids"] == ["plan-test"]
        assert plan_can_reconcile(saved) is False
        assert await db[COLL_FISCAL_DOCUMENTS].count_documents({}) == 2
        assert await db[COLL_TAX_PAYMENTS].count_documents({}) == 0
    asyncio.run(scenario())


def test_identical_terms_copied_in_a_second_pdf_are_preserved_without_creating_conflict(db_and_ingestor):
    async def scenario():
        db = db_and_ingestor
        await ader.apply_ader_archive_plan(db=db, plan=archive(plan()))
        await ader.apply_ader_archive_plan(db=db, plan=archive(plan(filename="copy.pdf"), b"same-terms-copy"))
        saved = await db[COLL_TAX_RATE_PLANS].find_one({"id": "plan-test"})
        assert saved["terms_conflict"] is False and saved["requires_review"] is False
        assert len(saved["source_variants"]) == 2
        assert len({variant["terms_signature"] for variant in saved["source_variants"]}) == 1
        assert plan_can_reconcile(saved) is True
    asyncio.run(scenario())


def test_terms_signature_ignores_copy_name_upload_time_and_resolved_claim_suffix():
    original = plan()
    copy = {**original, "source_filename": "final.pdf", "created_at": "2026-10-17",
            "document_references": [{"printed_reference": NUMBER[:17], "document_number": None}]}
    assert plan_terms_signature(original) == plan_terms_signature(copy)
    assert plan_terms_signature(original) != plan_terms_signature(plan(count=4))


@pytest.mark.parametrize("change", [
    {"terms_conflict": True}, {"requires_review": True}, {"taxpayer_identity_status": "MISSING"},
    {"taxpayer_identity_status": None}, {"taxpayer_identity_status": "MISMATCH"},
])
def test_unreviewed_or_conflicting_plan_is_not_a_payment_target(change):
    target = {**plan(), "payment_modules": [{"document_number": "payment-strong-id",
                                             "installments": [{"number": 1, "amount": 100}]}], **change}
    assert find_ader_payment_target(payment={"document_number": "payment-strong-id", "amount": 100},
                                   rate_plans=[target], settlements=[])["matched"] is False


def test_exact_documentary_payment_target_does_not_require_a_bank_movement():
    target = {**plan(), "payment_modules": [{"document_number": "payment-strong-id",
                                             "installments": [{"number": 1, "amount": 100}]}]}
    result = find_ader_payment_target(payment={"document_number": "payment-strong-id", "amount": 100},
                                      rate_plans=[target], settlements=[])
    assert result["matched"] is True


def test_later_claim_reference_resolution_cannot_clear_a_terms_conflict(db_and_ingestor):
    async def scenario():
        db = db_and_ingestor
        await db[COLL_TAX_RATE_PLANS].insert_one({
            **plan(), "terms_conflict": True, "requires_review": True,
            "unresolved_references": [NUMBER[:17]],
            "document_references": [{"printed_reference": NUMBER[:17], "document_number": None}],
        })
        assert await ader._risolvi_piani_in_attesa(db, COMPANY, NUMBER, now="2026-10-17") == 0
        saved = await db[COLL_TAX_RATE_PLANS].find_one({"id": "plan-test"})
        assert saved["requires_review"] is True and saved["terms_conflict"] is True
        assert saved["document_references"][0]["document_number"] is None
    asyncio.run(scenario())


@pytest.mark.parametrize("printed,filename,expected", [
    ("071123456", "Accoglimento_AR999999.pdf", "AR071123456"),
    ("123456", "Accoglimento_AR071123456.pdf", "AR123456"),
])
def test_plan_reference_comes_only_from_content_never_filename_or_invented_prefix(monkeypatch, printed, filename, expected):
    text = f"Identificativo {printed} del 01/01/2026 presentata dal C.F. {COMPANY} Numero rate accordato: 2"
    monkeypatch.setattr(ader, "_pdf_text", lambda _content: text)
    result = ader.parse_rate_plan(content=b"synthetic", filename=filename,
                                  company_id=COMPANY, document_numbers=[], dataset_sha256="a" * 64)
    assert result["plan_reference"] == expected
    assert result["printed_plan_reference"] == printed
    assert result["filename_reference_discrepancy"] is True


def test_different_filenames_cannot_split_one_printed_protocol_and_evade_terms_conflict(db_and_ingestor, monkeypatch):
    def parse(count, filename):
        text = f"Identificativo 071123456 del 01/01/2026 presentata dal C.F. {COMPANY} Numero rate accordato: {count}"
        monkeypatch.setattr(ader, "_pdf_text", lambda _content: text)
        return ader.parse_rate_plan(content=b"synthetic", filename=filename,
                                    company_id=COMPANY, document_numbers=[], dataset_sha256="a" * 64)

    first = parse(2, "Accoglimento_AR999999.pdf")
    second = parse(4, "Accoglimento_AR888888_finale.pdf")
    assert first["id"] == second["id"]

    async def scenario():
        db = db_and_ingestor
        await ader.apply_ader_archive_plan(db=db, plan=archive(first))
        await ader.apply_ader_archive_plan(db=db, plan=archive(second, b"letter-b"))
        assert await db[COLL_TAX_RATE_PLANS].count_documents({}) == 1
        saved = await db[COLL_TAX_RATE_PLANS].find_one({})
        assert saved["terms_conflict"] is True
        assert {variant["installment_count"] for variant in saved["source_variants"]} == {2, 4}
    asyncio.run(scenario())
