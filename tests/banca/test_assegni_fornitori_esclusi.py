"""Fornitori mai pagabili con assegno (richiesta utente 18/07/2026):
Amazon, ABC acquedotto, Fastweb, PayPal, Enel, Leasys, Arval arrivano su
carta di credito o addebito bancario, mai su assegno — non devono comparire
tra le proposte di riconciliazione assegni."""
import asyncio

from app.routers.bank.assegni_auto_match import (
    FORNITORI_MAI_ASSEGNO,
    fornitore_esclude_assegno,
    _load_open_invoices_by_piva,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_fornitore_esclude_assegno_riconosce_i_nomi_dettati():
    for nome in ("Amazon EU S.a.r.l.", "ABC Acquedotto Campano", "Fastweb S.p.A.",
                 "PayPal (Europe)", "Enel Energia", "Leasys Plan S.p.A.",
                 "Leasys Italia", "Arval Service Lease Italia"):
        assert fornitore_esclude_assegno(nome), nome


def test_fornitore_esclude_assegno_lascia_passare_gli_altri():
    for nome in ("Bianchi Forniture Srl", "Rossi & C. Snc", "Studio Verdi"):
        assert not fornitore_esclude_assegno(nome)


def test_fornitori_dettati_coprono_lista_utente():
    attesi = {"amazon", "abc acquedotto", "fastweb", "paypal", "enel", "leasys", "arval"}
    for k in attesi:
        assert any(k in x for x in FORNITORI_MAI_ASSEGNO)


# ----------------------------------------------- repository asincrono fittizio

def _match(doc, cond):
    for k, v in (cond or {}).items():
        if k == "$and":
            if not all(_match(doc, c) for c in v):
                return False
        elif k == "$or":
            if not any(_match(doc, c) for c in v):
                return False
        elif k == "$nin":
            continue
        elif isinstance(v, dict):
            val = doc.get(k)
            if "$gt" in v and not (val is not None and val > v["$gt"]):
                return False
            if "$ne" in v and val == v["$ne"]:
                return False
            if "$nin" in v and val in v["$nin"]:
                return False
            if "$in" in v and val not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    def find(self, q=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, q)])


class _DB:
    def __init__(self, invoices, fornitori):
        self._c = {"invoices": _Coll(invoices), "fornitori": _Coll(fornitori)}

    def __getitem__(self, name):
        return self._c[name]


def test_load_open_invoices_esclude_fornitori_mai_assegno():
    invoices = [
        {"id": "1", "total_amount": 100.0, "payment_status": "open",
         "entity_status": "attivo", "supplier_vat": "11111111111",
         "supplier_name": "Amazon EU S.a.r.l."},
        {"id": "2", "total_amount": 200.0, "payment_status": "open",
         "entity_status": "attivo", "supplier_vat": "22222222222",
         "supplier_name": "Bianchi Forniture Srl"},
    ]
    db = _DB(invoices, [])
    by_piva = _run(_load_open_invoices_by_piva(db))
    assert "11111111111" not in by_piva
    assert "22222222222" in by_piva
