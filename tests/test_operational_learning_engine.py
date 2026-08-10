import asyncio
from copy import deepcopy
from datetime import date

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.db_collections import (
    COLL_CASE_MEMORY,
    COLL_DECISION_QUESTIONS,
    COLL_EXPECTED_EVENTS,
    COLL_F24,
    COLL_KNOWLEDGE_SOURCES,
)
from app.services.mittenti import sender_matches_trusted_rules, trusted_sender_rules
from app.services.operational_learning_engine import (
    OperationalLearningEngine,
    build_tax_obligation,
    identity_document_expiry_question,
    expected_vs_actual,
    payroll_residual_question,
    tax_misallocation_assessment,
)


def _run(coro):
    return asyncio.run(coro)


def _database():
    return AsyncMongoMockClient()["gestionale_test"]


def test_expected_vs_actual_usa_centesimi_esatti():
    comparison = expected_vs_actual("100,00", "99,99")
    assert comparison == {
        "expected": 100.0,
        "actual": 99.99,
        "delta": 0.01,
        "status": "partial",
        "comparison": "exact_cents",
    }


def test_cedolino_parziale_non_viene_chiuso():
    question = payroll_residual_question(
        {
            "id": "ced-1",
            "nome_dipendente": "Mario Rossi",
            "anno": 2026,
            "mese": 7,
            "netto": "1.000,00",
        },
        "999,99",
    )
    assert question is not None
    assert question["question_type"] == "payroll_residual"
    assert question["evidence"]["status"] == "partial"
    assert question["evidence"]["residuo"] == 0.01


def test_controipotesi_f24_abbassa_la_conclusione_e_la_confidenza():
    possible = tax_misallocation_assessment(
        expected_year=2025,
        declared_year=2024,
        tax_code="2001",
        expected_amount="4613,50",
        paid_amount="4613,50",
        bank_verified=True,
        compatible_declared_year_debt=False,
    )
    ambiguous = tax_misallocation_assessment(
        expected_year=2025,
        declared_year=2024,
        tax_code="2001",
        expected_amount="4613,50",
        paid_amount="4613,50",
        bank_verified=True,
        compatible_declared_year_debt=True,
    )
    mismatch = tax_misallocation_assessment(
        expected_year=2025,
        declared_year=2024,
        tax_code="2001",
        expected_amount="4613,50",
        paid_amount="4613,48",
        bank_verified=True,
    )

    assert possible["conclusion"] == "possible_year_misallocation"
    assert ambiguous["conclusion"] == "ambiguous_compatible_declared_year_debt"
    assert ambiguous["confidence"] < possible["confidence"]
    assert mismatch["conclusion"] == "not_supported"
    assert mismatch["must_not_auto_pay_again"] is False


def test_obbligo_fiscale_rifiuta_importi_nulli_e_periodi_incoerenti():
    annual = build_tax_obligation(
        tax_code="2001",
        year=2025,
        due_date="2026-08-20",
        expected_amount="4613,50",
        source_id="studio-marotta-f24-1",
    )
    monthly = build_tax_obligation(
        tax_code="1040",
        year=2026,
        due_date="2026-08-16",
        expected_amount="210,00",
        source_id="f24-ritenute-luglio",
        period="07/2026",
    )
    assert annual["month"] is None
    assert annual["period"] == "2025"
    assert monthly["month"] == 7
    assert monthly["period"] == "2026-07"
    with pytest.raises(ValueError):
        build_tax_obligation(
            tax_code="1040",
            year=2026,
            due_date="2026-08-16",
            expected_amount=0,
            source_id="x",
        )
    with pytest.raises(ValueError):
        build_tax_obligation(
            tax_code="1040",
            year=2026,
            due_date="2026-08-16",
            expected_amount=10,
            source_id="x",
            period="07/2025",
        )


def test_documento_scaduto_resta_visibile_come_criticita():
    question = identity_document_expiry_question(
        {"id": "dip-1", "nome_completo": "Mario Rossi"},
        date(2026, 7, 31),
        today=date(2026, 8, 10),
    )
    assert question is not None
    assert question["severity"] == "critical"
    assert question["evidence"]["days_to_expiry"] == -10
    assert "scaduto da 10 giorni" in question["question"]


