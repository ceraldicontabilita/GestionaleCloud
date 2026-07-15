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
    assert res["riparati"] == 1
    assert res["gia_presenti"] == 0

    cassa = db["prima_nota_cassa"].docs
    assert len(cassa) == 1
    assert cassa[0]["tipo"] == "uscita"
    assert cassa[0]["categoria"] == "Versamento"
    assert cassa[0]["importo"] == 5000.0
    assert cassa[0]["estratto_conto_id"] == "EC-vecchio"


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

    assert res2["riparati"] == 0
    assert res2["gia_presenti"] == 1
    assert len(db["prima_nota_cassa"].docs) == 1
