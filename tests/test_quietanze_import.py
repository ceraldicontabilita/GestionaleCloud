"""
Motore unico import quietanze F24 (app/services/quietanze_import.py):
dedup per impronta, salvataggio e matching automatico con gli F24.
Usato sia dall'upload manuale che dal canale Google Drive.
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.sheets_document_store import MemorySheetsClient

from app.services import quietanze_import as qi
from tests.document_preview_helpers import confirmed_preview_headers


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs[:n]


class _FakeCollection:
    def __init__(self):
        self.docs = []
        self.updates = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                return d
        return None

    def find(self, query, *a, **k):
        out = []
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                out.append(d)
        return _FakeCursor(out)

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        self.updates.append((query, update))
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                for k2, v in update.get("$set", {}).items():
                    d[k2] = v
                for k2, v in update.get("$push", {}).items():
                    d.setdefault(k2, []).append(v)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


PARSED_OK = {
    "dati_generali": {
        "protocollo_telematico": "24123456789012345678",
        "saldo_delega": 1500.0,
        "data_pagamento": "2026-06-16",
        "codice_fiscale": "01879020517",
    },
    "sezione_erario": [
        {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1000.0},
        {"codice_tributo": "1040", "periodo_riferimento": "05/2026", "importo_debito": 500.0},
    ],
    "sezione_inps": [],
    "sezione_regioni": [],
    "sezione_tributi_locali": [],
    "sezione_inail": [],
    "totali": {"saldo_netto": 1500.0},
    "validazione": {
        "saldo_quadrato": True,
        "differenza_saldo": 0.0,
        "parser_version": "test-v1",
    },
}


def _patch_parser(monkeypatch, parsed):
    import app.services.f24_parser as f24_parser
    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: parsed)


def test_import_e_matching_automatico(monkeypatch):
    """La quietanza collega il modello ma non sostituisce la prova bancaria."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    # F24 del commercialista in attesa con gli stessi tributi
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-1", "status": "da_pagare", "riconciliato": False,
        "file_name": "F24_giugno.pdf",
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1000.0},
            {"codice_tributo": "1040", "periodo_riferimento": "05/2026", "importo_debito": 500.0},
        ],
        "totali": {"saldo_netto": 1500.0},
    }))

    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "quietanza.pdf", fonte="test"))

    assert esito["success"] and not esito["duplicate"]
    assert len(esito["f24_matchati"]) == 1  # tolleranza €0.50 sul singolo tributo
    f24 = db[qi.COLL_F24_COMMERCIALISTA].docs[0]
    assert f24["status"] == "da_pagare"
    assert f24["stato_pagamento"] == "DA_VERIFICARE_BANCA"
    assert f24["pagato"] is False
    assert f24["quietanza_id"] == esito["quietanza_id"]
    quietanza = db[qi.COLL_QUIETANZE].docs[0]
    assert quietanza["pdf_hash"]
    assert quietanza["f24_associati"] == ["f24-1"]


def test_dedup_per_impronta(monkeypatch):
    """Lo stesso PDF importato due volte non crea doppioni."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    primo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "q.pdf"))
    secondo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "q.pdf"))
    assert primo["duplicate"] is False
    assert secondo["duplicate"] is True
    assert secondo["quietanza_id"] == primo["quietanza_id"]
    assert len(db[qi.COLL_QUIETANZE].docs) == 1


def test_senza_match_crea_alert(monkeypatch):
    """Nessun F24 corrispondente → warning + alert quietanza_senza_match."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-altro", "q2.pdf"))
    assert esito["success"]
    assert esito["f24_matchati"] == []
    assert esito.get("warning")
    alerts = db[qi.COLL_F24_ALERTS].docs
    assert len(alerts) == 1 and alerts[0]["tipo"] == "quietanza_senza_match"


