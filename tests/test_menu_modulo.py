"""Modulo Menu (ex app Menu) sull'app reale, registro in memoria.

Copre il giro completo: la gestione crea il catalogo -> il menu pubblico lo
espone con gli allergeni -> un cliente ordina dal tavolo (sala con coperto e
contanti bloccati) -> la cassa lo vede, lo avanza e lo incassa -> una
sessione del portale dipendenti lavora al banco ma non nella gestione ->
immagini deduplicate per contenuto -> backup JSON esportato e ripristinato ->
magazzino bar condiviso con movimenti.
"""
import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.services.sheets_document_store import SheetDatabase
from app.utils.auth_tokens import create_access_token


@pytest.fixture
def client(monkeypatch):
    from app import database as gestionale_database
    from app.menu import storage

    store = SheetDatabase("test")
    monkeypatch.setattr(gestionale_database.Database, "db", store)
    monkeypatch.setattr(gestionale_database.Database, "client", store)
    storage._blob_cache.clear()

    import app.main as main
    yield TestClient(main.app, raise_server_exceptions=True), store
    storage._blob_cache.clear()


def _h(role, user="u@test"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user, role=role, auth_method='pin')}"}


ADMIN = _h("admin", "admin@test")
OPERATORE = _h("operatore", "op@test")
LETTURA = _h("sola_lettura", "ro@test")
DIPENDENTE = _h("dipendente", "dip-1")


def _catalogo(c):
    cat = c.post("/api/menu/admin/categorie", json={"name": "Bar & Desserts", "nameIT": "Bar e Dolci"}, headers=ADMIN)
    assert cat.status_code == 201, cat.text
    sotto = c.post("/api/menu/admin/sottocategorie", json={"name": "Coffee Shop", "nameIT": "Caffetteria", "category_id": cat.json()["id"]}, headers=OPERATORE)
    assert sotto.status_code == 201, sotto.text
    prod = c.post("/api/menu/admin/prodotti", json={
        "name": "Cappuccino", "nameIT": "Cappuccino", "price": "1.50€", "allergens": ["milk"],
        "category_id": cat.json()["id"], "subcategory_id": sotto.json()["id"],
    }, headers=OPERATORE)
    assert prod.status_code == 201, prod.text
    return cat.json(), sotto.json(), prod.json()


def test_catalogo_e_menu_pubblico(client):
    c, _ = client
    cat, sotto, prod = _catalogo(c)
    assert (cat["id"], sotto["id"], prod["id"]) == (1, 10, 100)

    menu = c.get("/api/menu/pubblico/")
    assert menu.status_code == 200
    albero = menu.json()
    assert [a["id"] for a in albero["allergens"]][:3] == ["gluten", "milk", "eggs"]
    assert albero["categories"][0]["subcategories"][0]["items"][0]["nameIT"] == "Cappuccino"

    assert c.get("/api/menu/pubblico/cerca", params={"q": "capp"}).json()["count"] == 1
    piatto = c.get("/api/menu/admin/prodotti", headers=OPERATORE).json()
    assert piatto["products"][0]["subcategoryName"] == "Caffetteria"

    # Modifica e cancellazione a cascata.
    assert c.put(f"/api/menu/admin/prodotti/{prod['id']}", json={"price": "1.70€"}, headers=OPERATORE).json()["price"] == "1.70€"
    assert c.delete(f"/api/menu/admin/categorie/{cat['id']}", headers=OPERATORE).status_code == 200
    assert c.get("/api/menu/pubblico/").json()["categories"] == []
    assert c.get("/api/menu/admin/prodotti", headers=OPERATORE).json()["total"] == 0


def test_ordine_dal_tavolo_fino_alla_cassa(client):
    c, _ = client
    _, _, prod = _catalogo(c)
    sala = c.post("/api/menu/admin/sale", json={"nome": "Dehor", "coperto_attivo": True, "coperto_importo": 1.5, "disabilita_contanti_qr": True}, headers=ADMIN)
    assert sala.status_code == 201
    sala_id = sala.json()["id"]
    assert c.get("/api/menu/pubblico/sale").json()[0]["nome"] == "Dehor"

    righe = [{"product_id": prod["id"], "name": "Cappuccino", "price": "1.50€", "quantity": 2}]
    bloccato = c.post("/api/menu/pubblico/ordini", json={"items": righe, "sala_id": sala_id, "payment_method": "contanti", "numero_coperti": 2})
    assert bloccato.status_code == 400
    assert "contanti" in bloccato.json()["message"]

    ordine = c.post("/api/menu/pubblico/ordini", json={"items": righe, "table": "5", "sala_id": sala_id, "payment_method": "pos", "numero_coperti": 2, "paid": True})
    assert ordine.status_code == 201, ordine.text
    o = ordine.json()
    assert o["total"] == 6.0 and o["totale_coperto"] == 3.0 and o["paid"] is False and o["source"] == "cliente"
    assert c.get(f"/api/menu/pubblico/ordini/{o['id']}").json()["status"] == "nuovo"

    # Senza sessione le schermate di banco restano chiuse.
    assert c.get("/api/menu/staff/ordini").status_code == 401

    attivi = c.get("/api/menu/staff/ordini", params={"active_only": True}, headers=DIPENDENTE).json()
    assert [x["id"] for x in attivi] == [o["id"]]
    assert c.patch(f"/api/menu/staff/ordini/{o['id']}/stato", json={"status": "pronto"}, headers=DIPENDENTE).json()["status"] == "pronto"
    pagato = c.patch(f"/api/menu/staff/ordini/{o['id']}/pagamento", json={"paid": True, "payment_method": "pos"}, headers=DIPENDENTE).json()
    assert pagato["paid"] is True

    cassa = c.post("/api/menu/staff/ordini", json={"items": righe, "source": "cliente", "paid": True, "payment_method": "contanti"}, headers=DIPENDENTE)
    assert cassa.status_code == 201
    assert cassa.json()["source"] == "cassa" and cassa.json()["paid"] is True and cassa.json()["created_by"] == "dip-1"

    assert c.post("/api/menu/staff/ordini", json={"items": []}, headers=DIPENDENTE).status_code == 400
    assert c.patch(f"/api/menu/staff/ordini/{o['id']}/stato", json={"status": "boh"}, headers=DIPENDENTE).status_code == 400


