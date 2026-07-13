"""Libro giornale e libro mastro: le scritture in partita doppia si generano
agli eventi della fattura, quadrano, non si duplicano al reimport (dedup per
hash) e vivono in `scritture_contabili`, separata da `invoices` → il mastro si
ricostruisce anche dopo l'azzeramento delle fatture."""
import asyncio

from app.services import libro_giornale as lg


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    def aggregate(self, pipeline):
        # Mini-esecutore: supporta $match, $unwind righe, $group per conto, $sort.
        rows = [dict(d) for d in self.docs]
        for stage in pipeline:
            if "$match" in stage:
                m = stage["$match"]
                rows = [r for r in rows if _match(r, m)]
            elif "$unwind" in stage:
                field = stage["$unwind"].lstrip("$")
                unwound = []
                for r in rows:
                    for item in (r.get(field) or []):
                        nr = dict(r)
                        nr[field] = item
                        unwound.append(nr)
                rows = unwound
            elif "$group" in stage:
                rows = _group(rows, stage["$group"])
            elif "$sort" in stage:
                key = list(stage["$sort"].keys())[0]
                rows.sort(key=lambda r: (r.get(key) is None, r.get(key)))
        return _AsyncIter(rows)


def _match(r, m):
    for k, cond in m.items():
        val = r.get(k)
        if isinstance(cond, dict):
            for op, cmp in cond.items():
                if op == "$gte" and not (val and val >= cmp):
                    return False
                if op == "$lte" and not (val and val <= cmp):
                    return False
        elif val != cond:
            return False
    return True


def _group(rows, spec):
    id_expr = spec["_id"]
    buckets = {}
    for r in rows:
        key = _resolve(r, id_expr)
        b = buckets.setdefault(key, {"_id": key})
        for out_field, acc in spec.items():
            if out_field == "_id":
                continue
            if "$sum" in acc:
                inc = acc["$sum"]
                inc = 1 if inc == 1 else _resolve(r, inc)
                b[out_field] = b.get(out_field, 0) + (inc or 0)
            elif "$last" in acc:
                b[out_field] = _resolve(r, acc["$last"])
    return list(buckets.values())


def _resolve(r, expr):
    if isinstance(expr, str) and expr.startswith("$"):
        cur = r
        for part in expr[1:].split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur
    if isinstance(expr, dict):
        if "$toDouble" in expr:
            return float(_resolve(r, expr["$toDouble"]) or 0)
        if "$ifNull" in expr:
            a, b = expr["$ifNull"]
            v = _resolve(r, a)
            return v if v is not None else b
    return expr


class _AsyncIter:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _fattura():
    return {
        "id": "F1", "invoice_key": "K-1", "invoice_number": "10",
        "supplier_name": "ACME Srl", "invoice_date": "2026-04-05",
        "imponibile": 100.0, "iva": 22.0, "total_amount": 122.0,
    }


def test_scrittura_acquisto_quadra_e_non_duplica():
    db = _Db()
    f = _fattura()
    id1 = _run(lg.genera_scrittura_acquisto(db, f))
    assert id1 is not None
    coll = db.colls["scritture_contabili"]
    assert len(coll.docs) == 1
    scr = coll.docs[0]
    # quadratura Dare == Avere
    tot_dare = sum(r["dare"] for r in scr["righe"])
    tot_avere = sum(r["avere"] for r in scr["righe"])
    assert round(tot_dare, 2) == round(tot_avere, 2) == 122.0
    assert scr["invoice_key"] == "K-1"

    # Reimport della stessa fattura → dedup per hash, nessun doppione
    _run(lg.genera_scrittura_acquisto(db, dict(f, id="F1-NEW")))
    assert len(coll.docs) == 1


def test_pagamento_chiude_il_debito_nel_mastro():
    db = _Db()
    f = _fattura()
    _run(lg.genera_scrittura_acquisto(db, f))
    _run(lg.genera_scrittura_pagamento(db, dict(f, data_pagamento="2026-04-20"), mezzo="banca"))

    mastrini = _run(lg.libro_mastro(db))
    per_conto = {m["conto"]: m for m in mastrini}
    # Debiti v/fornitori: nasce in Avere (122) con l'acquisto, si chiude in Dare
    # (122) col pagamento → saldo 0 = fornitore pagato.
    assert round(per_conto["60.01"]["saldo"], 2) == 0.0
    # Banca movimentata in Avere per il pagamento
    assert round(per_conto["40.02"]["avere"], 2) == 122.0
    # quadratura generale del mastro: Σ Dare == Σ Avere
    tot_dare = round(sum(m["dare"] for m in mastrini), 2)
    tot_avere = round(sum(m["avere"] for m in mastrini), 2)
    assert tot_dare == tot_avere


def test_mastro_sopravvive_azzeramento_fatture():
    db = _Db()
    _run(lg.genera_scrittura_acquisto(db, _fattura()))
    # azzero le fatture: le scritture sono in una collezione separata
    db.colls["invoices"] = _Coll()
    mastrini = _run(lg.libro_mastro(db))
    assert any(m["conto"] == "80.01" for m in mastrini)  # Acquisti ancora nel mastro
