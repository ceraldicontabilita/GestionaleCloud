"""ERP-001 (19/07/2026): apply_suggestions non deve più permettere al
chiamante di azzerare la soglia di confidenza inviando soglia_confidenza=0
(o qualunque valore sotto SOGLIA_CONFIDENZA_MINIMA_ASSOLUTA). Il chiamante
può solo chiedere una soglia più alta (più prudente), mai più bassa."""
import asyncio

from app.database import Database
from app.routers import learning_universal as router_mod


class _FakeUpdateResult:
    def __init__(self, modified_count):
        self.modified_count = modified_count


class _FakeMovimentiColl:
    def __init__(self):
        self.calls = []

    async def update_many(self, query, update):
        self.calls.append((query, update))
        return _FakeUpdateResult(1)


class _FakeLearningResultsColl:
    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, query):
        return self._doc


class _FakeDb:
    """db.movimenti_banca / db.learning_results (accesso ad attributo,
    come nel codice reale di apply_suggestions)."""

    def __init__(self, learning_doc):
        self.learning_results = _FakeLearningResultsColl(learning_doc)
        self.movimenti_banca = _FakeMovimentiColl()


def _learning_doc():
    return {
        "modules": {
            "movimenti": {
                "rules": [
                    {"category": "CatA", "keywords": ["alfa"], "confidence": 0.9},
                    {"category": "CatB", "keywords": ["beta"], "confidence": 0.3},
                ]
            }
        }
    }


def test_soglia_zero_dal_chiamante_non_azzera_il_filtro(monkeypatch):
    """Prima di ERP-001: soglia_confidenza=0 applicava anche la regola CatB
    (confidence 0.3). Dopo ERP-001: la soglia minima assoluta (0.7) resta in
    vigore comunque, CatB viene saltata."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({
        "module": "movimenti",
        "soglia_confidenza": 0,
    }))

    assert result["soglia_confidenza"] == router_mod.SOGLIA_CONFIDENZA_MINIMA_ASSOLUTA
    assert result["saltate_bassa_confidenza"] == 1  # solo CatB (0.3 < 0.7)
    assert result["applied"] == 1  # solo l'update di CatA (0.9 >= 0.7)
    assert len(db.movimenti_banca.calls) == 1
    _, update = db.movimenti_banca.calls[0]
    assert update["$set"]["categoria"] == "CatA"


def test_default_senza_soglia_resta_070_nessuna_regressione(monkeypatch):
    """Comportamento invariato per chi non specifica soglia_confidenza."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({"module": "movimenti"}))

    assert result["soglia_confidenza"] == 0.7
    assert result["saltate_bassa_confidenza"] == 1
    assert result["applied"] == 1


def test_chiamante_puo_alzare_la_soglia_oltre_il_minimo(monkeypatch):
    """Il chiamante resta libero di essere PIÙ prudente del minimo: una
    soglia di 0.95 esclude anche CatA (confidence 0.9)."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({
        "module": "movimenti",
        "soglia_confidenza": 0.95,
    }))

    assert result["soglia_confidenza"] == 0.95
    assert result["saltate_bassa_confidenza"] == 2
    assert result["applied"] == 0
    assert len(db.movimenti_banca.calls) == 0
