import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.entity_relations import (
    relation_key,
    revoke_entity_relation,
    upsert_entity_relation,
)
from app.services.payment_invoice_matching import money_cents


def test_money_cents_accetta_formato_euro_italiano_con_spazi():
    assert money_cents("€ 1.234,56") == 123456


def test_relation_key_e_deterministica_e_direzionale():
    assert relation_key(
        "bonifico_pdf", "b1", "documents_invoice_payment", "invoice", "f1"
    ) == "bonifico_pdf|b1|documents_invoice_payment|invoice|f1"


def test_upsert_relazione_e_idempotente_e_non_copia_documenti():
    collection = MagicMock(update_one=AsyncMock())
    db = SimpleNamespace(entity_relations=collection)
    kwargs = dict(
        source_type="bonifico_pdf",
        source_id="b1",
        relation_type="documents_invoice_payment",
        target_type="invoice",
        target_id="f1",
        status="confirmed",
        rule="invoice_number+exact_cents+supplier_identity",
        evidence=[
            {"type": "invoice_number", "value": "FT-88"},
            {"type": "invoice_number", "value": "FT-88"},
        ],
        amount="€ 120,50",
        provenance={"sha256": "abc", "filename": "bonifico.pdf"},
    )

    first = asyncio.run(upsert_entity_relation(db, **kwargs))
    second = asyncio.run(upsert_entity_relation(db, **kwargs))

    assert first == second
    assert collection.update_one.await_count == 2
    call = collection.update_one.await_args
    assert call.args[0] == {"relation_key": first}
    assert call.kwargs["upsert"] is True
    stored = call.args[1]["$set"]
    assert stored["amount_cents"] == 12050
    assert stored["evidence"] == [{"type": "invoice_number", "value": "FT-88"}]
    assert "pdf_data" not in str(call)


def test_revoca_conserva_la_traccia_senza_cancellare():
    result = SimpleNamespace(matched_count=1)
    collection = MagicMock(update_one=AsyncMock(return_value=result))
    db = SimpleNamespace(entity_relations=collection)

    revoked = asyncio.run(
        revoke_entity_relation(
            db,
            source_type="bonifico_pdf",
            source_id="b1",
            relation_type="documents_invoice_payment",
            target_type="invoice",
            target_id="f1",
            actor="manual_unlink",
        )
    )

    assert revoked is True
    update = collection.update_one.await_args.args[1]
    assert update["$set"]["status"] == "revoked"
    assert "$unset" not in update
