"""Regola versamenti: la cassa nasce dall'azione manuale dell'utente.

L'estratto conto può riconoscere la causale "VERS. CONTANTI" e confermare
l'accredito in banca, ma non deve mai inventare l'uscita di cassa.
"""
import asyncio

from app.routers.bank import estratto_conto as mod


def test_is_versamento_contanti_riconosce_abbreviazione_reale():
    # Causale reale, verificata sull'export Banco BPM su Drive.
    assert mod.is_versamento_contanti("VERS. CONTANTI - VVVVV") is True


def test_is_versamento_contanti_riconosce_parola_intera():
    assert mod.is_versamento_contanti("VERSAMENTO CONTANTI SPORTELLO") is True


def test_is_versamento_contanti_non_falsi_positivi():
    casi_falsi = [
        "PRELIEVO ASSEGNO - DM 00000 CRA: 00000000000000 NUM: 0000000000",
        "ADD. PAGAM. DIVERSI",
        "VOSTRA DISPOSIZIONE - VS.DISP. RIF. XX0X00000000 FAVORE Fornitore Test",
        "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 02/04/26",
        "",
        None,
    ]
    for desc in casi_falsi:
        assert mod.is_versamento_contanti(desc) is False, desc


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        if isinstance(v, dict) and "$regex" in v:
            if not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                return False
            continue
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
            continue
        if isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
            continue
        if doc.get(k) != v:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_many(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                break

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


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

def test_ripara_versamenti_disattivato_fase0_non_scrive_nulla(monkeypatch):
    """Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punto 6): ripara_versamenti_cassa
    e' disattivato — deve rifiutare la richiesta con 409 e non toccare
    prima_nota_cassa/prima_nota_banca/estratto_conto_movimenti, qualunque sia
    il movimento presente (versamento riconosciuto o no)."""
    from fastapi import HTTPException

    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-vecchio", "data": "2026-03-30", "importo": 5000.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
        "riconciliato": False,
    }]

    try:
        _run(mod.ripara_versamenti_cassa(anno=2026))
        assert False, "doveva sollevare HTTPException 409"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["estratto_conto_movimenti"].docs[0]["riconciliato"] is False


def test_ripara_prelievo_disattivato_fase0_non_scrive_nulla(monkeypatch):
    """Stessa disattivazione anche per il ramo prelievo (doppia scrittura
    cassa/banca): nessuna scrittura, l'estratto conto resta non riconciliato."""
    from fastapi import HTTPException

    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-prel", "data": "2026-05-10", "importo": 500.0,
        "tipo": "uscita", "descrizione_originale": "PRELIEVO CONTANTI SPORTELLO",
    }]

    try:
        _run(mod.ripara_versamenti_cassa(anno=2026))
        assert False, "doveva sollevare HTTPException 409"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert "tipo_riconciliazione" not in db["estratto_conto_movimenti"].docs[0]


def test_prelievo_non_confuso_con_versamento():
    assert mod.is_prelievo_contanti("PRELIEVO CONTANTI SPORTELLO") is True
    assert mod.is_prelievo_contanti("PRELEV. BANCOMAT CARTA 123") is True
    assert mod.is_prelievo_contanti("VERS. CONTANTI - VVVVV") is False
    assert mod.is_prelievo_contanti("PRELIEVO ASSEGNO - DM 00000") is False
    assert mod.is_prelievo_contanti("") is False
