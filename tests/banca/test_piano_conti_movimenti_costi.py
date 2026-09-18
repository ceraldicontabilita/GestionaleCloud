"""Segnalato dall'utente 18/07/2026: nel Piano dei Conti, cliccando su
QUALSIASI sotto-conto costi (es. "05.02.22 Noleggio automezzi", saldo €0,00
"Inattivo") usciva sempre lo stesso elenco di 40 fatture di fornitori
completamente estranei (HP Italy, Eureka Onlus, Leasys, Langellotti...),
identico a quello mostrato per "05.01.09 Acquisto caffè e affini" (saldo
reale €3.331,04). Causa: get_movimenti_per_conto, per la categoria "costi",
interrogava TUTTE le fatture dell'anno senza filtrare per il conto
effettivamente cliccato — a differenza del saldo (_calcola_saldi_piano_conti)
che invece splitta correttamente le righe fattura per conto tramite il
dizionario_articoli. Ora il ramo costi usa la STESSA aggregazione per riga
del saldo, filtrando a valle sul conto richiesto."""
import asyncio

from app.routers.accounting.piano_conti import get_movimenti_per_conto


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_dotted(d, path):
    cur = d
    for p in path.split("."):
        if isinstance(cur, list):
            cur = [(_get_dotted(item, p) if isinstance(item, dict) else None) for item in cur]
        elif isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def _eval_expr(expr, doc):
    if isinstance(expr, dict):
        if "$ifNull" in expr:
            a, b = expr["$ifNull"]
            v = _eval_expr(a, doc)
            return v if v is not None else _eval_expr(b, doc)
        if "$arrayElemAt" in expr:
            arr_expr, idx = expr["$arrayElemAt"]
            arr = _eval_expr(arr_expr, doc)
            if isinstance(arr, list) and len(arr) > idx:
                return arr[idx]
            return None
        return None
    if isinstance(expr, str) and expr.startswith("$"):
        return _get_dotted(doc, expr[1:])
    return expr


def _match_expr(doc, spec):
    for k, v in spec.items():
        if _get_dotted(doc, k) != v:
            return False
    return True


class _AggCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs[:n]


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def count_documents(self, q=None):
        return len(self.docs)

    def find(self, q=None, proj=None):
        return _AggCursor([d for d in self.docs])

    def aggregate(self, pipeline, lookup_source=None):
        data = [dict(d) for d in self.docs]
        for stage in pipeline:
            op, spec = next(iter(stage.items()))
            if op == "$match":
                data = [d for d in data if _match_expr(d, spec)]
            elif op == "$unwind":
                path = spec["path"].lstrip("$")
                preserve = spec.get("preserveNullAndEmptyArrays", False)
                new_data = []
                for d in data:
                    arr = d.get(path)
                    if isinstance(arr, list) and arr:
                        for item in arr:
                            nd = dict(d)
                            nd[path] = item
                            new_data.append(nd)
                    elif preserve:
                        new_data.append(dict(d))
                data = new_data
            elif op == "$lookup":
                coll = lookup_source[spec["from"]].docs
                lf, ff, as_ = spec["localField"], spec["foreignField"], spec["as"]
                new_data = []
                for d in data:
                    lv = _get_dotted(d, lf)
                    matches = [c for c in coll if c.get(ff) == lv]
                    nd = dict(d)
                    nd[as_] = matches
                    new_data.append(nd)
                data = new_data
            elif op == "$addFields":
                for d in data:
                    for k, expr in spec.items():
                        d[k] = _eval_expr(expr, d)
            elif op == "$sort":
                key, direction = next(iter(spec.items()))
                data.sort(key=lambda d: d.get(key) or "", reverse=(direction == -1))
            elif op == "$limit":
                data = data[:spec]
            elif op == "$project":
                new_data = []
                for d in data:
                    nd = {}
                    for k, v in spec.items():
                        if v == 0:
                            continue
                        if v == 1:
                            val = _get_dotted(d, k)
                            if val is not None:
                                nd[k] = val
                        elif isinstance(v, str) and v.startswith("$"):
                            nd[k] = _get_dotted(d, v[1:])
                    new_data.append(nd)
                data = new_data
        return _AggCursor(data)


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())


def _setup_db():
    db = _DB()
    db["piano_conti"].docs = [
        {"codice": "05.01.09", "nome": "Acquisto caffe e affini", "categoria": "costi"},
        {"codice": "05.02.22", "nome": "Noleggio automezzi", "categoria": "costi"},
        {"codice": "05.06.01", "nome": "Imposte e tasse", "categoria": "costi"},
    ]
    db["dizionario_articoli"].docs = [
        {"descrizione": "Caffe in grani 1kg", "conto": "05.01.09"},
        {"descrizione": "Canone noleggio Leasys", "conto": "05.02.22"},
    ]
    db["invoices"].docs = [
        {"invoice_number": "1", "supplier_name": "Torrefazione Napoli", "invoice_date": "2026-03-01",
         "status": "pagata", "linee": [{"descrizione": "Caffe in grani 1kg", "prezzo_totale": 120.0}]},
        {"invoice_number": "2", "supplier_name": "Leasys Italia S.p.A", "invoice_date": "2026-02-01",
         "status": "pagata", "linee": [{"descrizione": "Canone noleggio Leasys", "prezzo_totale": 1119.48}]},
        {"invoice_number": "3", "supplier_name": "HP Italy S.r.l.", "invoice_date": "2026-07-08",
         "status": "pagata", "linee": [{"descrizione": "Toner stampante", "prezzo_totale": 4.79}]},
    ]
    return db


def _patch(monkeypatch, db):
    import app.routers.accounting.piano_conti as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    orig_aggregate_invoices = db["invoices"].aggregate

    def aggregate_with_lookup(pipeline):
        return orig_aggregate_invoices(pipeline, lookup_source=db._c)

    db["invoices"].aggregate = aggregate_with_lookup


def test_conto_caffe_mostra_solo_le_righe_caffe(monkeypatch):
    db = _setup_db()
    _patch(monkeypatch, db)

    res = _run(get_movimenti_per_conto(codice="05.01.09"))
    assert res["totale_movimenti"] == 1
    assert "Torrefazione" in res["movimenti"][0]["descrizione"]
    assert res["totale_importo"] == 120.0


def test_conto_noleggio_mostra_solo_le_righe_noleggio_non_tutte_le_fatture(monkeypatch):
    """Caso esatto segnalato dall'utente: 05.02.22 Noleggio automezzi non
    deve MAI mostrare Torrefazione Napoli (caffè) o HP Italy (toner)."""
    db = _setup_db()
    _patch(monkeypatch, db)

    res = _run(get_movimenti_per_conto(codice="05.02.22"))
    assert res["totale_movimenti"] == 1
    descrizioni = " ".join(m["descrizione"] for m in res["movimenti"])
    assert "Leasys" in descrizioni
    assert "Torrefazione" not in descrizioni
    assert "HP Italy" not in descrizioni


def test_conto_senza_righe_mappate_non_mostra_dati_estranei(monkeypatch):
    """Un conto costi senza nessuna riga fattura mappata (es. saldo 0,
    "Inattivo") deve restituire una lista vuota, non l'elenco di tutte le
    fatture come prima del fix."""
    db = _setup_db()
    _patch(monkeypatch, db)

    res = _run(get_movimenti_per_conto(codice="05.06.01"))
    assert res["totale_movimenti"] == 0
    assert res["movimenti"] == []
