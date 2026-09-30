"""AV3-09: `upload-quietanza` — solo admin, importo Decimal al centesimo, idempotente."""

import asyncio
import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


PDF = base64.b64encode(b"%PDF-1.4 quietanza").decode("ascii")


def _client(monkeypatch, db, admin=True):
    from app.database import Database
    from app.routers import verbali_noleggio_api as api
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(api.router, prefix="/api/verbali-noleggio")
    if admin:
        app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app)


def _db(**verbale):
    db = ClientArchivioMemoria()["quietanza"]
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "111/V/2025", "targa": "AB123CD", "importo": 57.05,
        "stato": "aperto", "driver_id": "d1", "driver": "Mario", **verbale}))
    return db


def _corpo(**extra):
    return {"importo_pagato": "57,05", "data_pagamento": "23/01/2025", "pdf_base64": PDF, **extra}


def test_senza_sessione_admin_e_rifiutato(monkeypatch):
    db = _db()
    client = _client(monkeypatch, db, admin=False)
    risposta = client.post("/api/verbali-noleggio/v1/upload-quietanza", json=_corpo())
    assert risposta.status_code in (401, 403)
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "aperto"


def test_importo_e_data_obbligatori_e_validi(monkeypatch):
    db = _db()
    client = _client(monkeypatch, db)
    base = "/api/verbali-noleggio/v1/upload-quietanza"
    assert client.post(base, json={"data_pagamento": "23/01/2025"}).status_code == 400          # mai 0 d'ufficio
    assert client.post(base, json=_corpo(importo_pagato="abc")).status_code == 400
    assert client.post(base, json=_corpo(importo_pagato="57.055")).status_code == 400            # oltre il centesimo
    assert client.post(base, json=_corpo(importo_pagato="-1")).status_code == 400
    assert client.post(base, json=_corpo(data_pagamento="ieri")).status_code == 400
    assert client.post(base, json=_corpo(pdf_base64="non base64!")).status_code == 400
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "aperto"


def test_importo_diverso_dal_verbale_e_409_e_non_registra(monkeypatch):
    db = _db()
    client = _client(monkeypatch, db)
    risposta = client.post("/api/verbali-noleggio/v1/upload-quietanza", json=_corpo(importo_pagato="57,06"))
    assert risposta.status_code == 409
    assert risposta.json()["detail"]["code"] == "IMPORTO_DIVERSO_DAL_VERBALE"
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "aperto"
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 0


def test_quietanza_con_pdf_e_idempotente_nota_e_trattenuta_una_sola_volta(monkeypatch):
    db = _db()
    client = _client(monkeypatch, db)
    url = "/api/verbali-noleggio/v1/upload-quietanza"

    primo = client.post(url, json=_corpo())
    secondo = client.post(url, json=_corpo())

    assert primo.status_code == 200 and primo.json()["duplicato"] is False
    assert secondo.status_code == 200 and secondo.json()["duplicato"] is True
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["stato"] == "pagato" and verbale["pagato_documentalmente"] is True
    assert verbale["importo_pagato"] == "57.05" and verbale["data_pagamento"] == "2025-01-23"
    assert len(verbale["quietanza_hash"]) == 64
    assert _run(db["note_presenze_consulente"].count_documents({})) == 1
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 1


def test_senza_pdf_il_verbale_resta_in_attesa_della_quietanza(monkeypatch):
    db = _db()
    client = _client(monkeypatch, db)
    corpo = _corpo()
    corpo.pop("pdf_base64")

    risposta = client.post("/api/verbali-noleggio/v1/upload-quietanza", json=corpo)

    assert risposta.status_code == 200
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["stato"] == "pagato_attesa_quietanza" and verbale["pagato_documentalmente"] is False
    assert verbale["quietanza_ricevuta"] is False


def test_verbale_inesistente_e_404(monkeypatch):
    client = _client(monkeypatch, _db())
    assert client.post("/api/verbali-noleggio/nope/upload-quietanza", json=_corpo()).status_code == 404
