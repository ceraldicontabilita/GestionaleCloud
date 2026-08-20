import asyncio
import copy
import re
from mongomock_motor import AsyncMongoMockClient

from app.services import ai_document_parser
from app.services import verbali_document_import as mod


def _match(doc, query):
    if not query:
        return True
    if "$or" in query:
        return any(_match(doc, item) for item in query["$or"])
    for key, expected in query.items():
        if key.startswith("$"):
            continue
        actual = doc.get(key)
        if isinstance(expected, dict) and "$regex" in expected:
            flags = re.I if "i" in expected.get("$options", "") else 0
            if not re.search(expected["$regex"], str(actual or ""), flags):
                return False
        elif actual != expected:
            return False
    return True


class _Result:
    modified_count = 1


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, _n):
        return self

    async def to_list(self, n):
        return [copy.deepcopy(doc) for doc in self.docs[:n]]


class _Collection:
    def __init__(self, docs=None):
        self.docs = [copy.deepcopy(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        found = next((doc for doc in self.docs if _match(doc, query)), None)
        return copy.deepcopy(found) if found else None

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _match(doc, query)])

    async def update_one(self, query, update, upsert=False):
        found = next((doc for doc in self.docs if _match(doc, query)), None)
        inserted = False
        if found is None and upsert:
            found = {key: value for key, value in query.items() if not key.startswith("$")}
            self.docs.append(found)
            inserted = True
        if found is None:
            return _Result()
        found.update(copy.deepcopy(update.get("$set", {})))
        if inserted:
            for key, value in update.get("$setOnInsert", {}).items():
                found.setdefault(key, copy.deepcopy(value))
        for key, value in update.get("$addToSet", {}).items():
            values = found.setdefault(key, [])
            if value not in values:
                values.append(copy.deepcopy(value))
        return _Result()


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def _run(coro):
    return asyncio.run(coro)


def test_numero_verbale_estratto_dai_nomi_file_reali():
    assert mod._extract_numero(
        "VERBALE N. 24990121765 DEL 13 MAGGIO 2026 CERALDI GROUP SRL.PDF"
    ) == "24990121765"
    assert mod._extract_numero("VERBALE N. VV/24990121765.pdf") == "VV/24990121765"


def test_importo_testuale_5164_centesimi_prevale_su_ocr_5164_euro():
    amount, source, conflict = mod._select_document_amount(
        {"importo_ridotto": 5164}, {}, "Importo da pagare € 51,64"
    )
    assert amount == 51.64
    assert source == "pdf_testo_conflitto_ocr_x100"
    assert conflict is True


def test_pdf_scansione_usa_vision_e_crea_verbale_amministrativo(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-scan"}]
    monkeypatch.setattr(mod, "_extract_text", lambda _content: "")

    async def fake_ai(**_kwargs):
        return {
            "success": True,
            "tipo_documento": "verbale",
            "numero_verbale": "VV/24990121765",
            "data_verbale": "2026-05-13",
            "data_violazione": "2026-04-24",
            "importo_ridotto": 25.82,
            "ente_creditore": "Comune di Napoli",
            "partita_iva_responsabile": "04523831214",
            "targa": None,
        }

    monkeypatch.setattr(ai_document_parser, "parse_verbale_ai", fake_ai)
    result = _run(mod.process_verbale_document(
        db,
        document_id="doc-scan",
        content=b"%PDF-1.7 scanned",
        filename="VERBALE N. 24990121765.pdf",
    ))

    assert result["status"] == "linked"
    verbale = db["verbali_noleggio"].docs[0]
    assert verbale["numero_verbale"] == "VV/24990121765"
    assert verbale["importo"] == 25.82
    assert verbale["ambito"] == "amministrativo"
    assert verbale["targa"] is None
    assert db["documents_inbox"].docs[0]["estrazione_ai_usata"] is True


def test_documento_senza_numero_o_iuv_resta_da_revisionare(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-1", "status": "nuovo"}]
    monkeypatch.setattr(mod, "_extract_text", lambda _content: "Documento generico senza riferimenti")

    result = _run(mod.process_verbale_document(
        db, document_id="doc-1", content=b"pdf", filename="documento.pdf"
    ))

    assert result["status"] == "review"
    assert db["documents_inbox"].docs[0]["status"] == "da_revisionare"
    assert db["documents_inbox"].docs[0]["processed"] is False
    assert db["verbali_noleggio"].docs == []


def test_verbale_collega_veicolo_ma_non_deduce_driver_dalla_sola_targa(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-1"}]
    db["veicoli_noleggio"].docs = [{
        "id": "car-1", "targa": "AB123CD", "driver_id": "dip-1", "driver": "Mario Rossi"
    }]
    monkeypatch.setattr(
        mod,
        "_extract_text",
        lambda _content: "Verbale numero A25111540620 Targa AB123CD Da pagare euro 120,50",
    )

    first = _run(mod.process_verbale_document(
        db, document_id="doc-1", content=b"same", filename="verbale.pdf"
    ))
    second = _run(mod.process_verbale_document(
        db, document_id="doc-1", content=b"same", filename="verbale.pdf"
    ))

    assert first["verbale_id"] == second["verbale_id"]
    assert len(db["verbali_noleggio"].docs) == 1
    verbale = db["verbali_noleggio"].docs[0]
    assert verbale["numero_verbale"] == "A25111540620"
    assert verbale["targa"] == "AB123CD"
    assert verbale.get("driver_id") is None
    assert verbale.get("driver") is None
    assert verbale["document_ids"] == ["doc-1"]
    assert db["documents_inbox"].docs[0]["verbale_id"] == verbale["id"]


def test_driver_richiede_assegnazione_storica_compatibile_con_la_data():
    db = AsyncMongoMockClient()["verbale-driver-temporale"]
    _run(db["veicoli_noleggio"].insert_one({
        "id": "car-1", "targa": "AB123CD", "driver_id": "driver-corrente",
    }))
    _run(db["storico_assegnazioni_veicoli"].insert_one({
        "targa": "AB123CD", "driver_id": "driver-storico",
        "driver": "Mario Storico", "data_inizio": "2025-01-01",
        "data_fine": "2025-06-30",
    }))

    context = _run(mod._vehicle_context(db, "AB123CD", "2025-04-10"))

    assert context["veicolo_id"] == "car-1"
    assert context["driver_id"] == "driver-storico"
    assert context["driver_match_basis"] == "assegnazione_storica_alla_data"


def test_ricevuta_pagopa_non_si_associa_se_importo_non_coincide(monkeypatch):
    db = _Db()
    db["documents_inbox"].docs = [{"id": "doc-r"}]
    db["verbali_noleggio"].docs = [{
        "id": "verb-1", "numero_verbale": "A25111540620", "importo": 120.51
    }]
    monkeypatch.setattr(
        mod,
        "_extract_text",
        lambda _content: (
            "Ricevuta di pagamento Verbale numero A25111540620 "
            "Codice Avviso 012345678901234567 Totale 120,50 Data pagamento 05/08/2026"
        ),
    )

    result = _run(mod.process_verbale_document(
        db, document_id="doc-r", content=b"receipt", filename="ricevuta_pagopa.pdf"
    ))

    assert result["status"] == "review"
    assert result["verbale_id"] is None
    assert db["ricevute_pagopa"].docs[0]["stato"] == "non_associata"
    assert db["documents_inbox"].docs[0]["processed"] is False
