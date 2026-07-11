"""
Coerenza POS — FASE 2 (POS reale vs Banca), fix del 12/07/2026.

Bug: la card "Accrediti banca mancanti" mostrava ~126.407 € su 41 giorni come
falso disavanzo. Causa: _carica_accrediti_banca_pos NON riconosceva gli
accrediti del provider reale (NUMIA) e filtrava sul campo esatto tipo="entrata".
Così l'estratto conto (che copre 16 mesi) non veniva agganciato e ogni giorno
con POS diventava "mancante".

Questi test verificano il comportamento del caricatore accrediti con un fake db
che riproduce la semantica della query Mongo usata (data range, importo>0,
source $nin, $or su descrizione/categoria con $regex case-insensitive).
"""
import re
import asyncio

from app.routers import pos_corrispettivi_check as pc


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _FakeBankColl:
    """Riproduce la semantica della query usata da _carica_accrediti_banca_pos."""

    def __init__(self, docs):
        self.docs = docs

    def _match(self, doc, query):
        # data range
        dr = query["data"]
        d = doc.get("data", "")
        if not (dr["$gte"] <= d <= dr["$lte"]):
            return False
        # importo > 0
        if not (float(doc.get("importo") or 0) > query["importo"]["$gt"]):
            return False
        # source $nin
        if doc.get("source") in query["source"]["$nin"]:
            return False
        # $or descrizione/categoria regex (case-insensitive)
        ok = False
        for cond in query["$or"]:
            for campo, spec in cond.items():
                val = doc.get(campo) or ""
                if re.search(spec["$regex"], val, re.IGNORECASE):
                    ok = True
        return ok

    def find(self, query, projection=None):
        return _FakeCursor([d for d in self.docs if self._match(d, query)])


class _FakeDb:
    def __init__(self, docs):
        self._coll = _FakeBankColl(docs)

    def __getitem__(self, name):
        assert name == "prima_nota_banca"
        return self._coll


def _run(coro):
    # Loop isolato: get_event_loop() condiviso entra in conflitto con gli
    # altri test async della suite (loop già chiuso/in uso).
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_accredito_numia_viene_riconosciuto():
    """Un accredito NUMIA (senza campo 'tipo') deve essere caricato: prima
    veniva ignorato perché la keyword 'NUMIA' non era in elenco e mancava
    tipo='entrata'."""
    docs = [
        {"data": "2026-03-10", "importo": 3618.0,
         "descrizione": "ACCREDITO NUMIA S.P.A. INCASSI POS", "categoria": "Ricavi - Incasso tramite POS"},
    ]
    out = _run(pc._carica_accrediti_banca_pos(_FakeDb(docs), "2026-01-01", "2026-12-31"))
    assert out.get("2026-03-10") == 3618.0


def test_entrate_per_importo_non_per_campo_tipo():
    """Le entrate si riconoscono per importo>0 anche se il doc non ha 'tipo'."""
    docs = [
        {"data": "2026-03-11", "importo": 3022.0, "descrizione": "NUMIA ACCREDITO"},  # niente 'tipo'
    ]
    out = _run(pc._carica_accrediti_banca_pos(_FakeDb(docs), "2026-01-01", "2026-12-31"))
    assert out.get("2026-03-11") == 3022.0


def test_uscite_e_chiusure_manuali_escluse():
    """Le uscite (importo<0) e le chiusure manuali NON sono accrediti."""
    docs = [
        {"data": "2026-03-12", "importo": -500.0, "descrizione": "COMMISSIONI NUMIA"},        # uscita
        {"data": "2026-03-12", "importo": 2994.0, "descrizione": "Chiusura POS mobile",
         "source": "chiusura_pos_mobile"},                                                    # chiusura manuale
        {"data": "2026-03-12", "importo": 2994.0, "descrizione": "ACCREDITO NUMIA POS"},       # vero accredito
    ]
    out = _run(pc._carica_accrediti_banca_pos(_FakeDb(docs), "2026-01-01", "2026-12-31"))
    # Resta solo il vero accredito NUMIA
    assert out.get("2026-03-12") == 2994.0


def test_movimenti_non_pos_ignorati():
    """Un bonifico qualsiasi (senza keyword POS/NUMIA) non è un accredito POS."""
    docs = [
        {"data": "2026-03-13", "importo": 5000.0, "descrizione": "BONIFICO DA CLIENTE ROSSI"},
    ]
    out = _run(pc._carica_accrediti_banca_pos(_FakeDb(docs), "2026-01-01", "2026-12-31"))
    assert out == {}


def test_numia_in_categoria():
    """Riconoscimento anche quando NUMIA è nella categoria e non nella descrizione."""
    docs = [
        {"data": "2026-03-14", "importo": 1500.0, "descrizione": "Accredito", "categoria": "Incasso NUMIA"},
    ]
    out = _run(pc._carica_accrediti_banca_pos(_FakeDb(docs), "2026-01-01", "2026-12-31"))
    assert out.get("2026-03-14") == 1500.0
