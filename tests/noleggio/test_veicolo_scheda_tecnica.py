"""Il salvataggio del veicolo conserva telaio, data di immatricolazione e CV, oltre ai campi gia' ammessi."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def test_put_veicolo_salva_i_campi_della_scheda_tecnica(monkeypatch):
    from app.database import Database
    from app.routers import noleggio as router_noleggio

    db = ClientArchivioMemoria()["scheda-tecnica"]
    asyncio.run(db["veicoli_noleggio"].insert_one({"id": "car-1", "targa": "AB123CD"}))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router_noleggio.router, prefix="/api/noleggio")
    scheda = {"telaio": "WBA15GR060N372203", "data_immatricolazione": "2025-10-13", "anno_immatricolazione": 2025,
              "potenza_kw": 110, "potenza_cv": 150, "cilindrata": 1995, "alimentazione": "diesel"}
    assert TestClient(app).put("/api/noleggio/veicoli/AB123CD", json=scheda).status_code == 200
    salvato = asyncio.run(db["veicoli_noleggio"].find_one({"targa": "AB123CD"}))
    assert {k: salvato[k] for k in scheda} == scheda
