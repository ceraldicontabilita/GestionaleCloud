import asyncio

from app.services.haccp_operations import (
    create_register_entry,
    register_production,
    resolve_register_entry,
    save_equipment,
    save_recipe,
)
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    return asyncio.run(coro)


def test_non_conformita_crea_attesa_e_la_correzione_la_soddisfa():
    async def scenario():
        db = MemorySheetsClient()["haccp_register"]
        equipment, _ = await save_equipment(
            db,
            name="Frigo laboratorio",
            equipment_type="FRIGO",
            threshold_min="0",
            threshold_max="4",
            location="Laboratorio",
            client_operation_id="equipment-frigo-1",
            user_id="admin",
        )
        entry, created = await create_register_entry(
            db,
            register_type="TEMPERATURA_POSITIVA",
            event_date="2026-08-22",
            subject="Frigo laboratorio",
            operator="Mario",
            client_operation_id="temperature-check-1",
            value="7,5",
            equipment_id=equipment["canonical_id"],
            user_id="mario",
        )
        repeated, repeated_created = await create_register_entry(
            db,
            register_type="TEMPERATURA_POSITIVA",
            event_date="2026-08-22",
            subject="Frigo laboratorio",
            operator="Mario",
            client_operation_id="temperature-check-1",
            value="7,5",
            equipment_id=equipment["canonical_id"],
            user_id="mario",
        )
        expectation = await db.haccp_expectations.find_one({"source_fact_id": entry["canonical_id"]})
        resolved = await resolve_register_entry(
            db,
            entry_id=entry["canonical_id"],
            corrective_action="Trasferita la merce e verificato il termostato",
            verification_notes="Seconda lettura nella norma",
            user_id="admin",
        )
        closed = await db.haccp_expectations.find_one({"source_fact_id": entry["canonical_id"]})
        return created, repeated_created, entry, repeated, expectation, resolved, closed

    created, repeated_created, entry, repeated, expectation, resolved, closed = _run(scenario())
    assert created is True
    assert repeated_created is False
    assert repeated["canonical_id"] == entry["canonical_id"]
    assert entry["compliant"] is False
    assert entry["threshold_max"] == "4"
    assert expectation["status"] == "ATTESO"
    assert resolved["status"] == "SODDISFATTO"
    assert closed["status"] == "SODDISFATTO"
    assert closed["evidence_ids"]


def test_chiusura_non_conformita_ripetuta_non_crea_nuova_evidenza():
    async def scenario():
        db = MemorySheetsClient()["haccp_resolve_retry"]
        entry, _ = await create_register_entry(
            db,
            register_type="SANIFICAZIONE",
            event_date="2026-08-22",
            subject="Banco laboratorio",
            operator="Mario",
            client_operation_id="sanitation-retry-1",
            compliant=False,
            user_id="mario",
        )
        first = await resolve_register_entry(
            db, entry_id=entry["canonical_id"], corrective_action="Ripetuta sanificazione",
            verification_notes="Controllo visivo", user_id="admin",
        )
        second = await resolve_register_entry(
            db, entry_id=entry["canonical_id"], corrective_action="Ripetuta sanificazione",
            verification_notes="Controllo visivo", user_id="admin",
        )
        return first, second

    first, second = _run(scenario())
    assert first["corrective_evidence_id"] == second["corrective_evidence_id"]


