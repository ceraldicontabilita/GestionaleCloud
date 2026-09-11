import asyncio
from types import SimpleNamespace

from app.routers.accounting import bilancio, centri_costo


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, rows): self.rows = rows
    async def to_list(self, _n): return list(self.rows)


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.updated = []
    def aggregate(self, _pipeline): return _Cursor([])
    def find(self, *_args, **_kwargs): return _Cursor(list(self.rows))
    async def count_documents(self, _query): return 0
    async def find_one(self, *_args, **_kwargs): return None
    async def update_one(self, query, update, **_kwargs):
        self.updated.append((query, update))
        return SimpleNamespace(modified_count=1)


class _DB(dict):
    def __getitem__(self, key):
        if key not in self: self[key] = _Collection()
        return dict.__getitem__(self, key)


def test_utile_obiettivo_riusa_conto_economico_canonico(monkeypatch):
    db = _DB()
    monkeypatch.setattr(centri_costo.Database, 'get_db', staticmethod(lambda: db))

    async def fake_ce(*, anno, mese):
        assert anno == 2026 and mese is None
        return {
            'ricavi': {'totale_ricavi': 1000.0},
            'costi': {'totale_costi': 400.0},
        }
    monkeypatch.setattr(bilancio, 'get_conto_economico', fake_ce)

    out = _run(centri_costo.get_utile_obiettivo(2026))
    assert out['reale']['ricavi_totali'] == 1000.0
    assert out['reale']['costi_totali'] == 400.0
    assert out['reale']['utile_corrente'] == 600.0


def test_cdc_sconosciuto_resta_da_verificare(monkeypatch):
    invoices = _Collection([{'_id': 'f1', 'categoria_contabile': 'misteriosa', 'supplier_name': 'FORNITORE X'}])
    db = _DB(invoices=invoices)
    monkeypatch.setattr(centri_costo.Database, 'get_db', staticmethod(lambda: db))

    out = _run(centri_costo.assegna_cdc_fatture(anno=None, force=False))
    assert out['fatture_aggiornate'] == 0
    assert out['distribuzione']['DA_VERIFICARE'] == 1
    update = invoices.updated[0][1]
    assert update['$set']['cdc_requires_review'] is True
    assert update['$set']['cdc_auto_assigned'] is False
    assert '$unset' in update and 'centro_costo' in update['$unset']


def test_bilancio_source_includes_separate_sumup_register():
    source = open('app/routers/accounting/bilancio.py', encoding='utf-8').read()
    assert 'COLLECTION_PRIMA_NOTA_SUMUP = "prima_nota_sumup"' in source
    assert '"sumup_mastercard": round(saldo_sumup, 2)' in source
    assert 'saldo_cassa + saldo_banca + saldo_sumup' in source
