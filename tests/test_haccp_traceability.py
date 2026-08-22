import asyncio

from app.services.haccp_traceability import (
    build_purchase_lines,
    create_lot_from_purchase_line,
    lot_trace,
    record_lot_movement,
    sync_invoice_lines,
)
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    return asyncio.run(coro)


def _invoice():
    return {
        "id": "INV-2026-1",
        "invoice_key": "10_IT01234567890_2026-02-03",
        "invoice_number": "10",
        "invoice_date": "2026-02-03",
        "anno": 2026,
        "supplier_name": "Forni Campania Srl",
        "supplier_vat": "IT01234567890",
        "linee": [
            {
                "numero_linea": "1",
                "descrizione": "Farina tipo 00",
                "quantita": "25,00",
                "unita_misura": "KG",
                "prezzo_unitario": "1,20",
                "prezzo_totale": "30,00",
                "altri_dati_gestionali": [],
            },
            {"numero_linea": "2", "descrizione": "Spese di trasporto", "prezzo_totale": "5,00"},
        ],
    }


def test_build_purchase_lines_non_inventa_lotto_e_scadenza():
    items = build_purchase_lines(_invoice())
    assert len(items) == 1
    assert items[0]["quantity"] == "25"
    assert items[0]["unit_price"] == "1.2"
    assert items[0]["document_lot_number"] == ""
    assert items[0]["document_expiry_date"] == ""
    assert items[0]["status"] == "DA_VERIFICARE"
    assert set(items[0]["missing_fields"]) == {"lot_number", "expiry_date"}


def test_sync_2026_e_idempotente_e_non_importa_altri_anni():
    async def scenario():
        db = MemorySheetsClient()["haccp_sync"]
        await db.invoices.insert_one(_invoice())
        old = _invoice()
        old.update({"id": "INV-2025-1", "invoice_key": "OLD", "anno": 2025, "invoice_date": "2025-02-03"})
        await db.invoices.insert_one(old)
        first = await sync_invoice_lines(db, 2026, dry_run=False)
        second = await sync_invoice_lines(db, 2026, dry_run=False)
        records = await db.haccp_purchase_lines.find({}).to_list(20)
        return first, second, records

    first, second, records = _run(scenario())
    assert first["written"] == 1
    assert second["written"] == 0
    assert len(records) == 1
    assert records[0]["anno"] == 2026


def test_registrazione_lotto_richiede_dati_osservati_ed_e_idempotente():
    async def scenario():
        db = MemorySheetsClient()["haccp_lot"]
        await db.invoices.insert_one(_invoice())
        await sync_invoice_lines(db, 2026, dry_run=False)
        line = await db.haccp_purchase_lines.find_one({})
        first = await create_lot_from_purchase_line(
            db,
            purchase_line_id=line["canonical_id"],
            lot_number="FC-260203",
            expiry_date="2026-08-31",
            quantity_received="25,00",
            received_date="2026-02-04",
            user_id="operatore@example.test",
        )
        second = await create_lot_from_purchase_line(
            db,
            purchase_line_id=line["canonical_id"],
            lot_number="FC-260203",
            expiry_date="2026-08-31",
            quantity_received="25",
            received_date="2026-02-04",
            user_id="operatore@example.test",
        )
        updated = await db.haccp_purchase_lines.find_one({"canonical_id": line["canonical_id"]})
        return first, second, updated

    first, second, updated = _run(scenario())
    assert first[1] is True
    assert second[1] is False
    assert first[0]["quantity_available"] == "25"
    assert updated["status"] == "SODDISFATTO"


def test_una_riga_fattura_puo_essere_ricevuta_in_piu_lotti():
    async def scenario():
        db = MemorySheetsClient()["haccp_split_lots"]
        await db.invoices.insert_one(_invoice())
        await sync_invoice_lines(db, 2026, dry_run=False)
        line = await db.haccp_purchase_lines.find_one({})
        await create_lot_from_purchase_line(
            db, purchase_line_id=line["canonical_id"], lot_number="A",
            expiry_date="2026-08-01", quantity_received="10",
            received_date="2026-02-04", user_id="op",
        )
        partial = await db.haccp_purchase_lines.find_one({"canonical_id": line["canonical_id"]})
        await create_lot_from_purchase_line(
            db, purchase_line_id=line["canonical_id"], lot_number="B",
            expiry_date="2026-09-01", quantity_received="15",
            received_date="2026-02-04", user_id="op",
        )
        complete = await db.haccp_purchase_lines.find_one({"canonical_id": line["canonical_id"]})
        return partial, complete

    partial, complete = _run(scenario())
    assert partial["status"] == "IN_ELABORAZIONE"
    assert partial["quantity_remaining"] == "15"
    assert complete["status"] == "SODDISFATTO"
    assert complete["quantity_received_total"] == "25"


def test_movimenti_lotto_sono_idempotenti_e_non_possono_superare_la_disponibilita():
    async def scenario():
        db = MemorySheetsClient()["haccp_movements"]
        await db.invoices.insert_one(_invoice())
        await sync_invoice_lines(db, 2026, dry_run=False)
        line = await db.haccp_purchase_lines.find_one({})
        lot, _ = await create_lot_from_purchase_line(
            db, purchase_line_id=line["canonical_id"], lot_number="A",
            expiry_date="2026-08-01", quantity_received="25",
            received_date="2026-02-04", user_id="op",
        )
        first = await record_lot_movement(
            db, lot_id=lot["canonical_id"], movement_type="CONSUMO",
            quantity="5", reason="Produzione", client_operation_id="op-consumo-1",
            user_id="op",
        )
        repeated = await record_lot_movement(
            db, lot_id=lot["canonical_id"], movement_type="CONSUMO",
            quantity="5", reason="Produzione", client_operation_id="op-consumo-1",
            user_id="op",
        )
        trace = await lot_trace(db, lot["canonical_id"])
        return first, repeated, trace

    first, repeated, trace = _run(scenario())
    assert first[2] is True
    assert repeated[2] is False
    assert trace["lot"]["quantity_available"] == "20"
    assert len(trace["movements"]) == 1