def test_ricetta_versionata_e_produzione_consumano_lotti_senza_duplicare():
    async def scenario():
        db = MemorySheetsClient()["haccp_production"]
        lot = {
            "id": "lot-flour",
            "canonical_id": "lot-flour",
            "lot_number": "FAR-1",
            "product_description": "Farina",
            "quantity_received": "10",
            "quantity_available": "10",
            "unit": "kg",
            "status": "ATTIVO",
        }
        await db.haccp_lots.insert_one(lot)
        recipe, created = await save_recipe(
            db,
            name="Pane",
            department="FORNO",
            yield_quantity="20",
            yield_unit="pezzi",
            ingredients=[{"name": "Farina", "quantity": "5", "unit": "kg", "allergens": ["glutine"]}],
            instructions="Impastare e cuocere",
            allergens=[],
            shelf_life_days=2,
            storage="Ambiente asciutto",
            client_operation_id="recipe-pane-2026",
            user_id="admin",
        )
        production, production_created = await register_production(
            db,
            recipe_id=recipe["canonical_id"],
            production_date="2026-08-22",
            quantity="20",
            unit="pezzi",
            lot_number="PANE-220826",
            ingredient_lots=[{"lot_id": "lot-flour", "quantity": "5"}],
            operator="Mario",
            notes="",
            production_kind="STANDARD",
            recovery_from_id="",
            client_operation_id="production-pane-1",
            user_id="mario",
        )
        repeated, repeated_created = await register_production(
            db,
            recipe_id=recipe["canonical_id"],
            production_date="2026-08-22",
            quantity="20",
            unit="pezzi",
            lot_number="PANE-220826",
            ingredient_lots=[{"lot_id": "lot-flour", "quantity": "5"}],
            operator="Mario",
            notes="",
            production_kind="STANDARD",
            recovery_from_id="",
            client_operation_id="production-pane-1",
            user_id="mario",
        )
        source_lot = await db.haccp_lots.find_one({"canonical_id": "lot-flour"})
        output_lot = await db.haccp_lots.find_one({"canonical_id": production["output_lot_id"]})
        movements = await db.haccp_lot_movements.find({"lot_id": "lot-flour"}).to_list(10)
        return created, production_created, repeated_created, production, repeated, source_lot, output_lot, movements

    created, production_created, repeated_created, production, repeated, source_lot, output_lot, movements = _run(scenario())
    assert created is True
    assert production_created is True
    assert repeated_created is False
    assert repeated["canonical_id"] == production["canonical_id"]
    assert production["status"] == "SODDISFATTO"
    assert source_lot["quantity_available"] == "5"
    assert output_lot["quantity_available"] == "20"
    assert len(movements) == 1
    assert "GLUTINE" in _run(_recipe_allergens())


def test_retry_di_produzione_parziale_non_scarica_due_volte_il_lotto():
    async def scenario():
        db = MemorySheetsClient()["haccp_production_retry"]
        await db.haccp_lots.insert_one({
            "id": "lot-retry", "canonical_id": "lot-retry", "lot_number": "R-1",
            "quantity_received": "5", "quantity_available": "5", "unit": "kg", "status": "ATTIVO",
        })
        recipe, _ = await save_recipe(
            db, name="Retry", department="FORNO", yield_quantity="1", yield_unit="pezzo",
            ingredients=[{"name": "Farina", "quantity": "5", "unit": "kg"}],
            instructions="", allergens=[], shelf_life_days=1, storage="",
            client_operation_id="recipe-retry-prod", user_id="admin",
        )
        from app.services.haccp_operations import _canonical, _operation_id
        from app.services.haccp_traceability import record_lot_movement
        production_id = _canonical("haccp_production", "production-partial-retry")
        operation_id = _operation_id(production_id)
        await db.haccp_productions.insert_one({
            "id": production_id, "canonical_id": production_id, "status": "IN_ELABORAZIONE",
        })
        await record_lot_movement(
            db, lot_id="lot-retry", movement_type="CONSUMO", quantity="5",
            reason="Produzione interrotta", client_operation_id=f"{operation_id}:ingredient:1",
            user_id="admin",
        )
        production, created = await register_production(
            db, recipe_id=recipe["canonical_id"], production_date="2026-08-22",
            quantity="1", unit="pezzo", lot_number="RETRY-1",
            ingredient_lots=[{"lot_id": "lot-retry", "quantity": "5"}], operator="admin",
            notes="", production_kind="STANDARD", recovery_from_id="",
            client_operation_id="production-partial-retry", user_id="admin",
        )
        movements = await db.haccp_lot_movements.find({"lot_id": "lot-retry"}).to_list(10)
        return production, created, movements

    production, created, movements = _run(scenario())
    assert created is False
    assert production["status"] == "SODDISFATTO"
    assert len(movements) == 1


async def _recipe_allergens():
    db = MemorySheetsClient()["haccp_recipe_allergens"]
    recipe, _ = await save_recipe(
        db,
        name="Test",
        department="FORNO",
        yield_quantity="1",
        yield_unit="pezzo",
        ingredients=[{"name": "Farina", "quantity": "1", "unit": "kg", "allergens": ["glutine"]}],
        instructions="",
        allergens=[],
        shelf_life_days=None,
        storage="",
        client_operation_id="recipe-allergen-1",
        user_id="admin",
    )
    return recipe["allergens"]
