"""Richiesta utente 15/07/2026 (punto 3): le attrezzature individuate nelle
fatture XML devono confluire da sole nel registro cespiti, non solo con lo
scan manuale. Nuovo handler su fattura.created, stessa logica (keyword map,
soglia 200€) di POST /api/cespiti/scan-fatture."""
import asyncio

from app.handlers import cespiti as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_crea_cespite_da_riga_fattura_sopra_soglia_con_categoria(monkeypatch):
    db = _FakeDb()

    esito = _run(mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-1",
        "fornitore_ragione_sociale": "Forniture Cucina Srl",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Forno industriale 6 teglie", "prezzo_totale": 3500.0},
            {"descrizione": "Caffè in grani 1kg", "prezzo_totale": 45.0},  # escluso, non cespite
        ],
    }, db))

    assert len(esito["cespiti_creati"]) == 1
    cespite = db["cespiti"].docs[0]
    assert cespite["categoria"] == "forni"
    assert cespite["valore_acquisto"] == 3500.0
    assert cespite["fattura_id"] == "fatt-1"
    assert cespite["anno_acquisto"] == 2026


def test_non_duplica_se_gia_creato_dallo_scan_manuale(monkeypatch):
    db = _FakeDb()
    db["cespiti"].docs = [
        {"id": "c-esistente", "descrizione": "Forno industriale 6 teglie", "valore_acquisto": 3500.0},
    ]

    esito = _run(mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-2",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Forno industriale 6 teglie", "prezzo_totale": 3500.0},
        ],
    }, db))

    assert esito["skipped"] is True
    assert len(db["cespiti"].docs) == 1  # nessun secondo cespite


def test_riga_sotto_soglia_non_diventa_cespite(monkeypatch):
    db = _FakeDb()

    esito = _run(mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-3",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Forno da tavolo piccolo", "prezzo_totale": 150.0},  # sotto soglia 200€
        ],
    }, db))

    assert esito["skipped"] is True
    assert db["cespiti"].docs == []


def test_riga_senza_categoria_riconosciuta_ignorata(monkeypatch):
    db = _FakeDb()

    esito = _run(mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-4",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Consulenza fiscale mensile", "prezzo_totale": 500.0},
        ],
    }, db))

    assert esito["skipped"] is True
    assert db["cespiti"].docs == []


def test_nessuna_riga_fattura_skip(monkeypatch):
    db = _FakeDb()

    esito = _run(mod.handler_auto_cespite_da_fattura({"fattura_id": "fatt-5"}, db))

    assert esito["skipped"] is True
    assert esito["reason"] == "nessuna riga fattura"