def test_domanda_risolta_non_viene_riaperta_da_una_nuova_scansione():
    async def scenario():
        db = _database()
        engine = OperationalLearningEngine(db)
        question = payroll_residual_question(
            {
                "id": "ced-answered",
                "nome_dipendente": "Mario Rossi",
                "anno": 2026,
                "mese": 7,
                "netto": "1.000,00",
            },
            "900,00",
        )
        await engine.open_question(question)
        await engine.answer_question(question["id"], "verifica_pagamenti", "admin")
        await engine.open_question(question)
        stored = await db[COLL_DECISION_QUESTIONS].find_one(
            {"id": question["id"]}, {"_id": 0}
        )
        assert stored["status"] == "answered"
        assert stored["answer"]["actor"] == "admin"
        assert stored.get("last_seen_at")

    _run(scenario())


def test_controipotesi_f24_deriva_da_obbligo_atteso_non_da_un_altro_pagamento():
    async def scenario():
        db = _database()
        engine = OperationalLearningEngine(db)
        payment = {
            "id": "f24-wrong-year",
            "bank_verified": True,
            "sezione_erario": [
                {
                    "codice_tributo": "2001",
                    "anno_riferimento": "2024",
                    "anno_atteso": "2025",
                    "importo_debito": "4.613,50",
                    "importo_atteso": "4.613,50",
                }
            ],
        }
        duplicate_payment = {**deepcopy(payment), "id": "f24-wrong-year-copy"}
        await db[COLL_F24].insert_many([payment, duplicate_payment])

        without_obligation = await engine.scan_f24_misallocations()
        assert all(
            item["assessment"]["conclusion"] == "possible_year_misallocation"
            for item in without_obligation
        )

        obligation = build_tax_obligation(
            tax_code="2001",
            year=2024,
            due_date="2025-06-30",
            expected_amount="4.613,50",
            source_id="dichiarazione-2024",
        )
        await engine.upsert_expected_event(obligation)
        with_obligation = await engine.scan_f24_misallocations()
        assert all(
            item["assessment"]["conclusion"]
            == "ambiguous_compatible_declared_year_debt"
            for item in with_obligation
        )

    _run(scenario())


def test_tax_event_legge_sezioni_f24_e_non_confonde_periodo_con_pagamento():
    async def scenario():
        db = _database()
        engine = OperationalLearningEngine(db)
        obligation_january = build_tax_obligation(
            tax_code="1040",
            year=2025,
            due_date="2025-02-16",
            expected_amount="210,00",
            source_id="source-jan",
            period="01/2025",
        )
        obligation_february = build_tax_obligation(
            tax_code="1040",
            year=2025,
            due_date="2025-03-16",
            expected_amount="210,00",
            source_id="source-feb",
            period="02/2025",
        )
        periodic_payment = {
            "id": "expected-periodic-feb",
            "event_type": "f24_periodic_tax",
            "key": "1040",
            "year": 2026,
            "month": 2,
            "expected_amount": 210.0,
            "status": "expected",
        }
        for event in (obligation_january, obligation_february, periodic_payment):
            await engine.upsert_expected_event(event)

        f24 = {
            "id": "f24-1040-jan",
            "data_pagamento": "2026-02-16",
            "sezione_erario": [
                {
                    "codice_tributo": "1040",
                    "anno_riferimento": "2025",
                    "periodo_riferimento": "0101",
                    "importo_debito": "210,00",
                }
            ],
        }
        source_before = deepcopy(f24)
        await db[COLL_F24].insert_one(f24)
        await engine.reconcile_expected_tax_events()
        await engine.reconcile_expected_tax_events()

        january = await db[COLL_EXPECTED_EVENTS].find_one({"id": obligation_january["id"]}, {"_id": 0})
        february = await db[COLL_EXPECTED_EVENTS].find_one({"id": obligation_february["id"]}, {"_id": 0})
        periodic = await db[COLL_EXPECTED_EVENTS].find_one({"id": periodic_payment["id"]}, {"_id": 0})
        source_after = await db[COLL_F24].find_one({"id": "f24-1040-jan"}, {"_id": 0})

        assert january["status"] == "matched"
        assert len(january["evidence"]) == 1
        assert january["evidence"][0]["tax_month"] == 1
        assert february["status"] in {"missing", "overdue"}
        assert february["evidence"] == []
        assert periodic["status"] == "matched"
        assert source_after == source_before

    _run(scenario())


