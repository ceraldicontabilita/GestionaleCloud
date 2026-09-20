"""Contratto HTTP minimo della Prima Nota.

Questi test passano attraverso FastAPI (non chiamano direttamente le funzioni):
servono a intercettare anche errori di response-model/serializzazione che i test
unitari puri non vedono.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Database
from app.routers.prima_nota_module import router as prima_nota_router
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _app_con_db():
    memoria = ClientArchivioMemoria()
    Database.client = memoria
    Database.db = memoria["prima-nota-http-contract"]
    app = FastAPI()
    app.include_router(prima_nota_router, prefix="/api/prima-nota")
    return app, memoria


def test_post_cassa_restituisce_json_valido_e_persistito():
    app, memoria = _app_con_db()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/prima-nota/cassa",
                json={
                    "data": "2026-09-21",
                    "tipo": "entrata",
                    "importo": 125.0,
                    "descrizione": "Contratto HTTP Prima Nota",
                    "categoria": "Altro",
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["id"]
            assert payload["inserimento_manuale"] is True

            elenco = client.get("/api/prima-nota/cassa?anno=2026&limit=20")
            assert elenco.status_code == 200, elenco.text
            dati = elenco.json()
            assert any(
                riga.get("id") == payload["id"] and float(riga.get("importo") or 0) == 125.0
                for riga in dati["movimenti"]
            )
            assert float(dati["saldo"]) == 125.0
    finally:
        memoria.close()
        Database.client = None
        Database.db = None


def test_crud_cassa_aggiorna_saldo_e_soft_delete():
    app, memoria = _app_con_db()
    try:
        with TestClient(app) as client:
            creato = client.post(
                "/api/prima-nota/cassa",
                json={
                    "data": "2026-09-21",
                    "tipo": "uscita",
                    "importo": 40.0,
                    "descrizione": "Spesa contanti E2E contratto",
                    "categoria": "Altro",
                },
            )
            assert creato.status_code == 200, creato.text
            movimento_id = creato.json()["id"]

            modifica = client.put(
                f"/api/prima-nota/cassa/{movimento_id}",
                json={"importo": 55.0, "descrizione": "Spesa contanti corretta"},
            )
            assert modifica.status_code == 200, modifica.text

            elenco = client.get("/api/prima-nota/cassa?anno=2026&limit=20")
            assert elenco.status_code == 200, elenco.text
            assert float(elenco.json()["saldo"]) == -55.0

            eliminato = client.delete(f"/api/prima-nota/cassa/{movimento_id}?force=true")
            assert eliminato.status_code == 200, eliminato.text

            dopo = client.get("/api/prima-nota/cassa?anno=2026&limit=20")
            assert dopo.status_code == 200, dopo.text
            assert dopo.json()["movimenti"] == []
            assert float(dopo.json()["saldo"]) == 0.0
    finally:
        memoria.close()
        Database.client = None
        Database.db = None


def test_update_cassa_rifiuta_importo_non_positivo():
    app, memoria = _app_con_db()
    try:
        with TestClient(app) as client:
            creato = client.post(
                "/api/prima-nota/cassa",
                json={
                    "data": "2026-09-21", "tipo": "entrata", "importo": 10.0,
                    "descrizione": "Movimento da validare",
                },
            )
            movimento_id = creato.json()["id"]
            risposta = client.put(
                f"/api/prima-nota/cassa/{movimento_id}",
                json={"importo": -10},
            )
            assert risposta.status_code == 422, risposta.text
    finally:
        memoria.close()
        Database.client = None
        Database.db = None


def test_crud_banca_manuale_e_validazione_importo():
    app, memoria = _app_con_db()
    try:
        with TestClient(app) as client:
            creato = client.post(
                "/api/prima-nota/banca",
                json={
                    "data": "2026-09-21",
                    "tipo": "entrata",
                    "importo": 80.0,
                    "descrizione": "Movimento banca manuale non collegato a fattura",
                    "categoria": "Altro",
                },
            )
            assert creato.status_code == 200, creato.text
            movimento_id = creato.json()["id"]

            modifica_errata = client.put(
                f"/api/prima-nota/banca/{movimento_id}",
                json={"importo": 0},
            )
            assert modifica_errata.status_code == 422, modifica_errata.text

            modifica = client.put(
                f"/api/prima-nota/banca/{movimento_id}",
                json={"importo": 90.0, "descrizione": "Movimento banca corretto"},
            )
            assert modifica.status_code == 200, modifica.text

            elenco = client.get("/api/prima-nota/banca?anno=2026&limit=20")
            assert elenco.status_code == 200, elenco.text
            dati = elenco.json()
            riga = next(r for r in dati["movimenti"] if r.get("id") == movimento_id)
            assert float(riga.get("importo") or 0) == 90.0
            assert riga["provvisorio"] is True
            assert riga["canonico"] is False
            assert riga["stato"] == "DA_VERIFICARE"
            # Visibile all'operatore, ma senza prova bancaria non e' liquidita'.
            assert float(dati["saldo"]) == 0.0
            assert float(dati["totale_entrate"]) == 0.0

            eliminato = client.delete(f"/api/prima-nota/banca/{movimento_id}?force=true")
            assert eliminato.status_code == 200, eliminato.text
    finally:
        memoria.close()
        Database.client = None
        Database.db = None


def test_cancellazione_pagamento_cassa_riapre_fattura_collegata():
    app, memoria = _app_con_db()
    try:
        db = Database.get_db()
        import asyncio
        asyncio.run(db["invoices"].insert_one({
            "id": "fattura-cassa-http",
            "invoice_number": "C-1",
            "pagato": False,
            "stato_pagamento": "",
        }))
        with TestClient(app) as client:
            creato = client.post(
                "/api/prima-nota/cassa",
                json={
                    "data": "2026-09-21",
                    "tipo": "uscita",
                    "importo": 25.0,
                    "descrizione": "Pagamento contanti fattura",
                    "categoria": "Fatture",
                    "fattura_id": "fattura-cassa-http",
                },
            )
            assert creato.status_code == 200, creato.text
            movimento_id = creato.json()["id"]

            fattura_pagata = asyncio.run(
                db["invoices"].find_one({"id": "fattura-cassa-http"}, {"_id": 0})
            )
            assert fattura_pagata["pagato"] is True
            assert fattura_pagata["prima_nota_cassa_id"] == movimento_id

            eliminato = client.delete(f"/api/prima-nota/cassa/{movimento_id}?force=true")
            assert eliminato.status_code == 200, eliminato.text

            fattura_riaperta = asyncio.run(
                db["invoices"].find_one({"id": "fattura-cassa-http"}, {"_id": 0})
            )
            assert fattura_riaperta["pagato"] is False
            assert not fattura_riaperta.get("prima_nota_cassa_id")
    finally:
        memoria.close()
        Database.client = None
        Database.db = None


def test_attendi_banca_non_segna_pagata_e_non_crea_scrittura_banca():
    app, memoria = _app_con_db()
    try:
        db = Database.get_db()
        import asyncio
        asyncio.run(db["invoices"].insert_one({
            "id": "fattura-attesa-banca-http",
            "invoice_number": "B-ATT",
            "invoice_date": "2026-09-21",
            "supplier_name": "Fornitore Banca",
            "total_amount": 120.0,
            "pagato": False,
            "stato_pagamento": "",
        }))
        with TestClient(app) as client:
            risposta = client.post(
                "/api/prima-nota/provvisori/attendi-banca",
                json={"fattura_id": "fattura-attesa-banca-http"},
            )
            assert risposta.status_code == 200, risposta.text
            fattura = asyncio.run(
                db["invoices"].find_one({"id": "fattura-attesa-banca-http"}, {"_id": 0})
            )
            assert fattura["pagato"] is False
            assert fattura["stato_pagamento"] == "in_attesa_banca"
            assert fattura["stato_finanziario"] == "aperta_in_attesa_banca"
            assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0
    finally:
        memoria.close()
        Database.client = None
        Database.db = None


def test_pagamento_banca_con_evidenza_e_cancellazione_riapre_fattura():
    app, memoria = _app_con_db()
    try:
        db = Database.get_db()
        import asyncio
        asyncio.run(db["estratto_conto_movimenti"].insert_one({
            "id": "ec-http-1",
            "data": "2026-09-21",
            "tipo": "uscita",
            "importo": -75.0,
            "descrizione": "BONIFICO FORNITORE TEST",
        }))
        asyncio.run(db["invoices"].insert_one({
            "id": "fattura-banca-http",
            "invoice_number": "B-1",
            "invoice_date": "2026-09-21",
            "supplier_name": "Fornitore Test",
            "total_amount": 75.0,
            "pagato": False,
            "stato_pagamento": "",
        }))
        with TestClient(app) as client:
            creato = client.post(
                "/api/prima-nota/banca",
                json={
                    "data": "2026-09-21",
                    "tipo": "uscita",
                    "importo": 75.0,
                    "descrizione": "Pagamento banca fattura",
                    "categoria": "Fatture",
                    "fattura_id": "fattura-banca-http",
                    "estratto_conto_id": "ec-http-1",
                },
            )
            assert creato.status_code == 200, creato.text
            movimento_id = creato.json()["id"]

            fattura_pagata = asyncio.run(
                db["invoices"].find_one({"id": "fattura-banca-http"}, {"_id": 0})
            )
            assert fattura_pagata["pagato"] is True
            assert fattura_pagata["prima_nota_banca_id"] == movimento_id

            eliminato = client.delete(f"/api/prima-nota/banca/{movimento_id}?force=true")
            assert eliminato.status_code == 200, eliminato.text

            fattura_riaperta = asyncio.run(
                db["invoices"].find_one({"id": "fattura-banca-http"}, {"_id": 0})
            )
            assert fattura_riaperta["pagato"] is False
            assert not fattura_riaperta.get("prima_nota_banca_id")
    finally:
        memoria.close()
        Database.client = None
        Database.db = None
