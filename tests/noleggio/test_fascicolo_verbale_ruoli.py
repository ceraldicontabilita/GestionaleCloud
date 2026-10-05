"""Nel fascicolo del verbale ogni file ha un solo ruolo: una ricevuta pagoPA non e' anche il «verbale originale»."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _fascicolo(monkeypatch, documenti, **verbale):
    from app.database import Database
    from app.routers import verbali_noleggio as router
    from app.services import verbali_pdf_service as servizio

    db = ClientArchivioMemoria()["fascicolo"]
    asyncio.run(db["verbali_noleggio"].insert_one({"id": "v1", "numero_verbale": "A25111856676", "targa": "GW980EP", **verbale}))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    async def raccogli(*_a, **_k):
        return documenti

    monkeypatch.setattr(servizio, "collect_verbale_pdfs", raccogli)
    monkeypatch.setattr(servizio, "pdf_metadata", lambda docs: docs)
    app = FastAPI()
    app.include_router(router.router)
    return TestClient(app).get("/api/verbali-noleggio/dettaglio/A25111856676").json()["fascicolo"]


def test_la_ricevuta_pagopa_non_e_anche_il_verbale_originale(monkeypatch):
    ricevuta = {"filename": "2025-11-15_1854_pagoPA_30,90EUR.pdf", "source": "verbale_pdf", "tipo": "pdf", "indice": 0}
    f = _fascicolo(monkeypatch, [ricevuta, dict(ricevuta)])
    assert f["quietanza"]["presente"] is True
    assert f["verbale"]["presente"] is False and f["verbale"]["documento"] is None


def test_verbale_e_quietanza_sono_file_diversi(monkeypatch):
    verbale = {"filename": "A25111856676 verbale.pdf", "tipo": "pdf", "indice": 0}
    ricevuta = {"filename": "RicevutaTelematica_302000600007523483.pdf", "tipo": "pdf", "indice": 1}
    f = _fascicolo(monkeypatch, [ricevuta, verbale])
    assert f["verbale"]["documento"]["filename"] == "A25111856676 verbale.pdf"
    assert f["quietanza"]["documento"]["filename"].startswith("RicevutaTelematica")


def test_i_documenti_drive_vanno_nella_casella_del_loro_tipo(monkeypatch):
    drive = [{"drive_id": "1AbCdEfGhIjKlMnOpQrStUv", "tipo": "quietanza", "nome": "Ricevuta.pdf"},
             {"drive_id": "1ZyXwVuTsRqPoNmLkJiHgFe", "tipo": "avviso_pagopa", "nome": "Avviso.pdf"}]
    f = _fascicolo(monkeypatch, [], documenti_drive=drive)
    assert [d["drive_id"] for d in f["quietanza"]["documenti_drive"]] == ["1AbCdEfGhIjKlMnOpQrStUv"]
    assert f["quietanza"]["presente"] is True and f["verbale"]["presente"] is False
