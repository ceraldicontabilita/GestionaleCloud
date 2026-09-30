"""MINI-08: scheda e originale di una busta per la vista `/personale/cedolini/:id`.

Sola lettura: un importo assente resta `None` (la pagina scrive «Dato non
disponibile», mai zero), le versioni della stessa busta si vedono affiancate
con la decisione del motore unico, e `/versioni` non viene mangiato dalla
route `/{cedolino_id}`.
"""
import asyncio
import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.constants.stati_netto import NETTO_FONTE_CELLA, NETTO_VERIFICATO_DA_CEDOLINO
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

CF = "RSSMRA80A01H501U"
PDF = b"%PDF-1.4 busta di prova"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _busta(netto, **extra):
    base = {
        "codice_fiscale": CF, "nome_dipendente": "ROSSI MARIO", "anno": 2025, "mese": 6,
        "tipo_cedolino": "mensile", "netto": netto, "lordo": 2000.0, "totale_trattenute": None if netto is None else 2000.0 - netto,
        "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO, "netto_fonte": NETTO_FONTE_CELLA, "canale": "drive",
    }
    base.update(extra)
    return base


def _client(monkeypatch, righe):
    from app.database import Database
    from app.routers import cedolini_scheda, cedolini_versioni
    from app.utils.dependencies import get_current_admin_user

    db = ClientArchivioMemoria()["scheda-test"]
    for riga in righe:
        _run(db["cedolini"].insert_one(riga))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    # Stesso ordine del registro: `/versioni` prima di `/{cedolino_id}`.
    app.include_router(cedolini_versioni.router, prefix="/api/cedolini")
    app.include_router(cedolini_scheda.router, prefix="/api/cedolini")
    return app, get_current_admin_user


def test_scheda_con_due_versioni_mostra_decisione_e_canale(monkeypatch):
    app, admin = _client(monkeypatch, [
        {"id": "a", "filename": "Rossi giugno.pdf", "created_at": "2025-07-01", "stampa_di_controllo": True,
         "status": "sostituito", **_busta(1400.0)},
        {"id": "b", "filename": "Rossi giugno (definitiva).pdf", "created_at": "2025-07-02",
         "rettificato": True, "n_versioni_totali": 2, "storico_netto": [{"prima": 1400.0, "dopo": 1500.0}],
         # il marcatore che il runtime Supabase scrive per ogni campo pesante (regola 3 di CLAUDE.md)
         "_payload_stato": {"pdf_data": "pieno"},
         "pdf_data": base64.b64encode(PDF).decode(), **_busta(1500.0)},
    ])
    app.dependency_overrides[admin] = lambda: {"role": "admin"}
    with TestClient(app) as client:
        corpo = client.get("/api/cedolini/b").json()
        assert corpo["periodo"] == "Giugno 2025" and corpo["tipo"] == "mensile"
        assert corpo["netto"] == 1500.0 and corpo["netto_fonte"] == NETTO_FONTE_CELLA
        assert corpo["canale"] == "drive" and corpo["sostituito"] is False
        assert corpo["versione"]["rettificato"] is True and corpo["versione"]["n_versioni_totali"] == 2
        assert corpo["versione"]["storico_netto"][0]["prima"] == 1400.0
        # la sostituita non e' attiva: il gruppo mostra solo le righe vive, la scheda dice il suo stato
        assert client.get("/api/cedolini/a").json()["sostituito"] is True
        assert "pdf_data" not in corpo and corpo["pdf_url"] == "/api/cedolini/b/pdf"


def test_pdf_senza_marcatore_si_prova_per_id(monkeypatch):
    app, admin = _client(monkeypatch, [{"id": "m", "pdf_data": base64.b64encode(PDF).decode(), **_busta(1500.0)}])
    app.dependency_overrides[admin] = lambda: {"role": "admin"}
    with TestClient(app) as client:
        assert client.get("/api/cedolini/m").json()["pdf_url"] == "/api/cedolini/m/pdf"


def test_scheda_importi_assenti_restano_none_e_pdf_assente(monkeypatch):
    riga = _busta(None, id="z")
    riga.pop("lordo"); riga.pop("totale_trattenute")
    app, admin = _client(monkeypatch, [riga])
    app.dependency_overrides[admin] = lambda: {"role": "admin"}
    with TestClient(app) as client:
        corpo = client.get("/api/cedolini/z").json()
        assert corpo["netto"] is None and corpo["lordo"] is None and corpo["totale_trattenute"] is None
        assert corpo["pdf_disponibile"] is False and corpo["pdf_url"] is None
        assert client.get("/api/cedolini/z/pdf").status_code == 404
        assert client.get("/api/cedolini/non-esiste").status_code == 404


def test_pdf_originale_e_versioni_resta_raggiungibile(monkeypatch):
    app, admin = _client(monkeypatch, [
        {"id": "p", "filename": "busta.pdf", "pdf_data": base64.b64encode(PDF).decode(), **_busta(1500.0)},
    ])
    with TestClient(app) as client:
        assert client.get("/api/cedolini/p").status_code in (401, 403)
    app.dependency_overrides[admin] = lambda: {"role": "admin"}
    with TestClient(app) as client:
        res = client.get("/api/cedolini/p/pdf")
        assert res.status_code == 200 and res.content == PDF
        assert res.headers["content-type"] == "application/pdf"
        # `/versioni` e' un indirizzo fisso, non un id di busta
        rapporto = client.get("/api/cedolini/versioni")
        assert rapporto.status_code == 200 and "gruppi" in rapporto.json()
