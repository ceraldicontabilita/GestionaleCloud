"""Segnalato dall'utente 18/07/2026: un pagamento PayPal a Spotify risultava
collegato alla fattura di "Ricambi Manzo sas" (fornitore completamente
estraneo), un altro a una fattura ormai cancellata ("Fattura non trovata").
Causa: auto_associa_transazioni scriveva un collegamento "certo" anche con
UN SOLO candidato trovato per pura coincidenza di importo, senza alcun
riscontro sul nome del fornitore — frequente per le controparti PayPal-
native/estere (Spotify, OpenAI...) che non hanno mai una fattura italiana
nel gestionale. Ora questi match "a indovinare" non vengono più scritti, e
un endpoint di pulizia rimuove lo storico già scritto in produzione."""
import asyncio

from app.routers.paypal_statements import auto_associa_transazioni, pulisci_match_solo_importo


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self

    async def to_list(self, n):
        return self._docs[:n]


class _AggCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs[:n]


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, q=None, proj=None):
        def _match(doc, cond):
            for k, v in (cond or {}).items():
                if k == "fattura_associata.match":
                    if (doc.get("fattura_associata") or {}).get("match") != v:
                        return False
                elif k == "fattura_associata":
                    exists = "fattura_associata" in doc
                    if isinstance(v, dict) and "$exists" in v and exists != v["$exists"]:
                        return False
                elif isinstance(v, dict):
                    val = doc.get(k)
                    if "$lt" in v and not (val is not None and val < v["$lt"]):
                        return False
                else:
                    if doc.get(k) != v:
                        return False
            return True
        return _Cursor([d for d in self.docs if _match(d, q)])

    def aggregate(self, pipeline):
        # Simula $addFields + $match su _importo_coalesced + $limit per invoices
        match_stage = next((s["$match"] for s in pipeline if "$match" in s), {})
        rng = match_stage.get("_importo_coalesced", {})
        out = []
        for d in self.docs:
            val = d.get("total_amount", d.get("importo_totale"))
            if val is None:
                continue
            if "$gte" in rng and val < rng["$gte"]:
                continue
            if "$lte" in rng and val > rng["$lte"]:
                continue
            out.append(d)
        return _AggCursor(out)

    async def update_one(self, q, update):
        for d in self.docs:
            if d.get("transaction_id") == q.get("transaction_id"):
                if "$set" in update:
                    d.update(update["$set"])

    async def update_many(self, q, update):
        n = 0
        matched = self.find(q)._docs
        for d in matched:
            if "$unset" in update:
                for k in update["$unset"]:
                    d.pop(k, None)
            n += 1
        return type("R", (), {"modified_count": n})()


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())


def test_auto_associa_non_scrive_match_solo_importo(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "importo": -20.99, "lordo": -20.99,
         "nome_controparte": "Spotify AB", "data": "2026-07-12"},
    ]
    db["invoices"].docs = [
        {"id": "f1", "invoice_number": "P447FF04EC", "invoice_date": "2026-07-10",
         "supplier_name": "Ricambi Manzo sas di Manzo dr. Raf", "total_amount": 20.99},
    ]

    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(auto_associa_transazioni())
    assert res["associate"] == 0
    assert "fattura_associata" not in db["paypal_transactions"].docs[0]


def test_auto_associa_scrive_solo_con_riscontro_nome(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "importo": -100.0, "lordo": -100.0,
         "nome_controparte": "Fornitore Rossi Srl", "data": "2026-07-12"},
    ]
    db["invoices"].docs = [
        {"id": "f1", "invoice_number": "X1", "invoice_date": "2026-07-10",
         "supplier_name": "Fornitore Rossi Srl", "total_amount": 100.0},
        {"id": "f2", "invoice_number": "X2", "invoice_date": "2026-07-11",
         "supplier_name": "Altra Azienda Srl", "total_amount": 100.0},
    ]

    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(auto_associa_transazioni())
    assert res["associate"] == 1
    fa = db["paypal_transactions"].docs[0]["fattura_associata"]
    assert fa["fattura_id"] == "f1"
    assert fa["match"] == "nome_e_importo"


def test_pulisci_match_solo_importo_dry_run_non_modifica(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "nome_controparte": "Spotify AB",
         "fattura_associata": {"fattura_id": "f1", "fornitore": "Ricambi Manzo sas", "match": "solo_importo"}},
        {"transaction_id": "t2", "nome_controparte": "Fornitore Rossi Srl",
         "fattura_associata": {"fattura_id": "f2", "fornitore": "Fornitore Rossi Srl", "match": "nome_e_importo"}},
    ]
    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(pulisci_match_solo_importo(dry_run=True))
    assert res["trovate"] == 1
    assert res["esempi"][0]["controparte"] == "Spotify AB"
    assert "fattura_associata" in db["paypal_transactions"].docs[0]


def test_pulisci_match_solo_importo_applica(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "nome_controparte": "Spotify AB",
         "fattura_associata": {"fattura_id": "f1", "fornitore": "Ricambi Manzo sas", "match": "solo_importo"}},
        {"transaction_id": "t2", "nome_controparte": "Fornitore Rossi Srl",
         "fattura_associata": {"fattura_id": "f2", "fornitore": "Fornitore Rossi Srl", "match": "nome_e_importo"}},
    ]
    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(pulisci_match_solo_importo(dry_run=False))
    assert res["trovate"] == 1
    assert "fattura_associata" not in db["paypal_transactions"].docs[0]
    assert db["paypal_transactions"].docs[1]["fattura_associata"]["match"] == "nome_e_importo"