def test_perimetro_ruoli(client, monkeypatch):
    c, _ = client
    # Il perimetro non deve mai toccare la rete reale: la sincronizzazione da
    # Qromo qui serve solo a verificare chi puo' avviarla, non il suo esito.
    import app.menu.migrazione_qromo as migrazione_qromo

    async def _finta_sincronizzazione(**_kwargs):
        return {"dry_run": True, "sottodominio": "test", "tabelle": {}, "immagini_scaricate": 0, "immagini_non_scaricate": 0, "coincide": True}

    monkeypatch.setattr(migrazione_qromo, "sincronizza", _finta_sincronizzazione)
    # Il portale dipendenti lavora al banco ma non entra nella gestione del menu.
    assert c.get("/api/menu/staff/sale", headers=DIPENDENTE).status_code == 200
    assert c.get("/api/menu/admin/prodotti", headers=DIPENDENTE).status_code == 403
    # Sola lettura: legge, non scrive.
    assert c.get("/api/menu/staff/ordini", headers=LETTURA).status_code == 200
    assert c.post("/api/menu/staff/ordini", json={"items": [{"name": "x", "price": "1"}]}, headers=LETTURA).status_code == 403
    assert c.get("/api/menu/admin/prodotti", headers=LETTURA).status_code == 403
    # Ripristino e sincronizzazione da Qromo: solo admin.
    assert c.post("/api/menu/admin/backup/ripristina", json={"formato": "x"}, headers=OPERATORE).status_code == 403
    assert c.post("/api/menu/admin/migrazione-qromo", json={}, headers=OPERATORE).status_code == 403
    job = c.post("/api/menu/admin/migrazione-qromo", json={"dry_run": True}, headers=ADMIN)
    assert job.status_code == 200 and job.json()["status"] in ("queued", "running")
    assert c.get(f"/api/menu/admin/migrazione-qromo/{job.json()['id']}", headers=ADMIN).status_code == 200
    assert c.get("/api/menu/admin/migrazione-qromo/inesistente", headers=ADMIN).status_code == 404


def test_immagine_con_scheda_ma_senza_file_viene_riscritta(client):
    """Scheda in menu_immagini senza il blob (immagini importate su Sheets con
    l'archivio binari in memoria, poi copiate su Supabase): ricaricare lo
    stesso contenuto deve riscrivere il file, non rispondere 'gia' presente'."""
    from app.menu import storage

    c, _ = client
    png = b"\x89PNG\r\n\x1a\n" + b"1" * 64
    up = c.post("/api/menu/admin/immagini", files={"file": ("foto.png", io.BytesIO(png), "image/png")}, headers=OPERATORE)
    assert up.status_code == 201, up.text
    url = up.json()["url"]
    assert c.get(url).status_code == 200

    # Il file sparisce, la scheda resta: e' esattamente lo stato trovato in produzione.
    scheda = asyncio.run(storage.uno(storage.COLL_IMMAGINI, {"id": up.json()["id"]}))
    asyncio.run(storage.blobs().delete([scheda["blob_key"]]))
    assert c.get(url).status_code == 404

    di_nuovo = c.post("/api/menu/admin/immagini", files={"file": ("foto.png", io.BytesIO(png), "image/png")}, headers=OPERATORE)
    assert di_nuovo.status_code in (200, 201)
    assert di_nuovo.json()["id"] == up.json()["id"]
    servita = c.get(url)
    assert servita.status_code == 200 and servita.content == png


