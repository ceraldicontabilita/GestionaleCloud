"""Bug 14/07/2026 segnalato dall'utente: fornitore "Ceraldi Group" duplicato
3 volte con P.IVA/CF diverse. merge_fornitori() univa i due record fornitore
ma _migra_riferimenti() (nonostante il commento che assumeva convergenza
automatica) NON ripuntava Prima Nota/pagamenti indicizzati sulla P.IVA
testuale del duplicato: quei movimenti restavano orfani, invisibili
dall'estratto del fornitore superstite dopo il merge."""
import asyncio

from app.services import fornitori_dedupe as dedupe_mod


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def update_many(self, query, update, *a, **k):
        n = 0
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                d.update(update.get("$set", {}))
                n += 1

        class _Res:
            modified_count = n

        return _Res()

    async def update_one(self, query, update, *a, **k):
        return await self.update_many(query, update)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    async def list_collection_names(self):
        return list(self.collections.keys())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_merge_fornitori_ripunta_prima_nota_con_piva_diversa(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(dedupe_mod.Database, "get_db", staticmethod(lambda: db))

    db["fornitori"].docs = [
        {"id": "sup-target", "ragione_sociale": "CERALDI GROUP S.R.L.", "partita_iva": "01879020517"},
        {"id": "sup-dup", "ragione_sociale": "Ceraldi Group srl", "partita_iva": "PMUGLN65L23F839F"},
    ]
    db["prima_nota_cassa"].docs = [
        {"id": "pn-1", "fornitore_piva": "PMUGLN65L23F839F", "importo": 100.0},
    ]
    db["prima_nota_banca"].docs = [
        {"id": "pn-2", "fornitore_piva": "PMUGLN65L23F839F", "importo": 200.0},
    ]
    db["pagamenti"].docs = [
        {"id": "pag-1", "fornitore_piva": "PMUGLN65L23F839F", "importo": 50.0},
    ]

    res = _run(dedupe_mod.merge_fornitori("sup-target", "sup-dup", soft=True))

    assert res["success"] is True
    assert res["stats_migrazione"]["prima_nota_cassa_migrati"] == 1
    assert res["stats_migrazione"]["prima_nota_banca_migrati"] == 1
    assert res["stats_migrazione"]["pagamenti_migrati"] == 1
    assert db["prima_nota_cassa"].docs[0]["fornitore_piva"] == "01879020517"
    assert db["prima_nota_banca"].docs[0]["fornitore_piva"] == "01879020517"
    assert db["pagamenti"].docs[0]["fornitore_piva"] == "01879020517"


def test_merge_fornitori_stessa_piva_non_tocca_prima_nota(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(dedupe_mod.Database, "get_db", staticmethod(lambda: db))

    db["fornitori"].docs = [
        {"id": "sup-target", "ragione_sociale": "ACME SRL", "partita_iva": "12345678901"},
        {"id": "sup-dup", "ragione_sociale": "ACME S.R.L.", "partita_iva": "12345678901"},
    ]
    db["prima_nota_cassa"].docs = [
        {"id": "pn-1", "fornitore_piva": "12345678901", "importo": 100.0},
    ]

    res = _run(dedupe_mod.merge_fornitori("sup-target", "sup-dup", soft=True))

    assert res["stats_migrazione"]["prima_nota_cassa_migrati"] == 0
    assert db["prima_nota_cassa"].docs[0]["fornitore_piva"] == "12345678901"
