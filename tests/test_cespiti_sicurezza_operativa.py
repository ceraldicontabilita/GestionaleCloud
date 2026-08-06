"""Pagina 22 - invarianti operative del registro cespiti.

I test coprono i difetti trovati nell'audit reale: registrazione annuale
prematura, risposta dopo scritture con variabile inesistente, beni senza prova
dell'entrata in funzione, cancellazione fisica e falsa prima nota monetaria in
caso di dismissione.
"""
import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

from app.routers import cespiti as mod


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _matches(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches(doc, branch) for branch in expected):
                return False
            continue
        if isinstance(expected, dict):
            if "$ne" in expected and doc.get(key) == expected["$ne"]:
                return False
            if "$not" in expected and "$elemMatch" in expected["$not"]:
                rows = doc.get(key) or []
                wanted = expected["$not"]["$elemMatch"]
                if any(_matches(row, wanted) for row in rows):
                    return False
            continue
        if doc.get(key) != expected:
            return False
    return True


class _Result:
    def __init__(self, modified=0, upserted_id=None):
        self.modified_count = modified
        self.upserted_id = upserted_id


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.docs)


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, query=None, projection=None):
        return _Cursor([d for d in self.docs if _matches(d, query or {})])

    async def find_one(self, query=None, projection=None):
        return next((dict(d) for d in self.docs if _matches(d, query or {})), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _Result(modified=1)

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if not _matches(doc, query):
                continue
            for key, value in (update.get("$set") or {}).items():
                doc[key] = value
            for key, value in (update.get("$push") or {}).items():
                doc.setdefault(key, []).append(value)
            return _Result(modified=1)
        if upsert:
            doc = dict(update.get("$setOnInsert") or {})
            self.docs.append(doc)
            return _Result(modified=0, upserted_id=doc.get("id"))
        return _Result()

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if _matches(d, query or {}))


class _Db:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def _asset(**overrides):
    doc = {
        "id": "asset-1",
        "descrizione": "Forno",
        "categoria": "forni",
        "stato": "attivo",
        "data_acquisto": "2025-01-10",
        "anno_acquisto": 2025,
        "data_entrata_funzione": "2025-01-15",
        "anno_entrata_funzione": 2025,
        "valore_acquisto": 1000.0,
        "fondo_ammortamento": 0.0,
        "valore_residuo": 1000.0,
        "coefficiente_ammortamento": 20,
        "ammortamento_completato": False,
        "piano_ammortamento": [],
    }
    doc.update(overrides)
    return doc


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))


def test_registrazione_richiede_conferma_esplicita(monkeypatch):
    _patch_db(monkeypatch, _Db())
    with pytest.raises(HTTPException) as exc:
        _run(mod.registra_ammortamenti_anno(2025, conferma=False))
    assert exc.value.status_code == 400


def test_registrazione_corrente_bloccata_prima_di_fine_esercizio(monkeypatch):
    db = _Db({"cespiti": _Collection([_asset(anno_acquisto=2026, data_entrata_funzione="2026-01-15")])})
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(mod, "_today", lambda: date(2026, 8, 6))

    with pytest.raises(HTTPException) as exc:
        _run(mod.registra_ammortamenti_anno(2026, conferma=True))

    assert exc.value.status_code == 409
    assert db["movimenti_contabili"].docs == []
    assert db["cespiti"].docs[0]["piano_ammortamento"] == []


def test_registrazione_blocca_entrata_funzione_non_documentata(monkeypatch):
    db = _Db({"cespiti": _Collection([_asset(data_entrata_funzione=None)])})
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(mod, "_today", lambda: date(2027, 1, 10))

    with pytest.raises(HTTPException) as exc:
        _run(mod.registra_ammortamenti_anno(2025, conferma=True))

    assert exc.value.status_code == 409
    assert "entrata in funzione" in exc.value.detail


