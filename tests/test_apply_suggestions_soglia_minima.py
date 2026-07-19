"""ERP-001 (19/07/2026): hardening di apply_suggestions.

1. Il chiamante non può più azzerare la soglia di confidenza inviando
   soglia_confidenza=0 (o qualunque valore sotto SOGLIA_CONFIDENZA_MINIMA_
   ASSOLUTA): può solo chiedere una soglia più alta (più prudente).
2. suggestion_ids, se non vuoto, limita realmente l'applicazione ai soli
   suggerimenti scelti (prima veniva letto ma mai usato).
3. Ogni chiamata genera una voce di audit, ma un fallimento dell'audit non
   deve mai bloccare la risposta già calcolata (best-effort).

Nota: questi test chiamano la funzione Python direttamente (bypassando
FastAPI), quindi il parametro admin_user — normalmente risolto dalla
dependency get_current_admin_user tramite JWT — va passato a mano."""
import asyncio

from app.database import Database
from app.routers import learning_universal as router_mod

_ADMIN = {"user_id": "u1", "email": "admin-test@example.com", "role": "admin"}


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
    come nel codice reale di apply_suggestions). Nessun attributo
    'audit_log': verifica che l'assenza non faccia esplodere la funzione,
    perché log_evento cattura internamente ogni eccezione di scrittura."""

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
    }, admin_user=_ADMIN))

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

    result = asyncio.run(router_mod.apply_suggestions(
        {"module": "movimenti"}, admin_user=_ADMIN
    ))

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
    }, admin_user=_ADMIN))

    assert result["soglia_confidenza"] == 0.95
    assert result["saltate_bassa_confidenza"] == 2
    assert result["applied"] == 0
    assert len(db.movimenti_banca.calls) == 0


def test_suggestion_ids_limita_realmente_applicazione(monkeypatch):
    """suggestion_ids=['CatA'] deve escludere CatB anche se sopra soglia,
    e l'esclusione va contata separatamente da quella per bassa confidenza."""
    db = _FakeDb({
        "modules": {
            "movimenti": {
                "rules": [
                    {"category": "CatA", "keywords": ["alfa"], "confidence": 0.9},
                    {"category": "CatB", "keywords": ["beta"], "confidence": 0.95},
                ]
            }
        }
    })
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({
        "module": "movimenti",
        "suggestion_ids": ["CatA"],
    }, admin_user=_ADMIN))

    assert result["applied"] == 1
    assert result["categorie_applicate"] == ["CatA"]
    assert result["saltate_non_selezionate"] == 1  # CatB, pur sopra soglia
    assert result["saltate_bassa_confidenza"] == 0
    assert len(db.movimenti_banca.calls) == 1


def test_soglia_nan_dal_chiamante_non_azzera_il_filtro(monkeypatch):
    """Review Codex su PR #67: il body JSON può contenere il token NaN
    (valido per json.loads di Python). Senza il fix, max(nan, 0.7) == nan
    e OGNI confronto "< nan" è falso: la soglia minima verrebbe aggirata
    silenziosamente, applicando tutte le regole a prescindere dalla
    confidenza — esattamente come con soglia_confidenza=0."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({
        "module": "movimenti",
        "soglia_confidenza": float("nan"),
    }, admin_user=_ADMIN))

    assert result["soglia_confidenza"] == router_mod.SOGLIA_CONFIDENZA_MINIMA_ASSOLUTA
    assert result["saltate_bassa_confidenza"] == 1  # CatB (0.3) esclusa comunque
    assert result["applied"] == 1  # solo CatA (0.9)


def test_soglia_infinito_negativo_non_azzera_il_filtro(monkeypatch):
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({
        "module": "movimenti",
        "soglia_confidenza": float("-inf"),
    }, admin_user=_ADMIN))

    assert result["soglia_confidenza"] == router_mod.SOGLIA_CONFIDENZA_MINIMA_ASSOLUTA
    assert result["applied"] == 1


def test_soglia_stringa_non_numerica_usa_il_minimo(monkeypatch):
    """Un valore non convertibile a float (es. iniezione di una stringa
    arbitraria) non deve far esplodere l'endpoint né bypassare la soglia."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions({
        "module": "movimenti",
        "soglia_confidenza": "non-un-numero",
    }, admin_user=_ADMIN))

    assert result["soglia_confidenza"] == router_mod.SOGLIA_CONFIDENZA_MINIMA_ASSOLUTA
    assert result["applied"] == 1


def test_suggestion_ids_vuoto_applica_tutte_le_regole_sopra_soglia(monkeypatch):
    """Comportamento invariato quando suggestion_ids non è specificato o è
    vuoto: nessuna regressione rispetto a prima di questa estensione."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    result = asyncio.run(router_mod.apply_suggestions(
        {"module": "movimenti", "suggestion_ids": []}, admin_user=_ADMIN
    ))

    assert result["applied"] == 1
    assert result["categorie_applicate"] == ["CatA"]
    assert result["saltate_non_selezionate"] == 0


def test_audit_fallito_non_blocca_la_risposta(monkeypatch):
    """Se la scrittura dell'audit fallisce (es. collection audit_log non
    disponibile), la risposta all'endpoint deve comunque arrivare intatta:
    l'audit è best-effort, non deve mai impedire l'operazione principale."""
    db = _FakeDb(_learning_doc())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    async def _log_evento_che_fallisce(*a, **k):
        raise RuntimeError("audit_log non raggiungibile (simulato)")

    monkeypatch.setattr(router_mod, "log_evento", _log_evento_che_fallisce)

    result = asyncio.run(router_mod.apply_suggestions(
        {"module": "movimenti"}, admin_user=_ADMIN
    ))

    assert result["applied"] == 1  # la scrittura sui movimenti è comunque avvenuta
