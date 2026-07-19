"""Bug corretto 16/07/2026 (verifica live: 1066 entrate Corrispettivi per
149 corrispettivi reali, 50 giorni con uscita POS doppia): il purge del
rebuild era limitato a categoria "Corrispettivi" + lista parziale di source,
quindi non eliminava mai le uscite POS né i residui delle pipeline
smantellate (corrispettivo_xml, corrispettivi_pos_sync). Ora il purge è per
source su TUTTE le righe generate dai corrispettivi; i movimenti manuali
(versamenti, pagamenti fatture) non vengono toccati. In più il rebuild non
crea mai due entrate per lo stesso (giorno, matricola, totale) anche se in
collection restano documenti corrispettivi duplicati."""
import asyncio

from app.routers.invoices import corrispettivi_helpers as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$regex" in v and not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

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

    async def delete_many(self, query, *a, **k):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, query)]

        class _R:
            deleted_count = before - len(self.docs)
        return _R()

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


def _setup_db():
    db = _Db()
    db["corrispettivi"].docs = [
        {"id": "c1", "data": "2026-01-02", "matricola_rt": "RT1", "totale": 5169.0,
         "pagato_contanti": 1552.0, "pagato_elettronico": 3617.0, "created_at": "2026-01-02"},
        # Documento DUPLICATO dello stesso giorno (reimport storico mai ripulito)
        {"id": "c1-dup", "data": "2026-01-02", "matricola_rt": "RT1", "totale": 5169.0,
         "pagato_contanti": 1552.0, "pagato_elettronico": 3617.0, "created_at": "2026-01-05"},
    ]
    db["prima_nota_cassa"].docs = [
        # residui da ripulire (tutte le pipeline, entrate E uscite POS)
        {"id": "e1", "data": "2026-01-02", "tipo": "entrata", "importo": 5169.0,
         "categoria": "Corrispettivi", "source": "corrispettivo_import"},
        {"id": "e2", "data": "2026-01-02", "tipo": "entrata", "importo": 5169.0,
         "categoria": "Corrispettivi", "source": "corrispettivo_xml"},
        {"id": "u1", "data": "2026-01-02", "tipo": "uscita", "importo": 3617.0,
         "categoria": "POS Verso Banca", "source": "corrispettivo_import"},
        {"id": "u2", "data": "2026-01-02", "tipo": "uscita", "importo": 3617.0,
         "categoria": "POS", "source": "corrispettivi_pos_sync"},
        {"id": "u3", "data": "2026-01-02", "tipo": "uscita", "importo": 3617.0,
         "categoria": "Girofondi POS", "source": "corrispettivo_xml"},
        # movimenti NON derivati dai corrispettivi: intoccabili
        {"id": "v1", "data": "2026-01-02", "tipo": "uscita", "importo": 41570.0,
         "categoria": "Versamento Banca", "source": "versamento_contanti"},
        {"id": "f1", "data": "2026-01-03", "tipo": "uscita", "importo": 100.0,
         "categoria": "Fatture", "source": "sync_fatture"},
    ]
    db["prima_nota_banca"].docs = [
        {"id": "b1", "data": "2026-01-02", "tipo": "entrata", "importo": 3617.0,
         "categoria": "Corrispettivi POS", "source": "corrispettivo_pos"},
        {"id": "b2", "data": "2026-01-03", "tipo": "uscita", "importo": 100.0,
         "categoria": "Pagamento fornitore", "source": "fattura_pagata"},
    ]
    return db


def test_purge_elimina_tutte_le_pipeline_e_ricrea_pulito():
    db = _setup_db()

    esito = _run(mod.rebuild_prima_nota_from_corrispettivi(db, anno=2026))

    assert esito["prima_nota_cassa_eliminati"] == 5  # e1 e2 u1 u2 u3, NON v1/f1
    assert esito["prima_nota_banca_eliminati"] == 1  # b1, NON b2
    assert esito["corrispettivi_processati"] == 1
    assert esito["corrispettivi_duplicati_saltati"] == 1  # c1-dup non ricrea nulla

    cassa = db["prima_nota_cassa"].docs
    entrate = [m for m in cassa if m.get("tipo") == "entrata" and m.get("categoria") == "Corrispettivi"]
    uscite_pos = [m for m in cassa if m.get("tipo") == "uscita" and m.get("categoria") == "POS Verso Banca"]
    assert len(entrate) == 1 and entrate[0]["importo"] == 5169.0
    assert len(uscite_pos) == 1 and uscite_pos[0]["importo"] == 3617.0
    # intoccati
    assert any(m["id"] == "v1" for m in cassa)
    assert any(m["id"] == "f1" for m in cassa)

    banca = db["prima_nota_banca"].docs
    entrate_pos = [m for m in banca if m.get("source") == "corrispettivo_pos"]
    assert entrate_pos == []  # MODELLO POS 18/07/2026: mai banca sintetica (entrata banca = accredito EC reale)
    assert any(m["id"] == "b2" for m in banca)
