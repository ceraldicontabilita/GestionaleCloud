"""Backend Menu per il collaudo browser: tutte le scritture restano in memoria.

Avvio: python -m uvicorn tests.menu.e2e_server:app --port 8790
Nessuno startup ERP, client Supabase reale o sync Qromo.
"""
import os
from copy import deepcopy

for nome in list(os.environ):
    if nome.startswith(("MENU_", "SUPABASE_", "HR_", "LOTTI_", "GOOGLE_", "GMAIL_")):
        os.environ.pop(nome, None)
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["ENABLE_QROMO_AUTO_SYNC"] = "false"
os.environ["MENU_JWT_SECRET"] = "menu-e2e-isolato-solo-test-non-produzione"

from fastapi import FastAPI

from app.menu import carta_qromo
from app.menu.routes import allergeni_routes, menu_routes, qrcode_routes
from app.menu.server import app as menu_app
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from tests.menu.test_menu_public_visible import _FakeSupabase

client = _FakeSupabase({
    "menu_categories": [{"id": 1, "name": "Test", "name_it": "Menu di prova"}],
    "menu_subcategories": [{"id": 10, "category_id": 1, "name": "Test", "name_it": "Sezione di prova"}],
    "menu_products": [{"id": 100, "category_id": 1, "subcategory_id": 10,
                       "name": "Test", "name_it": "Prodotto di prova", "price": "2.50€",
                       "description_it": "Ingredienti di prova", "allergens": ["milk"], "visible": True},
                      {"id": 101, "category_id": 1, "subcategory_id": 10,
                       "name": "Lotti", "name_it": "Ricetta di prova", "price": "4.00€",
                       "allergens": ["eggs"], "origine": "lotti", "visible": True}],
    "menu_allergens": [{"id": "milk", "name": "Milk", "name_it": "Latte", "icon": ""},
                       {"id": "eggs", "name": "Eggs", "name_it": "Uova", "icon": ""}],
    "menu_allergeni_esclusioni": [],
    "menu_qrcode_config": [{"id": "qrcode_config", "menu_url": "https://example.invalid/menu/"}],
})
dati_iniziali = deepcopy(client.tabelle)
for modulo in (menu_routes, allergeni_routes, qrcode_routes):
    modulo.supabase = client

db = ClientArchivioMemoria()["menu_e2e_isolato"]


async def _db():
    return db


carta_qromo._db = _db
menu_app.dependency_overrides[qrcode_routes.verify_token] = lambda: "admin_isolato"

app = FastAPI(title="Menu collaudo isolato")


@app.get("/__fixture__/health")
async def salute_fixture():
    return {"fixture": "menu-e2e-isolato"}


@app.post("/__fixture__/reset")
async def reset_fixture():
    client.tabelle.clear()
    client.tabelle.update(deepcopy(dati_iniziali))
    client.chiamate.clear()
    return {"fixture": "menu-e2e-isolato", "reset": True}


@app.get("/api/sezioni")
async def sezioni():
    return {"sezioni": []}


app.mount("/menu", menu_app)
