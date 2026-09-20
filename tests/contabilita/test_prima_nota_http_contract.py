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