def test_immagini_deduplicate_e_backup(client):
    c, _ = client
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    up1 = c.post("/api/menu/admin/immagini", files={"file": ("logo.png", io.BytesIO(png), "image/png")}, headers=OPERATORE)
    assert up1.status_code == 201, up1.text
    up2 = c.post("/api/menu/admin/immagini", files={"file": ("copia.png", io.BytesIO(png), "image/png")}, headers=OPERATORE)
    assert up2.json()["id"] == up1.json()["id"]
    assert len(c.get("/api/menu/admin/immagini", headers=OPERATORE).json()["images"]) == 1
    assert c.post("/api/menu/admin/immagini", files={"file": ("x.txt", io.BytesIO(b"ciao"), "text/plain")}, headers=OPERATORE).status_code == 400

    url = up1.json()["url"]
    servita = c.get(url)
    assert servita.status_code == 200 and servita.content == png and servita.headers["content-type"] == "image/png"

    _catalogo(c)
    c.put("/api/menu/admin/prodotti/100", json={"image": url}, headers=OPERATORE)
    backup = c.get("/api/menu/admin/backup/esporta", headers=ADMIN)
    assert backup.status_code == 200
    dump = backup.json()
    assert dump["formato"] == "gestionalecloud-menu/1"
    assert len(dump["collezioni"]["menu_products"]) == 1 and len(dump["blob_immagini"]) == 1

    # Svuoto e ripristino: stesso catalogo, stessa immagine servita.
    assert c.delete("/api/menu/admin/immagini/" + up1.json()["id"], headers=OPERATORE).status_code == 200
    assert c.get(url).status_code == 404
    c.delete("/api/menu/admin/categorie/1", headers=ADMIN)
    rip = c.post("/api/menu/admin/backup/ripristina", json=json.loads(json.dumps(dump)), headers=ADMIN)
    assert rip.status_code == 200, rip.text
    assert rip.json()["ripristinato"]["menu_products"] == 1
    assert c.get("/api/menu/pubblico/").json()["categories"][0]["subcategories"][0]["items"][0]["image"] == url
    assert c.get(url).content == png

    stato = c.get("/api/menu/admin/stato-dati", headers=ADMIN).json()
    assert stato["collezioni"]["menu_products"] == 1


def test_magazzino_bar_condiviso(client):
    c, store = client
    import asyncio
    # Articolo gia' presente nella collezione di Lotti (campi di Lotti).
    asyncio.run(store["magazzino_bar_prodotti"].insert_one({"_id": "l1", "id": "l1", "nome": "Acqua naturale", "unita": "cartone", "stock": 4, "min_threshold": 6}))

    lista = c.get("/api/menu/staff/magazzino/articoli", headers=DIPENDENTE).json()
    assert lista[0] == {**lista[0], "name": "Acqua naturale", "unit": "cartone", "quantity": 4.0, "min_threshold": 6.0}
    assert len(c.get("/api/menu/staff/magazzino/articoli", params={"low_stock_only": True}, headers=DIPENDENTE).json()) == 1

    nuovo = c.post("/api/menu/staff/magazzino/articoli", json={"name": "Birra Peroni", "unit": "cartone", "quantity": 10, "category": "Bar"}, headers=DIPENDENTE)
    assert nuovo.status_code == 201
    doc = asyncio.run(store["magazzino_bar_prodotti"].find_one({"id": nuovo.json()["id"]}))
    assert doc["nome"] == "Birra Peroni" and doc["stock"] == 10.0 and doc["categoria"] == "Bar"

    mov = c.post("/api/menu/staff/magazzino/articoli/l1/movimento", json={"type": "carico", "quantity": 12}, headers=DIPENDENTE)
    assert mov.status_code == 200 and mov.json()["quantity"] == 16.0
    mov = c.post("/api/menu/staff/magazzino/articoli/l1/movimento", json={"type": "scarico", "quantity": 1.5, "note": "sfrido"}, headers=DIPENDENTE)
    assert mov.json()["quantity"] == 14.5
    storico = c.get("/api/menu/staff/magazzino/movimenti", params={"item_id": "l1"}, headers=DIPENDENTE).json()
    assert [m["type"] for m in storico] == ["scarico", "carico"] and storico[0]["operatore"] == "dip-1"
    assert c.post("/api/menu/staff/magazzino/articoli/l1/movimento", json={"type": "boh", "quantity": 1}, headers=DIPENDENTE).status_code == 400

    assert c.put("/api/menu/staff/magazzino/articoli/l1", json={"supplier": "Big Food"}, headers=DIPENDENTE).json()["supplier"] == "Big Food"
    assert c.delete("/api/menu/staff/magazzino/articoli/l1", headers=DIPENDENTE).status_code == 200
    assert c.delete("/api/menu/staff/magazzino/articoli/l1", headers=DIPENDENTE).status_code == 404


def test_config_qr_pubblico_senza_password(client):
    c, _ = client
    r = c.put("/api/menu/admin/qrcode/config", json={"menu_url": "https://gestionale.example/menu", "wifi": {"ssid": "Ceraldi", "password": "segreta", "security": "WPA"}}, headers=OPERATORE)
    assert r.status_code == 200 and r.json()["config"]["updated_by"] == "op@test"
    pubblico = c.get("/api/menu/pubblico/qrcode/config").json()
    assert pubblico == {"menu_url": "https://gestionale.example/menu"}
    assert c.get("/api/menu/admin/qrcode/config", headers=OPERATORE).json()["wifi"]["password"] == "segreta"
