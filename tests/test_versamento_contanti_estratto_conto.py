"""Bug segnalato dall'utente 15/07/2026: i versamenti di contanti in banca
non generavano MAI l'uscita corrispondente in Prima Nota Cassa.

Causa verificata scaricando un export reale dell'estratto conto (Google
Drive, cartella "Estratti conto", 4287 movimenti): la causale usata dalla
banca (Banco BPM) è l'abbreviazione "VERS. CONTANTI" — mai la parola intera
"VERSAMENTO" che il vecchio controllo `is_versamento` cercava. Risultato: 96
righe reali, zero riconosciute. L'entrata in Prima Nota Banca veniva comunque
creata dal fallback generico, ma la cassa non registrava mai l'uscita del
contante — il saldo cassa risultava sistematicamente gonfiato.

`is_versamento_contanti` è ora l'unica implementazione (usata sia
dall'import sia dall'endpoint di riparazione dello storico
`ripara-versamenti-cassa`)."""
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


def test_ripara_versamenti_cassa_crea_uscita_mancante(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    # Riga storica già riconciliata (l'entrata banca generica l'aveva già
    # chiusa) ma senza mai aver creato l'uscita cassa, per via del bug.
    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-vecchio", "data": "2026-03-30", "importo": 5000.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
        "riconciliato": True,
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["movimenti_versamento_trovati"] == 1
    assert res["creati_cassa"] == 1
    assert res["gia_presenti_cassa"] == 0

    cassa = db["prima_nota_cassa"].docs
    assert len(cassa) == 1
    assert cassa[0]["tipo"] == "uscita"
    assert cassa[0]["categoria"] == "Versamento"
    assert cassa[0]["importo"] == 5000.0
    assert cassa[0]["estratto_conto_id"] == "EC-vecchio"


def test_ripara_versamenti_crea_anche_entrata_banca(monkeypatch):
    """Richiesta utente 17/07/2026: il versamento è una DOPPIA scrittura —
    uscita di cassa (il contante lascia il cassetto) ed entrata in banca
    (lo stesso denaro arriva sul conto)."""
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-vers", "data": "2026-07-01", "importo": 7880.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
    }]

    res = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res["creati_cassa"] == 1
    assert res["creati_banca"] == 1
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["tipo"] == "entrata"
    assert banca[0]["importo"] == 7880.0
    assert banca[0]["estratto_conto_id"] == "EC-vers"
    # la riga EC resta (immutabile) ma viene marcata riconciliata
    ec = db["estratto_conto_movimenti"].docs[0]
    assert ec["riconciliato"] is True
    assert ec["tipo_riconciliazione"] == "versamento_contanti"


def test_ripara_versamenti_cassa_idempotente(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["estratto_conto_movimenti"].docs = [{
        "id": "EC-1", "data": "2026-03-30", "importo": 5000.0,
        "tipo": "entrata", "descrizione_originale": "VERS. CONTANTI - VVVVV",
        "riconciliato": True,
    }]

    _run(mod.ripara_versamenti_cassa(anno=2026))
    res2 = _run(mod.ripara_versamenti_cassa(anno=2026))

    assert res2["creati_cassa"] == 0
    assert res2["creati_banca"] == 0
    assert res2["gia_presenti_cassa"] == 1
    assert res2["gia_presenti_banca"] == 1
    assert len(db["prima_nota_cassa"].docs) == 1
    assert len(db["prima_nota_banca"].docs) == 1


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