def test_registrazione_restituisce_id_reale_e_scrive_una_sola_quota(monkeypatch):
    db = _Db({"cespiti": _Collection([_asset()])})
    _patch_db(monkeypatch, db)
    monkeypatch.setattr(mod, "_today", lambda: date(2027, 1, 10))

    async def fake_registra(db_arg, movimento, righe, chiave_naturale):
        doc = {**movimento, "id": "mov-amm-2025", "righe": righe}
        await db_arg["movimenti_contabili"].insert_one(doc)
        return doc

    import app.services.registrazione_contabile as rc
    monkeypatch.setattr(rc, "registra_scrittura_semplice", fake_registra)

    result = _run(mod.registra_ammortamenti_anno(2025, conferma=True))

    assert result["movimento_id"] == "mov-amm-2025"
    assert result["cespiti_ammortizzati"] == 1
    assert len(db["cespiti"].docs[0]["piano_ammortamento"]) == 1
    assert db["movimenti_contabili"].docs[0]["dettaglio"][0]["cespite_id"] == "asset-1"


def test_verifica_coerenza_e_pura_lettura(monkeypatch):
    db = _Db({
        "cespiti": _Collection([_asset(data_entrata_funzione=None)]),
        "movimenti_contabili": _Collection([]),
    })
    _patch_db(monkeypatch, db)

    before = list(db["cespiti"].docs)
    result = _run(mod.verifica_coerenza_ammortamenti(2026))

    assert result["stato"] == "da_verificare"
    assert result["entrata_funzione_da_verificare"] == 1
    assert result["scritture_eseguite"] == 0
    assert db["cespiti"].docs == before


def test_verifica_segnala_quota_con_coefficiente_oltre_massimo(monkeypatch):
    asset = _asset(
        categoria="mobili_arredi",
        coefficiente_ammortamento=12,
        data_entrata_funzione="2026-01-10",
        piano_ammortamento=[{"anno": 2026, "quota": 84.0}],
    )
    db = _Db({
        "cespiti": _Collection([asset]),
        "movimenti_contabili": _Collection([
            {"id": "mov-1", "tipo": "ammortamento", "anno": 2026, "importo": 84.0},
        ]),
    })
    _patch_db(monkeypatch, db)

    result = _run(mod.verifica_coerenza_ammortamenti(2026))

    assert result["stato"] == "critico"
    assert result["coefficienti_oltre_massimo_con_quote"] == 1
    assert "quote_registrate_con_coefficiente_oltre_massimo" in result["critiche"]


def test_verifica_legge_anche_quota_anno_legacy(monkeypatch):
    asset = _asset(piano_ammortamento=[{"anno": 2026, "quota_anno": 120.0}])
    db = _Db({
        "cespiti": _Collection([asset]),
        "movimenti_contabili": _Collection([
            {"id": "mov-legacy", "tipo": "ammortamento", "anno": 2026, "importo": 120.0},
        ]),
    })
    _patch_db(monkeypatch, db)

    result = _run(mod.verifica_coerenza_ammortamenti(2026))

    assert result["totale_quote_registro"] == 120.0
    assert result["differenza"] == 0


def test_eliminazione_archivia_senza_cancellare(monkeypatch):
    db = _Db({"cespiti": _Collection([_asset()])})
    _patch_db(monkeypatch, db)

    result = _run(mod.elimina_cespite("asset-1"))

    assert result["success"] is True
    assert len(db["cespiti"].docs) == 1
    assert db["cespiti"].docs[0]["entity_status"] == "deleted"
    assert db["cespiti"].docs[0]["stato"] == "archiviato"


def test_dismissione_non_inventa_movimento_banca_o_cassa(monkeypatch):
    db = _Db({"cespiti": _Collection([_asset(valore_residuo=600.0)])})
    _patch_db(monkeypatch, db)

    result = _run(mod.dismetti_cespite(mod.DismissioneInput(
        cespite_id="asset-1",
        data_dismissione="2026-02-01",
        tipo="vendita",
        prezzo_vendita=800.0,
    )))

    assert result["dettaglio"]["plusminusvalenza"] == 200.0
    assert db["movimenti_contabili"].docs[0]["segno"] == "avere"
    assert db["prima_nota_banca"].docs == []
    assert db["prima_nota_cassa"].docs == []

    retry = _run(mod.dismetti_cespite(mod.DismissioneInput(
        cespite_id="asset-1",
        data_dismissione="2026-02-01",
        tipo="vendita",
        prezzo_vendita=800.0,
    )))
    assert retry["gia_registrato"] is True
    assert retry["movimento_id"] == result["movimento_id"]
    assert len(db["movimenti_contabili"].docs) == 1
