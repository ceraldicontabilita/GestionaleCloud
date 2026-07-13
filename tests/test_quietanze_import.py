"""
Motore unico import quietanze F24 (app/services/quietanze_import.py):
dedup per impronta, salvataggio e matching automatico con gli F24.
Usato sia dall'upload manuale che dal canale Google Drive.
"""
import asyncio

from app.services import quietanze_import as qi


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
}


def _patch_parser(monkeypatch, parsed):
    import app.services.f24_parser as f24_parser
    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: parsed)


def test_import_e_matching_automatico(monkeypatch):
    """Quietanza con gli stessi tributi di un F24 da pagare → F24 pagato."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    # F24 del commercialista in attesa con gli stessi tributi
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-1", "status": "da_pagare", "riconciliato": False,
        "file_name": "F24_giugno.pdf",
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1000.0},
            {"codice_tributo": "1040", "periodo_riferimento": "05/2026", "importo_debito": 500.20},
        ],
        "totali": {"saldo_netto": 1500.20},
    }))

    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "quietanza.pdf", fonte="test"))

    assert esito["success"] and not esito["duplicate"]
    assert len(esito["f24_matchati"]) == 1  # tolleranza €0.50 sul singolo tributo
    f24 = db[qi.COLL_F24_COMMERCIALISTA].docs[0]
    assert f24["status"] == "pagato"
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


def test_drive_quietanze_helpers():
    from app.services import drive_quietanze_ingest as dq
    assert dq.is_quietanza_filename("quietanza_giugno.PDF")
    assert not dq.is_quietanza_filename("nota.txt")
    # In sandbox senza env Drive il canale risulta non configurato ma il
    # flag di default è ACCESO (scelta utente 10/07)
    from app.config import settings
    assert settings.ENABLE_DRIVE_QUIETANZE_SYNC is True
