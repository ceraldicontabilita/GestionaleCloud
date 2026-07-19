"""Bug grave verificato live 17/07/2026: la cassa era risalita da 428k a
4,3M in 24 ore. Corrispettivi legacy SENZA campo id mandavano in tilt il
dedup del catch-up scheduler (cercava corrispettivo_id:"" ma il movimento
aveva None) che ricreava l'entrata a ogni giro. Due difese:
1) guardia di idempotenza nel writer canonico: mai due entrate
   "Corrispettivi" per la stessa giornata (un solo registratore);
2) lo scheduler assegna un id ai documenti che ne sono privi e deduplica
   anche per data."""
import asyncio

from app.routers.invoices import corrispettivi_helpers as mod_helpers
from app.routers.prima_nota_module import sync as mod_sync


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$exists" in v and (k in doc) != v["$exists"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _Cursor([dict(d) for d in self.docs if _match(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return

    async def find_one_and_update(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        if upsert:
            self.docs.append(dict(update.get("$setOnInsert", {})))
        return None


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


CORR = {"data": "2026-04-06", "totale": 3787.29,
        "pagato_contanti": 1000.0, "pagato_elettronico": 2787.29}


def test_writer_non_crea_mai_due_entrate_stessa_giornata():
    db = _Db()

    r1 = _run(mod_helpers._create_prima_nota_movements(db, dict(CORR)))
    r2 = _run(mod_helpers._create_prima_nota_movements(db, dict(CORR)))

    entrate = [m for m in db["prima_nota_cassa"].docs
               if m["tipo"] == "entrata" and m["categoria"] == "Corrispettivi"]
    assert len(entrate) == 1  # la seconda chiamata NON duplica
    assert r2.get("gia_esistente") is True
    assert r2["prima_nota_cassa_id"] == r1["prima_nota_cassa_id"]
    # e non duplica neanche uscita POS / entrata banca
    assert len([m for m in db["prima_nota_cassa"].docs if m["tipo"] == "uscita"]) == 1
    assert len(db["prima_nota_banca"].docs) == 1  # REGOLA CANONICA: un solo trasferimento, mai duplicato


def test_scheduler_assegna_id_ai_doc_legacy_e_non_ricrea(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod_sync.Database, "get_db", staticmethod(lambda: db))
    # Documento LEGACY senza campo id: era il caso che duplicava all'infinito.
    db["corrispettivi"].docs = [
        {"data": "2026-04-06", "totale": 3787.29, "anno": 2026,
         "pagato_contanti": 1000.0, "pagato_elettronico": 2787.29,
         "created_at": "2026-04-06T20:00:00"},
    ]

    r1 = _run(mod_sync._sync_corrispettivi_impl(2026))
    r2 = _run(mod_sync._sync_corrispettivi_impl(2026))

    assert r1["inseriti"] == 1
    assert r2["inseriti"] == 0  # secondo giro: dedup, niente ricreazione
    assert r2["duplicati"] == 1
    assert db["corrispettivi"].docs[0].get("id")  # id assegnato al legacy
    entrate = [m for m in db["prima_nota_cassa"].docs
               if m["tipo"] == "entrata" and m["categoria"] == "Corrispettivi"]
    assert len(entrate) == 1
