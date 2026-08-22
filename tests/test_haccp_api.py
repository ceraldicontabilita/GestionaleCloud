from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Database
from app.routers.haccp import router
from app.services.sheets_document_store import MemorySheetsClient
from app.utils.dependencies import get_current_admin_user, get_current_user
from app.utils.ruoli import richiedi_scrittura


def _user():
    return {"user_id": "test-admin", "email": "admin@example.test", "role": "admin"}


def _app():
    application = FastAPI()
    application.include_router(router, prefix="/api/haccp")
    application.dependency_overrides[get_current_user] = _user
    application.dependency_overrides[get_current_admin_user] = _user
    application.dependency_overrides[richiedi_scrittura] = _user
    return application


def test_api_preview_sync_and_lot_registration_are_connected():
    original_db = Database.db
    db = MemorySheetsClient()["haccp_api"]
    Database.db = db
    try:
        client = TestClient(_app())
        invoice = {
            "id": "INV-API-1",
            "invoice_key": "API-1",
            "invoice_number": "API/1",
            "invoice_date": "2026-04-02",
            "anno": 2026,
            "supplier_name": "Molino Test",
            "supplier_vat": "IT00000000001",
            "linee": [{
                "numero_linea": "1", "descrizione": "Farina 00",
                "quantita": "10", "unita_misura": "KG",
                "prezzo_unitario": "1.1", "prezzo_totale": "11",
            }],
        }
        import asyncio
        asyncio.run(db.invoices.insert_one(invoice))

        preview = client.get("/api/haccp/sync-preview", params={"anno": 2026})
        assert preview.status_code == 200
        assert preview.json()["new_lines"] == 1

        synced = client.post("/api/haccp/sync-invoices", json={"anno": 2026, "dry_run": False})
        assert synced.status_code == 200
        assert synced.json()["written"] == 1

        lines = client.get("/api/haccp/purchase-lines", params={"anno": 2026})
        assert lines.status_code == 200
        line_id = lines.json()["items"][0]["canonical_id"]

        created = client.post("/api/haccp/lots", json={
            "purchase_line_id": line_id,
            "lot_number": "M-2026-04",
            "expiry_date": "2026-10-31",
            "quantity_received": "10",
            "received_date": "2026-04-03",
        })
        assert created.status_code == 200
        assert created.json()["created"] is True
        assert created.json()["lot"]["invoice_id"] == "INV-API-1"
        lot_id = created.json()["lot"]["canonical_id"]

        movement = client.post(f"/api/haccp/lots/{lot_id}/movements", json={
            "movement_type": "CONSUMO",
            "quantity": "2",
            "reason": "Produzione test",
            "client_operation_id": "api-movement-0001",
        })
        assert movement.status_code == 200
        assert movement.json()["lot"]["quantity_available"] == "8"
        trace = client.get(f"/api/haccp/lots/{lot_id}/trace")
        assert trace.status_code == 200
        assert len(trace.json()["movements"]) == 1

        repeated = client.post("/api/haccp/lots", json={
            "purchase_line_id": line_id,
            "lot_number": "M-2026-04",
            "expiry_date": "2026-10-31",
            "quantity_received": "10",
            "received_date": "2026-04-03",
        })
        assert repeated.status_code == 200
        assert repeated.json()["created"] is False
    finally:
        Database.db = original_db


def test_account_sola_lettura_non_puo_registrare_lotti():
    application = FastAPI()
    application.include_router(router, prefix="/api/haccp")
    application.dependency_overrides[get_current_user] = lambda: {
        "user_id": "reader", "role": "sola_lettura"
    }
    response = TestClient(application).post("/api/haccp/lots", json={
        "purchase_line_id": "line-1",
        "lot_number": "LOT-1",
        "expiry_date": "2026-10-31",
        "quantity_received": "1",
        "received_date": "2026-04-03",
    })
    assert response.status_code == 403


def test_api_registri_ricette_e_produzioni_condividono_il_modulo_haccp():
    original_db = Database.db
    db = MemorySheetsClient()["haccp_full_api"]
    Database.db = db
    try:
        client = TestClient(_app())
        equipment = client.post("/api/haccp/equipment", json={
            "name": "Frigo laboratorio",
            "equipment_type": "FRIGO",
            "threshold_min": "0",
            "threshold_max": "4",
            "location": "Laboratorio",
            "client_operation_id": "api-equipment-0001",
        })
        assert equipment.status_code == 200

        control = client.post("/api/haccp/registers", json={
            "register_type": "TEMPERATURA_POSITIVA",
            "event_date": "2026-08-22",
            "subject": "Frigo laboratorio",
            "operator": "Operatore test",
            "client_operation_id": "api-control-0001",
            "value": "8",
            "equipment_id": equipment.json()["equipment"]["canonical_id"],
        })
        assert control.status_code == 200
        assert control.json()["entry"]["compliant"] is False
        expectations = client.get("/api/haccp/expectations", params={"anno": 2026})
        assert expectations.status_code == 200
        assert expectations.json()["total"] == 1

        recipe = client.post("/api/haccp/recipes", json={
            "name": "Brioche test",
            "department": "PASTICCERIA",
            "yield_quantity": "12",
            "yield_unit": "pezzi",
            "ingredients": [{
                "name": "Farina", "quantity": "1", "unit": "kg",
                "allergens": ["glutine"],
            }],
            "instructions": "Impastare",
            "allergens": [],
            "shelf_life_days": 2,
            "storage": "Ambiente asciutto",
            "client_operation_id": "api-recipe-0001",
        })
        assert recipe.status_code == 200
        recipe_id = recipe.json()["recipe"]["canonical_id"]
        import asyncio
        asyncio.run(db.haccp_lots.insert_one({
            "id": "api-source-lot",
            "canonical_id": "api-source-lot",
            "lot_number": "FAR-API-1",
            "product_description": "Farina",
            "quantity_received": "5",
            "quantity_available": "5",
            "unit": "kg",
            "status": "ATTIVO",
        }))
        production = client.post("/api/haccp/productions", json={
            "recipe_id": recipe_id,
            "production_date": "2026-08-22",
            "quantity": "12",
            "unit": "pezzi",
            "lot_number": "BRI-220826",
            "ingredient_lots": [{"lot_id": "api-source-lot", "quantity": "1"}],
            "operator": "Operatore test",
            "notes": "",
            "production_kind": "STANDARD",
            "recovery_from_id": "",
            "client_operation_id": "api-production-0001",
        })
        assert production.status_code == 200
        assert production.json()["production"]["status"] == "SODDISFATTO"
        overview = client.get("/api/haccp/overview", params={"anno": 2026})
        assert overview.status_code == 200
        assert overview.json()["register_entries"] == 1
        assert overview.json()["open_expectations"] == 1
        assert overview.json()["recipes"] == 1
        assert overview.json()["productions"] == 1
    finally:
        Database.db = original_db
