"""Segnalato dall'utente 18/07/2026: un pagamento PayPal a Spotify risultava
collegato alla fattura di "Ricambi Manzo sas" (fornitore completamente
estraneo), un altro a una fattura ormai cancellata ("Fattura non trovata").
Causa: auto_associa_transazioni scriveva un collegamento "certo" anche con
UN SOLO candidato trovato per pura coincidenza di importo, senza alcun
riscontro sul nome del fornitore — frequente per le controparti PayPal-
native/estere (Spotify, OpenAI...) che non hanno mai una fattura italiana
nel gestionale. Ora questi match "a indovinare" non vengono più scritti.
Inoltre lo storico già scritto in produzione da versioni precedenti della
logica può risultare etichettato "nome_e_importo" pur non avendo mai avuto
un vero riscontro sul nome (i tre pagamenti Spotify del caso segnalato erano
proprio così): l'endpoint di pulizia quindi non si fida dell'etichetta
salvata e rivalida ogni associazione automatica da zero."""
import asyncio

from app.routers.paypal_statements import auto_associa_transazioni, pulisci_match_solo_importo


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _has(doc, dotted):
    parts = dotted.split(".")
    cur = doc
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return False
        cur = cur[p]
    return isinstance(cur, dict) and parts[-1] in cur


def _get(doc, dotted):
    cur = doc
    for p in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def _match(doc, cond):
    if "$and" in (cond or {}):
        if not all(_match(doc, item) for item in cond["$and"]):
            return False
    if "$or" in (cond or {}):
        if not any(_match(doc, item) for item in cond["$or"]):
            return False
    for k, v in (cond or {}).items():
        if k in {"$and", "$or"}:
            continue
        if isinstance(v, dict) and "$exists" in v:
            if _has(doc, k) != v["$exists"]:
                return False
            continue
        if isinstance(v, dict) and "$lt" in v:
            val = _get(doc, k)
            if not (val is not None and val < v["$lt"]):
                return False
            continue
        if isinstance(v, dict) and "$gte" in v:
            val = _get(doc, k)
            if not (val is not None and val >= v["$gte"]):
                return False
            if "$lte" in v and val > v["$lte"]:
                return False
            continue
        if isinstance(v, dict) and "$ne" in v:
            if _get(doc, k) == v["$ne"]:
                return False
            continue
        if isinstance(v, dict) and "$in" in v:
            if _get(doc, k) not in v["$in"]:
                return False
            continue
        if _get(doc, k) != v:
            return False
    return True


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
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if _match(d, q):
                return dict(d)
        return None

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
            if _match(d, q):
                if "$set" in update:
                    d.update(update["$set"])
                for key, value in update.get("$addToSet", {}).items():
                    values = d.setdefault(key, [])
                    if value not in values:
                        values.append(value)
                return

    async def update_many(self, q, update):
        n = 0
        matched = [d for d in self.docs if _match(d, q)]
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


def test_auto_associa_scrive_solo_con_numero_importo_e_fornitore(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "importo": -100.0, "lordo": -100.0,
         "nome_controparte": "Fornitore Rossi Srl", "invoice_id_fornitore": "X1",
         "data": "2026-07-12"},
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
    assert fa["match"] == "fornitore_numero_importo_esatti"
    assert set(fa["evidenze"]) >= {"denominazione_fornitore", "numero_fattura", "importo"}


def test_pulisci_rimuove_associazione_storica_senza_riscontro_anche_se_etichettata_bene(monkeypatch):
    """Caso reale segnalato dall'utente: le 3 transazioni Spotify erano
    etichettate "nome_e_importo" (non "solo_importo") pur puntando a un
    fornitore "Ricambi Manzo sas" che non ha nulla a che vedere con
    "Spotify AB" — l'etichetta storica mente, va rivalidato il nome vero."""
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "5BX54306V8803724Y", "nome_controparte": "Spotify AB",
         "fattura_associata": {"fattura_id": "f1", "fornitore": "Ricambi Manzo sas",
                                "auto": True, "match": "nome_e_importo"}},
        {"transaction_id": "t2", "nome_controparte": "Fornitore Rossi Srl",
         "invoice_id_fornitore": "FT-2", "lordo": -250.00,
         "fattura_associata": {"fattura_id": "f2", "fornitore": "Fornitore Rossi Srl",
                                "auto": True, "match": "nome_e_importo"}},
    ]
    db["invoices"].docs = [
        {"id": "f1", "supplier_name": "Ricambi Manzo sas di Manzo dr. Raf"},
        {"id": "f2", "supplier_name": "Fornitore Rossi Srl",
         "invoice_number": "FT-2", "total_amount": 250.00},
    ]
    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(pulisci_match_solo_importo(dry_run=True))
    assert res["trovate"] == 1
    assert res["esempi"][0]["transaction_id"] == "5BX54306V8803724Y"
    assert res["esempi"][0]["motivo"] == "identita_fornitore_non_verificata"
    # dry_run: nessuna modifica
    assert "fattura_associata" in db["paypal_transactions"].docs[0]


def test_pulisci_rimuove_riferimento_a_fattura_cancellata(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "nome_controparte": "Qualcuno Srl",
         "fattura_associata": {"fattura_id": "non-esiste-piu", "fornitore": "Qualcuno Srl",
                                "auto": True, "match": "nome_e_importo"}},
    ]
    db["invoices"].docs = []
    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(pulisci_match_solo_importo(dry_run=False))
    assert res["trovate"] == 1
    assert res["esempi"][0]["motivo"] == "fattura_non_trovata"
    assert "fattura_associata" not in db["paypal_transactions"].docs[0]


def test_pulisci_rimuove_match_senza_numero_fattura_anche_con_nome_e_importo(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "nome_controparte": "Fornitore Rossi Srl",
         "lordo": -100.01,
         "fattura_associata": {"fattura_id": "f1", "auto": True}},
    ]
    db["invoices"].docs = [
        {"id": "f1", "supplier_name": "Fornitore Rossi Srl",
         "invoice_number": "FT-10", "total_amount": 100.01},
    ]
    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(pulisci_match_solo_importo(dry_run=False))

    assert res["trovate"] == 1
    assert res["esempi"][0]["motivo"] == "numero_fattura_mancante_o_non_coincidente"
    assert "fattura_associata" not in db["paypal_transactions"].docs[0]


def test_pulisci_non_tocca_associazioni_manuali_ne_valide(monkeypatch):
    db = _DB()
    db["paypal_transactions"].docs = [
        {"transaction_id": "t1", "nome_controparte": "Fornitore Rossi Srl",
         "invoice_id_fornitore": "FT-10", "lordo": -100.01,
         "fattura_associata": {"fattura_id": "f1", "fornitore": "Fornitore Rossi Srl",
                                "auto": True, "match": "nome_e_importo"}},
        {"transaction_id": "t2", "nome_controparte": "Chiunque",
         "fattura_associata": {"fattura_id": "f1", "fornitore": "Fornitore Rossi Srl",
                                "auto": False}},
    ]
    db["invoices"].docs = [{"id": "f1", "supplier_name": "Fornitore Rossi Srl",
                             "invoice_number": "FT-10", "total_amount": 100.01}]
    import app.routers.paypal_statements as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(pulisci_match_solo_importo(dry_run=False))
    assert res["trovate"] == 0
    assert "fattura_associata" in db["paypal_transactions"].docs[0]
    assert "fattura_associata" in db["paypal_transactions"].docs[1]