def test_quietanza_senza_f24_stato_canonico_e_nessuna_ricostruzione(monkeypatch):
    """§9.3 (regola cardine): quietanza senza F24 → stato canonico
    QUIETANZA_PRESENTE_F24_MANCANTE, alert bloccante, calcolo sospeso e NESSUN
    F24 ricostruito automaticamente."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-altro", "q3.pdf"))

    assert esito.get("stato_quietanza") == "QUIETANZA_PRESENTE_F24_MANCANTE"
    quietanza = db[qi.COLL_QUIETANZE].docs[0]
    assert quietanza["stato_quietanza"] == "QUIETANZA_PRESENTE_F24_MANCANTE"
    assert quietanza["calcolo_fiscale_sospeso"] is True
    # alert bloccante
    alerts = db[qi.COLL_F24_ALERTS].docs
    assert alerts and alerts[0].get("bloccante") is True
    # NESSUN F24 ricostruito in automatico (regola cardine CLAUDE.md)
    assert db["f24_unificato"].docs == []
    assert db["f24_models"].docs == []


def test_parsing_fallito_non_salva(monkeypatch):
    _patch_parser(monkeypatch, {"error": "PDF illeggibile"})
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"non-pdf", "rotto.pdf"))
    assert esito["success"] is False
    assert db[qi.COLL_QUIETANZE].docs == []


def test_saldo_non_quadrato_non_salva(monkeypatch):
    parsed = {**PARSED_OK, "validazione": {
        "saldo_quadrato": False,
        "differenza_saldo": 12.34,
        "parser_version": "test-v1",
    }}
    _patch_parser(monkeypatch, parsed)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-non-quadrato", "non-quadrato.pdf"))
    assert esito["success"] is False
    assert esito["stato_quietanza"] == "PARSING_DA_VERIFICARE"
    assert db[qi.COLL_QUIETANZE].docs == []


def test_quietanza_reale_1040_8948_marca_ravvedimento(monkeypatch):
    parsed = {
        **PARSED_OK,
        "dati_generali": {
            **PARSED_OK["dati_generali"],
            "saldo_delega": 286.0,
            "data_pagamento": "2026-07-21",
        },
        "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0},
            {"codice_tributo": "8948", "periodo_riferimento": "06/2026", "importo_debito": 2.0},
        ],
        "totali": {"totale_debito": 286.0, "totale_credito": 0.0, "saldo_netto": 286.0},
    }
    _patch_parser(monkeypatch, parsed)
    db = _FakeDb()
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-1040-06-2026",
        "status": "da_pagare",
        "riconciliato": False,
        "sezione_erario": [{
            "codice_tributo": "1040",
            "periodo_riferimento": "06/2026",
            "importo_debito": 284.0,
        }],
        "totali": {"saldo_netto": 284.0},
    }))

    esito = asyncio.run(qi.importa_quietanza_bytes(
        db, b"%PDF-caso-reale-anonimizzato", "quietanza_2026-07-21.pdf", fonte="test"
    ))

    assert esito["f24_matchati"][0]["ravveduto"] is True
    f24 = db[qi.COLL_F24_COMMERCIALISTA].docs[0]
    assert f24["codici_ravvedimento"] == ["8948"]
    assert f24["importo_ravvedimento"] == 2.0


def test_drive_quietanze_helpers():
    from app.services import drive_quietanze_ingest as dq
    assert dq.is_quietanza_filename("quietanza_giugno.PDF")
    assert not dq.is_quietanza_filename("nota.txt")
    # In sandbox senza env Drive il canale risulta non configurato ma il
    # flag di default è ACCESO (scelta utente 10/07)
    from app.config import settings
    assert settings.ENABLE_DRIVE_QUIETANZE_SYNC is True


def test_upload_auto_endpoint_usa_il_servizio_canonico_quietanze(monkeypatch):
    """Integrazione HTTP reale: multipart -> router -> servizio -> DB fake."""
    from app.routers import documenti
    from app.utils import upload_validation

    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-upload-auto",
        "status": "da_pagare",
        "riconciliato": False,
        "file_name": "F24 giugno 2026.pdf",
        "sezione_erario": PARSED_OK["sezione_erario"],
        "totali": PARSED_OK["totali"],
    }))
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(documenti, "detect_document_type", lambda *_: "quietanza_f24")
    monkeypatch.setattr(upload_validation, "verifica_pdf_reale", lambda *_: None)

    test_app = FastAPI()
    test_app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(test_app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("quietanza_1040.pdf", b"%PDF-1.4 fixture anonima", "application/pdf")},
            headers=confirmed_preview_headers(b"%PDF-1.4 fixture anonima", "quietanza_f24"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["workflow"] == "F24_CANONICO"
    assert payload["imported"] == 1
    assert payload["data"]["f24_matchati"][0]["f24_id"] == "f24-upload-auto"
    assert len(db[qi.COLL_QUIETANZE].docs) == 1
    assert db[qi.COLL_F24_COMMERCIALISTA].docs[0]["quietanza_id"] == payload["data"]["quietanza_id"]


def test_upload_auto_endpoint_importa_modello_nella_sola_collezione_canonica(monkeypatch):
    from app.routers import documenti
    from app.utils import upload_validation
    import app.services.parser_f24 as parser

    parsed = {
        "dati_generali": {"codice_fiscale": "CF-ANONIMO", "data_versamento": "2026-07-16"},
        "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0},
            {"codice_tributo": "1704", "periodo_riferimento": "06/2026", "importo_credito": 20.0},
        ],
        "totali": {"totale_debito": 284.0, "totale_credito": 20.0, "saldo_netto": 264.0},
        "validazione": {"saldo_quadrato": True, "parser_version": "test-v1"},
    }
    db = _FakeDb()
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(documenti, "detect_document_type", lambda *_: "f24")
    monkeypatch.setattr(upload_validation, "verifica_pdf_reale", lambda *_: None)
    monkeypatch.setattr(parser, "parse_f24_commercialista", lambda pdf_content: parsed)

    test_app = FastAPI()
    test_app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(test_app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("modello_f24.pdf", b"%PDF-1.4 fixture anonima", "application/pdf")},
            headers=confirmed_preview_headers(b"%PDF-1.4 fixture anonima", "f24"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["workflow"] == "F24_CANONICO"
    assert payload["data"]["righe_tributo"] == 2
    assert payload["data"]["righe_credito"] == 1
    assert len(db["f24_unificato"].docs) == 1
    assert db["f24_pagamenti"].docs == []
    assert db["tributi_pagati"].docs == []
    assert db["distinte_f24"].docs == []


def test_upload_quietanza_aggiorna_subito_ritenuta_reale_1040(monkeypatch):
    parsed = {
        "dati_generali": {
            "protocollo_telematico": "PROTO-1040-062026",
            "saldo_delega": 286.0,
            "data_pagamento": "2026-07-21",
            "codice_fiscale": "CF-ANONIMO",
        },
        "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0},
            {"codice_tributo": "8948", "periodo_riferimento": "06/2026", "importo_debito": 2.0},
        ],
        "sezione_inps": [], "sezione_regioni": [],
        "sezione_tributi_locali": [], "sezione_inail": [],
        "totali": {"saldo_netto": 286.0},
        "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0},
    }
    _patch_parser(monkeypatch, parsed)
    db = MemorySheetsClient()["quietanza-ritenuta-real-case"]
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "F24-1040-06-2026", "status": "da_pagare", "riconciliato": False,
        "codice_fiscale": "CF-ANONIMO",
        "sezione_erario": [{
            "codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0,
        }],
        "totali": {"saldo_netto": 284.0},
    }))
    asyncio.run(db["ritenute_acconto"].insert_one({
        "id": "rit-1040-06-2026", "importo": 284.0,
        "periodo_ritenuta": "2026-06", "scadenza": "2026-07-16",
        "data_fattura": "2026-06-30", "stato": "scaduta_da_versare",
    }))

    result = asyncio.run(qi.importa_quietanza_bytes(
        db, b"%PDF-real-case-anonimo", "quietanza_1040_2026-07-21.pdf",
        fonte="documenti_upload_auto",
    ))

    assert result["success"] is True
    assert result["ritenute_aggiornate"]["analizzate"] == 1
    ritenuta = asyncio.run(db["ritenute_acconto"].find_one({"id": "rit-1040-06-2026"}))
    assert ritenuta["f24_id"] == "F24-1040-06-2026"
    assert ritenuta["data_pagamento"] == "2026-07-21"
    assert ritenuta["stato"] == "pagata_con_ravvedimento"
    assert ritenuta["stato_evidenza_pagamento"] == "QUIETANZA_PRESENTE_DA_VERIFICARE_BANCA"
    assert ritenuta["movimento_bancario_f24_id"] is None
