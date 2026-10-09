"""Bug trovato nell'audit funzionale del 15/07/2026: POST /api/ai-parser/
parse-fattura classificava il centro di costo con una ricerca ridotta
(solo lookup diretto su fornitori_keywords per nome fornitore), bypassando
il motore unico classifica_fattura_con_learning — niente fallback sulla
tabella statica CENTRI_COSTO, niente scoring sul contenuto delle righe,
niente gestione FORNITORE_MISTO. Una fattura di un fornitore non ancora
configurato restava sempre "non classificata" anche quando il contenuto
delle righe (es. "caffè", "farina") avrebbe permesso al motore unico di
classificarla correttamente dalla tabella statica."""
import asyncio

from app.routers import ai_parser as mod


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
        return None

    def find(self, query=None, *a, **k):
        class _Cur:
            async def to_list(self, n=None):
                return []
        return _Cur()


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


class _FakeUploadFile:
    def __init__(self, filename, content=b"finto pdf"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


def test_parse_fattura_classifica_dal_contenuto_righe_senza_fornitore_configurato(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    async def fake_parse_fattura_ai(file_bytes=None, file_path=None):
        return {
            "success": True,
            "fornitore": {"denominazione": "Torrefazione Sconosciuta Srl"},
            "righe": [{"descrizione": "Caffè in grani 1kg"}],
        }
    monkeypatch.setattr(mod, "parse_fattura_ai", fake_parse_fattura_ai)

    esito = _run(mod.parse_fattura_endpoint(
        file=_FakeUploadFile("fattura.pdf"), save_to_db=False, apply_learning=True,
    ))

    # Il fornitore non è configurato, ma il contenuto ("Caffè in grani")
    # deve comunque classificare tramite la tabella statica del motore
    # unico — prima restava sempre "non configurato".
    assert esito["centro_costo_suggerito"] == "1.1_CAFFE_BEVANDE_CALDE"
    assert esito["classificazione_fonte"] == "tabella_statica"
    assert esito["classificazione_automatica"] is True


def test_parse_fattura_senza_match_specifico_cade_su_altri_costi(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    async def fake_parse_fattura_ai(file_bytes=None, file_path=None):
        return {
            "success": True,
            "fornitore": {"denominazione": "Fornitore Totalmente Generico Srl"},
            "righe": [{"descrizione": "Prestazione non classificabile"}],
        }
    monkeypatch.setattr(mod, "parse_fattura_ai", fake_parse_fattura_ai)

    esito = _run(mod.parse_fattura_endpoint(
        file=_FakeUploadFile("fattura.pdf"), save_to_db=False, apply_learning=True,
    ))

    assert esito["classificazione_automatica"] is False
    assert "note_classificazione" in esito
