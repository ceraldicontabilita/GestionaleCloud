"""Bug segnalato dall'utente 15/07/2026: le keyword suggerite dalla
Learning Machine per un fornitore erano frammenti senza senso ("unisex",
"preventivo", "taglia XXL" come parole isolate) invece di frasi complete
("gilet unisex", "amarena visciola"). Causa: suggerisci_keywords spezzava
ogni riga fattura in singole parole; ora segmenta per frasi di senso
compiuto, interrotte solo da stop-word/unità di misura/taglie."""
import asyncio

from app.routers.fornitori_learning import _estrai_frasi_da_descrizione, suggerisci_keywords
from app.routers import fornitori_learning as mod


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        return self

    async def to_list(self, n):
        return self._docs[:n]


class _FakeColl:
    def __init__(self, docs):
        self.docs = docs

    def find(self, *a, **k):
        return _FakeCursor(self.docs)


class _FakeDb:
    def __init__(self, invoices_docs):
        self._inv = _FakeColl(invoices_docs)

    def __getitem__(self, name):
        assert name == "invoices"
        return self._inv


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_estrae_frasi_complete_non_frammenti():
    assert _estrai_frasi_da_descrizione("GILET UNISEX TAGLIA XXL") == ["gilet unisex"]
    assert _estrai_frasi_da_descrizione("AMARENA VISCIOLA INTERA KG 5") == ["amarena visciola intera"]
    assert _estrai_frasi_da_descrizione("PREVENTIVO RIPARAZIONE MACCHINA CAFFE") == \
        ["riparazione macchina caffe"]


def test_scarta_righe_documento_logistica():
    frasi = _estrai_frasi_da_descrizione("DDT SPEDIZIONE MERCE VARIA")
    assert "ddt" not in frasi
    assert "spedizione" not in frasi
    assert "merce varia" in frasi


def test_suggerisci_keywords_propone_frasi_non_parole_isolate(monkeypatch):
    db_docs = [
        {"linee": [{"descrizione": "GILET UNISEX TAGLIA M"}], "descrizione": ""},
        {"linee": [{"descrizione": "GILET UNISEX TAGLIA L"}], "descrizione": ""},
        {"linee": [{"descrizione": "GILET UNISEX TAGLIA XXL"}], "descrizione": ""},
    ]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: _FakeDb(db_docs)))

    esito = _run(suggerisci_keywords("Fornitore Abbigliamento Srl"))

    assert "gilet unisex" in esito["keywords_suggerite"]
    # Nessun frammento isolato come "unisex" o "taglia" tra le proposte.
    assert "unisex" not in esito["keywords_suggerite"]
    assert "taglia" not in esito["keywords_suggerite"]
    assert esito["frequenze"]["gilet unisex"] == 3
