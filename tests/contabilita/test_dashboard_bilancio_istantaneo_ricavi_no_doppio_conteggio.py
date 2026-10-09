"""Bug trovato nell'audit funzionale del 15/07/2026, confermato dall'utente:
le fatture emesse NON sono mai un ricavo aggiuntivo, sostituiscono sempre
uno scontrino/corrispettivo già registrato (stessa regola del Conto
Economico ufficiale). GET /api/dashboard/bilancio-istantaneo sommava invece
corrispettivi + fatture_emesse senza alcuna deduplica, sovrastimando i
ricavi — in contrasto con la formula ufficiale (ricavi = solo
corrispettivi)."""
import asyncio

from app.routers.reports import dashboard as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def aggregate(self, pipeline, *a, **k):
        match = pipeline[0].get("$match", {}) if pipeline else {}
        matched = [d for d in self.docs if self._matches(d, match)]
        if not matched:
            return _FakeCursor([])
        return _FakeCursor([{
            "_id": None,
            "imponibile": sum(d.get("totale_imponibile", d.get("imponibile", 0)) for d in matched),
            "iva": sum(d.get("totale_iva", d.get("iva", 0)) for d in matched),
            "totale": sum(d.get("totale", d.get("total_amount", 0)) for d in matched),
        }])

    def _matches(self, doc, match):
        for k, v in match.items():
            if k in ("$or", "$and"):
                continue
            if isinstance(v, dict) and "$regex" in v:
                if not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                    return False
            elif isinstance(v, dict) and "$ne" in v:
                if doc.get(k) == v["$ne"]:
                    return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    async def count_documents(self, query):
        return len([d for d in self.docs if self._matches(d, query)])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_ricavi_totali_non_sommano_le_fatture_emesse(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["corrispettivi"].docs = [
        {"data": "2026-05-10", "totale_imponibile": 800.0, "totale_iva": 176.0, "totale": 976.0},
    ]
    db["fatture_emesse"].docs = [
        # Fattura che REPLICA uno scontrino già in corrispettivi: non deve
        # sommarsi di nuovo.
        {"anno": 2026, "imponibile": 200.0, "iva": 44.0, "totale": 244.0},
    ]
    db[mod.Collections.INVOICES].docs = []

    esito = _run(mod.get_bilancio_istantaneo(anno=2026))

    assert esito["ricavi"]["totale"] == 976.0  # solo corrispettivi
    assert esito["ricavi"]["da_corrispettivi"] == 976.0
    # Il dato resta visibile come informativo, solo non più sommato.
    assert esito["ricavi"]["da_fatture_emesse"] == 244.0
    assert esito["iva"]["debito"] == 176.0  # non 220.0 (176+44)
