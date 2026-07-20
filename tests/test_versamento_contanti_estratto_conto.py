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


def test_ripara_versamenti_non_inventa_uscita_cassa_mancante(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    # Il versamento appare in banca, ma l'utente non ha registrato l'uscita
    # di cassa: deve restare da verificare, senza scritture inventate.
    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-vecchio", "data": "2026-03-30", "importo": 5000.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
        "riconciliato": False,
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["movimenti_versamento_trovati"] == 1
    assert res["creati_cassa"] == 0
    assert res["creati_banca"] == 0
    assert res["gia_presenti_cassa"] == 0
    assert res["versamenti_senza_registrazione_cassa"] == 1
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["estratto_conto_movimenti"].docs[0]["riconciliato"] is False


def test_ripara_versamenti_senza_cassa_non_crea_neppure_prima_nota_banca(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-vers", "data": "2026-07-01", "importo": 7880.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["creati_cassa"] == 0
    assert res["creati_banca"] == 0
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert not db["estratto_conto_movimenti"].docs[0].get("riconciliato", False)


def test_ripara_versamenti_cassa_idempotente(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-1", "data": "2026-03-30", "importo": 5000.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
        "riconciliato": False,
    }]

    _run(mod.ripara_versamenti_cassa(anno=2026))
    res2 = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res2["creati_cassa"] == 0
    assert res2["creati_banca"] == 0
    assert res2["gia_presenti_cassa"] == 0
    assert res2["gia_presenti_banca"] == 0
    assert res2["versamenti_senza_registrazione_cassa"] == 1
    assert len(db["prima_nota_cassa"].docs) == 0
    assert len(db["prima_nota_banca"].docs) == 0


def test_ripara_versamenti_rispetta_registrazioni_manuali(monkeypatch):
    """L'utente aveva già registrato a mano alcune uscite di cassa con
    categoria "Versamento Banca" (source versamento_contanti): la
    riparazione NON deve duplicarle — riconosce pari data+importo anche
    con categoria diversa. Idem per l'entrata banca già creata dal sync
    generico all'import (source estratto_conto_auto)."""
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-2", "data": "2026-06-26", "importo": 4000.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
    }]
    db["prima_nota_cassa"].docs = [{
        "id": "man-1", "data": "2026-06-26", "tipo": "uscita", "importo": 4000.0,
        "categoria": "Versamento Banca", "source": "versamento_contanti",
    }]
    db["prima_nota_banca"].docs = [{
        "id": "auto-1", "data": "2026-06-26", "tipo": "entrata", "importo": 4000.0,
        "categoria": "Ricavi - Deposito contanti", "source": "estratto_conto_auto",
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["creati_cassa"] == 0
    assert res["creati_banca"] == 0
    assert res["gia_presenti_cassa"] == 1
    assert res["gia_presenti_banca"] == 1
    assert len(db["prima_nota_cassa"].docs) == 1
    assert len(db["prima_nota_banca"].docs) == 1


def test_ripara_prelievo_crea_doppia_scrittura(monkeypatch):
    """Regola utente 17/07/2026: il prelievo di contanti dall'estratto conto
    genera l'ENTRATA in prima nota cassa ("prelevamento banca") e l'USCITA
    in prima nota banca ("prelevamento verso cassa")."""
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-prel", "data": "2026-05-10", "importo": 500.0,
        "tipo": "uscita", "descrizione_originale": "PRELIEVO CONTANTI SPORTELLO",
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["movimenti_prelievo_trovati"] == 1
    cassa = db["prima_nota_cassa"].docs
    banca = db["prima_nota_banca"].docs
    assert len(cassa) == 1 and cassa[0]["tipo"] == "entrata"
    assert cassa[0]["categoria"] == "Prelevamento Banca"
    assert cassa[0]["descrizione"].startswith("Prelevamento da banca")
    assert len(banca) == 1 and banca[0]["tipo"] == "uscita"
    assert banca[0]["categoria"] == "Prelevamento Banca"
    assert banca[0]["descrizione"].startswith("Prelevamento verso cassa")
    assert db["estratto_conto_movimenti"].docs[0]["tipo_riconciliazione"] == "prelievo_contanti"

    # idempotente
    res2 = _run(mod.ripara_versamenti_cassa(anno=2026))
    assert res2["creati_cassa"] == 0 and res2["creati_banca"] == 0
    assert len(db["prima_nota_cassa"].docs) == 1
    assert len(db["prima_nota_banca"].docs) == 1


def test_prelievo_non_confuso_con_versamento():
    assert mod.is_prelievo_contanti("PRELIEVO CONTANTI SPORTELLO") is True
    assert mod.is_prelievo_contanti("PRELEV. BANCOMAT CARTA 123") is True
    assert mod.is_prelievo_contanti("VERS. CONTANTI - VVVVV") is False
    assert mod.is_prelievo_contanti("PRELIEVO ASSEGNO - DM 00000") is False
    assert mod.is_prelievo_contanti("") is False


def test_riga_legacy_esclusa_non_blocca_la_gamba_banca(monkeypatch):
    """Bug 17/07/2026: la copia legacy del versamento con source escluso
    dai saldi (estratto_conto_sync) veniva contata come "gia presente" e
    la vera entrata banca non veniva mai creata — l'utente vedeva l'uscita
    in cassa senza l'entrata in banca (o viceversa)."""
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-3", "data": "2026-01-14", "importo": 8350.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
    }]
    db["prima_nota_cassa"].docs = [{
        "id": "man-2", "data": "2026-01-14", "tipo": "uscita", "importo": 8350.0,
        "categoria": "Versamento Banca", "source": "versamento_contanti",
    }]
    # copia legacy INVISIBILE nei saldi: non deve contare come presenza
    db["prima_nota_banca"].docs = [{
        "id": "legacy-1", "data": "2026-01-14", "tipo": "entrata", "importo": 8350.0,
        "categoria": "Ricavi - Deposito contanti", "source": "estratto_conto_sync",
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["gia_presenti_cassa"] == 1      # la manuale in cassa vale
    assert res["creati_banca"] == 1            # la gamba banca ora nasce
    attive = [b for b in db["prima_nota_banca"].docs if b.get("source") != "estratto_conto_sync"]
    assert len(attive) == 1 and attive[0]["categoria"] == "Versamento Banca"
