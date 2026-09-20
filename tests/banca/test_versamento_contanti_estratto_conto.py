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

def test_ripara_versamenti_cassa_non_esiste_piu():
    """Non piu' spento: cancellato, endpoint e bottone.

    Creava una gamba di cassa dal solo estratto conto — anche quando il
    versamento era gia' registrato a mano in un altro giorno, e allora il
    contante usciva due volte. Dal 15/09/2026 rispondeva 409; il 20/09 sono
    stati tolti la funzione, la rotta e il passo «Riconcilia versamenti» della
    pagina Pulizia Prima Nota, che altrimenti restava li' a dare errore.

    Il riconoscimento delle causali resta, ed e' quello che i test sotto
    verificano: serve a leggere l'estratto conto, non a scrivere movimenti.
    """
    assert not hasattr(mod, "ripara_versamenti_cassa")


def test_prelievo_non_confuso_con_versamento():
    assert mod.is_prelievo_contanti("PRELIEVO CONTANTI SPORTELLO") is True
    assert mod.is_prelievo_contanti("PRELEV. BANCOMAT CARTA 123") is True
    assert mod.is_prelievo_contanti("VERS. CONTANTI - VVVVV") is False
    assert mod.is_prelievo_contanti("PRELIEVO ASSEGNO - DM 00000") is False
    assert mod.is_prelievo_contanti("") is False
