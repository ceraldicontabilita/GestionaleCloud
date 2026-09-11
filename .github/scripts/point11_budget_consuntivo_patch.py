from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:160]}')
    p.write_text(text.replace(old, new, 1))

path = 'app/routers/accounting/contabilita_gestionale.py'

# Keep category drill-down as managerial analysis, but source all monthly totals
# from the canonical P&L calculator so Budget vs Actual cannot invent a second P&L.
replace_once(path,
'''    # --- CONFRONTO PER VOCE ---\n    confronto_voci = []\n''',
'''    # --- TOTALI CONSUNTIVI CANONICI ---\n    # Il dettaglio per categoria sopra e' analitico/gestionale. I totali che\n    # alimentano margine, grafico e scostamenti devono invece coincidere col\n    # Conto Economico canonico (imponibile, note di credito, soft-delete e\n    # criteri data unificati).\n    from app.routers.accounting.bilancio import get_conto_economico\n    ricavi_mensili_canonici = {}\n    costi_mensili_canonici = {}\n    for mese_ce in range(1, 13):\n        ce = await get_conto_economico(anno=anno, mese=mese_ce)\n        ricavi_mensili_canonici[mese_ce] = float(ce["ricavi"]["totale_ricavi"] or 0)\n        costi_mensili_canonici[mese_ce] = float(ce["costi"]["totale_costi"] or 0)\n    ricavi_mensili = ricavi_mensili_canonici\n    costi_mensili = costi_mensili_canonici\n\n    # --- CONFRONTO PER VOCE ---\n    confronto_voci = []\n''')

replace_once(path,
'''        "andamento_mensile": andamento\n    }\n''',
'''        "andamento_mensile": andamento,\n        "qualita_consuntivo": {\n            "totali_fonte": "conto_economico_canonico",\n            "totali_validati": True,\n            "dettaglio_per_voce": "analisi_gestionale_per_categoria",\n            "dettaglio_per_voce_validato": False,\n            "nota": (\n                "I totali consuntivi coincidono con il Conto Economico canonico. "\n                "L'attribuzione alle singole voci di budget resta un'analisi "\n                "gestionale per categoria e non costituisce quadratura contabile."\n            ),\n        },\n    }\n''')

Path('tests/test_point11_budget_consistency.py').write_text(r'''import asyncio
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
''')