def test_due_obblighi_identici_non_riutilizzano_la_stessa_riga_f24():
    async def scenario():
        db = _database()
        engine = OperationalLearningEngine(db)
        first = build_tax_obligation(
            tax_code="1040",
            year=2026,
            due_date="2026-08-16",
            expected_amount="210,00",
            source_id="source-a",
            period="07/2026",
        )
        second = build_tax_obligation(
            tax_code="1040",
            year=2026,
            due_date="2026-08-16",
            expected_amount="210,00",
            source_id="source-b",
            period="07/2026",
        )
        await engine.upsert_expected_event(first)
        await engine.upsert_expected_event(second)
        await db[COLL_F24].insert_one(
            {
                "id": "f24-one-row",
                "data_pagamento": "2026-08-16",
                "sezione_erario": [
                    {
                        "codice_tributo": "1040",
                        "anno_riferimento": "2026",
                        "periodo_riferimento": "0701",
                        "importo_debito": "210,00",
                    }
                ],
            }
        )
        await engine.reconcile_expected_tax_events()
        stored = await db[COLL_EXPECTED_EVENTS].find(
            {"id": {"$in": [first["id"], second["id"]]}}, {"_id": 0}
        ).to_list(length=2)
        assert len(stored) == 2
        assert {item["status"] for item in stored} == {"ambiguous"}
        assert all(item["evidence"] == [] for item in stored)

    _run(scenario())


def test_righe_f24_identiche_reali_non_sono_collassate_dagli_alias():
    row = {
        "codice_tributo": "1040",
        "anno_riferimento": "2026",
        "periodo_riferimento": "0701",
        "importo_debito": "210,00",
    }
    document = {
        "sezione_erario": {"righe": [deepcopy(row), deepcopy(row)]},
        "tributi": [deepcopy(row), deepcopy(row)],
    }

    normalized = OperationalLearningEngine._f24_rows(document)

    assert len(normalized) == 2
    assert [item["_assistant_section_index"] for item in normalized] == [0, 1]
    assert all(item["_assistant_section"] == "sezione_erario" for item in normalized)


def test_motore_scrive_solo_memoria_assistente_ed_e_idempotente():
    async def scenario():
        db = _database()
        engine = OperationalLearningEngine(db)
        with pytest.raises(RuntimeError):
            engine._write_collection("fatture")
        with pytest.raises(ValueError):
            await engine.remember_case(
                {"case_type": "f24", "title": "Ipotesi", "resolution": "Non confermata"}
            )
        await engine.remember_case(
            {
                "case_type": "f24",
                "title": "Annualita' verificata",
                "resolution": "Confermata dallo studio",
                "outcome_status": "confirmed",
            }
        )
        kwargs = {
            "source": "trusted_email_document",
            "source_version": "message-1",
            "payload": {"sender": "studio@example.it", "document_id": "doc-1"},
        }
        first = await engine.record_observation(**kwargs)
        second = await engine.record_observation(**kwargs)
        assert first["id"] == second["id"]
        assert await db[COLL_CASE_MEMORY].count_documents({}) == 1
        assert await db[COLL_KNOWLEDGE_SOURCES].count_documents({}) == 1

    _run(scenario())


def test_mittenti_attendibili_supportano_legacy_wildcard_e_disattivazione():
    async def scenario():
        db = _database()
        await db["mittenti_attendibili"].insert_many(
            [
                {"indirizzo_email": "studio@example.it", "tipo_documento": "f24"},
                {
                    "indirizzo_email": "*@paghe.example.it",
                    "tipo_documento": "cedolino",
                    "canale": "gmail",
                    "attivo": True,
                },
                {
                    "indirizzo_email": "disabled@example.it",
                    "tipo_documento": "generico",
                    "canale": "gmail",
                    "attivo": False,
                },
            ]
        )
        rules = await trusted_sender_rules(db, canale="gmail")
        assert sender_matches_trusted_rules("Studio <studio@example.it>", "f24", rules)
        assert sender_matches_trusted_rules("ufficio@paghe.example.it", "cedolino", rules)
        assert not sender_matches_trusted_rules("disabled@example.it", "f24", rules)
        assert not sender_matches_trusted_rules("studio@example.it", "cedolino", rules)

    _run(scenario())
