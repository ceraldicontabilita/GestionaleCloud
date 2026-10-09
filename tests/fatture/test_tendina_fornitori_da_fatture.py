"""La tendina «Tutti i fornitori» di Fatture ricevute elencava solo i 22
fornitori con `fatture_count` salvato, su 202 in anagrafica e 153 con fatture
attive. «Ha fatture» si ricava dalle fatture attive."""
import asyncio

from app.services.archivio_documenti_memoria import matches_filter

from app.routers.fatture_module import crud as mod


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query=None, projection=None, *a, **k):
        return _Cursor([d for d in self.docs if matches_filter(d, query or {})])


class _Db:
    def __init__(self, colls):
        self.colls = colls

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll([]))


def test_tendina_fornitori_usa_le_fatture_attive(monkeypatch):
    db = _Db({
        "fornitori": _Coll([
            # Senza `fatture_count`: prima non compariva.
            {"ragione_sociale": "Alfa Srl", "partita_iva": "01234567890"},
            # Prefisso IT sulla fattura, non sull'anagrafica.
            {"ragione_sociale": "Beta Srl", "partita_iva": "09876543210"},
            # Solo fattura eliminata: non deve comparire.
            {"ragione_sociale": "Gamma Srl", "partita_iva": "11111111111",
             "fatture_count": 5},
            # Nessuna fattura.
            {"ragione_sociale": "Delta Srl", "partita_iva": "22222222222"},
        ]),
        "invoices": _Coll([
            {"id": "1", "supplier_vat": "01234567890"},
            {"id": "2", "supplier_vat": "IT09876543210"},
            {"id": "3", "supplier_vat": "11111111111", "status": "deleted"},
        ]),
    })
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    esito = asyncio.run(mod.get_fornitori(search=None, con_fatture=True, limit=500))
    assert [f["ragione_sociale"] for f in esito["items"]] == ["Alfa Srl", "Beta Srl"]
