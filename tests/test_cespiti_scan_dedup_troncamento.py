"""Bug trovato lavorando sull'auto-creazione cespiti da fattura XML
(15/07/2026): POST /api/cespiti/scan-fatture confrontava un dedup_key
troncato a 100 caratteri (`descrizione[:100]`) contro cespiti esistenti
salvati con la descrizione troncata a 200 caratteri (`descrizione[:200]`,
lo stesso troncamento usato dal nuovo handler automatico) — per righe con
descrizione tra 100 e 200 caratteri il confronto non coincideva mai,
rischiando un secondo cespite duplicato ad ogni scan manuale."""
import asyncio

from app.routers import cespiti as mod


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

    def __aiter__(self):
        return _AsyncIter(self._docs)


class _AsyncIter:
    def __init__(self, docs):
        self._it = iter(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor(list(self.docs))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    async def list_collection_names(self):
        return list(self.collections.keys())


DESCRIZIONE_LUNGA = "Impianto di condizionamento e climatizzazione professionale per cucina ristorante con unità esterna e canalizzazioni incluse"  # >100 caratteri


def test_scan_non_duplica_cespite_con_descrizione_oltre_100_caratteri(monkeypatch):
    assert len(DESCRIZIONE_LUNGA) > 100
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cespiti"].docs = [
        {"descrizione": DESCRIZIONE_LUNGA[:200], "valore_acquisto": 4200.0},
    ]
    db["invoices"].docs = [
        {
            "id": "fatt-1", "entity_status": "attivo", "total_amount": 4200.0,
            "invoice_date": "2026-06-10", "supplier_name": "Impianti Srl",
            "righe": [{"descrizione": DESCRIZIONE_LUNGA, "prezzo_totale": 4200.0}],
        },
    ]

    esito = _run(mod.scan_fatture_per_cespiti(soglia_valore=200, dry_run=True))

    assert esito["num_potenziali_cespiti"] == 0  # già esistente, non riproposto
