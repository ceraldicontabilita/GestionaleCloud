import asyncio
from collections import defaultdict

from app.routers.accounting import contabilita_gestionale as mod
from app.routers.accounting import bilancio


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, rows): self.rows = rows
    async def to_list(self, _n): return list(self.rows)


class _Collection:
    def __init__(self, rows=None): self.rows = list(rows or [])
    def find(self, *_args, **_kwargs): return _Cursor(self.rows)


class _DB(defaultdict):
    def __init__(self): super().__init__(_Collection)


def test_budget_totals_use_canonical_monthly_pnl(monkeypatch):
    db = _DB()
    monkeypatch.setattr(mod.Database, 'get_db', staticmethod(lambda: db))

    async def fake_budget(_anno):
        return {
            'voci': [
                {'voce': 'Ricavi', 'categoria': 'ricavo', 'importo_annuale': 1200.0,
                 'mensile': {m: 100.0 for m in range(1, 13)}},
                {'voce': 'Acquisti', 'categoria': 'costo', 'importo_annuale': 600.0,
                 'mensile': {m: 50.0 for m in range(1, 13)}},
            ],
            'totali': {'ricavi_budget': 1200.0, 'costi_budget': 600.0},
        }
    monkeypatch.setattr(mod, 'get_budget_completo', fake_budget)

    async def fake_ce(*, anno, mese):
        assert anno == 2026
        return {
            'ricavi': {'totale_ricavi': float(mese * 10)},
            'costi': {'totale_costi': float(mese * 4)},
        }
    monkeypatch.setattr(bilancio, 'get_conto_economico', fake_ce)

    out = _run(mod.get_budget_vs_consuntivo(2026, mese=None))
    assert out['totali']['ricavi']['consuntivo'] == sum(m * 10 for m in range(1, 13))
    assert out['totali']['costi']['consuntivo'] == sum(m * 4 for m in range(1, 13))
    assert out['andamento_mensile'][5]['ricavi_consuntivo'] == 60.0
    assert out['qualita_consuntivo']['totali_fonte'] == 'conto_economico_canonico'
    assert out['qualita_consuntivo']['totali_validati'] is True
    assert out['qualita_consuntivo']['dettaglio_per_voce_validato'] is False
