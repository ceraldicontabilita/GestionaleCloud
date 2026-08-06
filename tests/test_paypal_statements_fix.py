"""Copertura per i 2 fix isolati dell'operazione 14 (piano residuo,
audit 14/07/2026): il mapping fornitore PayPal leggeva da una collection
mai scritta (paypal_mapping_fornitori) e il KPI dashboard ignorava il
flag di riconciliazione scritto dal percorso API (riconciliato_con_estratto_banca)."""
import asyncio

import pytest

from app.routers import paypal_statements as mod


def _matches(doc, query):
    if not query:
        return True
    if "$and" in query:
        return all(_matches(doc, q) for q in query["$and"])
    if "$or" in query:
        return any(_matches(doc, q) for q in query["$or"])
    return all(doc.get(k) == v for k, v in query.items())


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return {k2: v for k2, v in d.items() if k2 != "_id"}
        return None

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if _matches(d, query))

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        return _FakeCursor([])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def skip(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)

    def __aiter__(self):
        return _aiter(self._docs)


async def _aiter(items):
    for i in items:
        yield i


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))


def test_dettaglio_transazione_legge_mapping_da_fornitori_non_da_collection_morta(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [{
        "transaction_id": "TX1", "paypal_account_id": "ACC-1",
        "importo": 100.0, "nome_controparte": "Fornitore Test",
    }]
    db["fornitori"].docs = [{
        "id": "f1", "paypal_account_id": "ACC-1",
        "nome": "Fornitore Test Srl", "piva": "IT12345678901",
    }]
    # La collection legacy morta esiste ma NON deve essere quella letta.
    db["paypal_mapping_fornitori"].docs = [{
        "paypal_account_id": "ACC-1", "fornitore_piva": "PIVA-SBAGLIATA",
    }]
    _patch_db(monkeypatch, db)

    res = _run(mod.dettaglio_transazione_paypal("TX1"))

    assert res["mapping_fornitore"] is not None
    assert res["mapping_fornitore"]["fornitore_piva"] == "IT12345678901"
    assert res["mapping_fornitore"]["fornitore_nome"] == "Fornitore Test Srl"


def test_dettaglio_transazione_nessun_mapping_se_fornitore_non_agganciato(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [{"transaction_id": "TX2", "paypal_account_id": "ACC-2"}]
    _patch_db(monkeypatch, db)

    res = _run(mod.dettaglio_transazione_paypal("TX2"))

    assert res["mapping_fornitore"] is None


def test_dashboard_conta_riconciliati_sia_da_statement_che_da_api(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [
        {"id": "1", "lordo": 10.0, "tipo": "pagamento_web", "riconciliato_banca": True},
        {"id": "2", "lordo": 20.0, "tipo": "pagamento_web", "riconciliato_con_estratto_banca": True},
        {"id": "3", "lordo": 30.0, "tipo": "pagamento_web"},
    ]
    _patch_db(monkeypatch, db)

    res = _run(mod.paypal_dashboard(anno=None))

    assert res["riconciliati_banca"] == 2


def test_fonti_paypal_mostrano_periodo_api_senza_inventare_un_documento(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [
        {
            "transaction_id": "PAY-1", "data": "2026-07-12",
            "lordo": -20.99, "currency": "EUR", "tipo": "pagamento_web",
            "source": "paypal_api",
        },
        {
            "transaction_id": "PAY-2", "data": "2026-07-20",
            "lordo": -42.62, "currency": "EUR", "tipo": "pagamento_web",
            "source": "paypal_api",
        },
    ]
    _patch_db(monkeypatch, db)

    res = _run(mod.get_paypal_statements(anno=None, limit=100))

    assert res["statements"] == []
    assert res["totale"] == 0
    assert res["totale_periodi_api"] == 1
    assert res["fonti"] == [{
        "id": "paypal-api-2026-07",
        "source_type": "api",
        "tipo_documento": "API",
        "periodo_inizio": "2026-07-01",
        "periodo_fine": "2026-07-31",
        "totale_transazioni": 2,
        "totale_pagamenti": 2,
        "riepilogo": {
            "pagamenti_inviati": 63.61,
            "depositi_accrediti": None,
            "saldo_finale": None,
        },
        "file_name": None,
        "source": "paypal_api",
        "documento_presente": False,
    }]


def test_stato_fattura_non_legittima_un_vecchio_match_solo_importo():
    assert mod._stato_collegamento_fattura({}) == "non_associata"
    assert mod._stato_collegamento_fattura({
        "fattura_associata": {
            "match": "solo_importo",
            "evidenze": ["importo"],
        }
    }) == "da_rivalidare"
    assert mod._stato_collegamento_fattura({
        "fattura_associata": {
            "match": "fornitore_numero_importo_esatti",
            "evidenze": ["numero_fattura", "importo", "partita_iva_o_cf"],
        }
    }) == "associata_validata"


def test_dashboard_non_somma_due_volte_conversione_valuta(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [
        {"transaction_id": "PAY-USD", "lordo": -120.0, "currency": "USD",
         "tipo": "pagamento_web", "nome_controparte": "Fornitore USA"},
        {"transaction_id": "CONV-EUR", "paypal_reference_id": "PAY-USD",
         "lordo": -100.0, "currency": "EUR", "tipo": "T0200"},
        {"transaction_id": "CONV-USD", "paypal_reference_id": "PAY-USD",
         "lordo": 120.0, "currency": "USD", "tipo": "T0200"},
    ]
    _patch_db(monkeypatch, db)

    res = _run(mod.paypal_dashboard(anno=None))

    assert res["totale_pagamenti"] == 1
    assert res["totale_speso"] == -100.0


def test_report_non_somma_due_volte_conversione_valuta(monkeypatch):
    db = _FakeDb()
    db["paypal_transactions"].docs = [
        {"transaction_id": "PAY-USD", "data": "2026-07-15", "lordo": -120.0,
         "currency": "USD", "tipo": "pagamento_web",
         "nome_controparte": "Fornitore USA"},
        {"transaction_id": "CONV-EUR", "paypal_reference_id": "PAY-USD",
         "data": "2026-07-15", "lordo": -100.0, "currency": "EUR", "tipo": "T0200"},
        {"transaction_id": "CONV-USD", "paypal_reference_id": "PAY-USD",
         "data": "2026-07-15", "lordo": 120.0, "currency": "USD", "tipo": "T0200"},
        {"transaction_id": "PAY-EUR", "data": "2026-07-16", "lordo": -30.0,
         "currency": "EUR", "tipo": "pagamento_web",
         "nome_controparte": "Fornitore Italia"},
    ]
    _patch_db(monkeypatch, db)

    res = _run(mod.paypal_report(anno=None))

    assert res["totale_transazioni"] == 2
    assert res["totale_speso"] == -130.0
    assert {row["nome"] for row in res["per_fornitore"]} == {
        "Fornitore USA", "Fornitore Italia",
    }


def test_match_banca_paypal_richiede_importo_segno_e_data_non_solo_importo():
    tx = {"transaction_id": "PAY-12345678", "data": "2026-07-15", "lordo": -42.62}
    corretto = {
        "data": "2026-07-17", "importo": -42.62,
        "descrizione": "ADDEBITO DIRETTO PAYPAL EUROPE",
    }
    lontano = {**corretto, "data": "2026-06-01"}
    segno_errato = {**corretto, "importo": 42.62}
    assert mod._score_match_banca(tx, corretto)["score"] >= 85
    assert mod._score_match_banca(tx, lontano) is None
    assert mod._score_match_banca(tx, segno_errato) is None


def test_riferimento_paypal_non_supera_un_importo_diverso():
    tx = {"transaction_id": "8ABCDEFGH12345", "data": "2026-07-15", "lordo": -42.62}
    mov = {
        "data": "2026-07-25", "importo": -40,
        "descrizione": "PAYPAL 8ABCDEFGH12345 regolazione",
    }
    assert mod._score_match_banca(tx, mov) is None


def test_match_banca_accetta_uscita_canonica_positiva_solo_al_centesimo():
    tx = {"transaction_id": "PAY-12345678", "data": "2026-07-15", "lordo": -42.62}
    movimento = {
        "data": "2026-07-17", "tipo": "uscita", "importo": 42.62,
        "descrizione": "ADDEBITO DIRETTO PAYPAL EUROPE",
    }
    assert mod._score_match_banca(tx, movimento)["score"] >= 85
    assert mod._score_match_banca(tx, {**movimento, "importo": 42.63}) is None


def test_match_banca_usa_la_gamba_eur_per_un_pagamento_in_valuta():
    tx = {
        "transaction_id": "PAY-USD",
        "data": "2026-07-15",
        "lordo": -120.0,
        "currency": "USD",
        "importo_report_eur": -100.0,
    }
    movimento = {
        "data": "2026-07-17", "importo": -100.0,
        "descrizione": "ADDEBITO PAYPAL EUROPE",
    }

    assert mod._score_match_banca(tx, movimento)["score"] >= 85
    assert mod._score_match_banca(tx, {**movimento, "importo": -120.0}) is None


def test_proposte_banca_accetta_solo_match_biunivoco():
    txs = [
        {"transaction_id": "PAY-A", "data": "2026-07-15", "lordo": -42.62},
        {"transaction_id": "PAY-B", "data": "2026-07-20", "lordo": -20.99},
    ]
    movimenti = [
        {"id": "EC-A", "data": "2026-07-17", "importo": -42.62,
         "descrizione": "ADDEBITO PAYPAL EUROPE"},
        {"id": "EC-B", "data": "2026-07-22", "importo": -20.99,
         "descrizione": "ADDEBITO PAYPAL EUROPE"},
    ]

    result = mod._proposte_riconciliazione_banca(txs, movimenti)

    assert result["ambigui"] == 0
    assert {(p["movimento_id"], p["transaction_id"]) for p in result["proposte"]} == {
        ("EC-A", "PAY-A"), ("EC-B", "PAY-B"),
    }


def test_proposte_banca_lascia_sospeso_un_pareggio():
    txs = [
        {"transaction_id": "PAY-A", "data": "2026-07-15", "lordo": -42.62},
        {"transaction_id": "PAY-B", "data": "2026-07-15", "lordo": -42.62},
    ]
    movimenti = [{
        "id": "EC-A", "data": "2026-07-17", "importo": -42.62,
        "descrizione": "ADDEBITO PAYPAL EUROPE",
    }]

    result = mod._proposte_riconciliazione_banca(txs, movimenti)

    assert result["proposte"] == []
    assert result["ambigui"] == 1


def test_proposte_banca_non_riusa_movimento_gia_riconciliato():
    txs = [{"transaction_id": "PAY-A", "data": "2026-07-15", "lordo": -42.62}]
    movimenti = [{
        "id": "EC-A", "data": "2026-07-17", "importo": -42.62,
        "descrizione": "ADDEBITO PAYPAL EUROPE", "riconciliato": True,
    }]

    result = mod._proposte_riconciliazione_banca(txs, movimenti)

    assert result["proposte"] == []
