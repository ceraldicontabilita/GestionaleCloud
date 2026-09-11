from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'marker not found in {path}: {old[:160]}')
    p.write_text(text.replace(old, new, 1))

# --- Bilancio: include Mastercard SumUp as separate real liquidity account ---
path = 'app/routers/accounting/bilancio.py'
replace_once(path,
'''COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"\nCOLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"\n''',
'''COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"\nCOLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"\nCOLLECTION_PRIMA_NOTA_SUMUP = "prima_nota_sumup"\n''')
replace_once(path,
'''    query_banca = filtro_saldo_prima_nota(COLLECTION_PRIMA_NOTA_BANCA, data=intervallo)\n    saldi_cassa = await aggrega_saldo_prima_nota(\n        db, COLLECTION_PRIMA_NOTA_CASSA, query_cassa, anno)\n    saldo_cassa = saldi_cassa["saldo"]\n    saldi_banca = await aggrega_saldo_prima_nota(\n        db, COLLECTION_PRIMA_NOTA_BANCA, query_banca, anno)\n    saldo_banca = saldi_banca["saldo"]\n''',
'''    query_banca = filtro_saldo_prima_nota(COLLECTION_PRIMA_NOTA_BANCA, data=intervallo)\n    query_sumup = filtro_saldo_prima_nota(COLLECTION_PRIMA_NOTA_SUMUP, data=intervallo)\n    saldi_cassa = await aggrega_saldo_prima_nota(\n        db, COLLECTION_PRIMA_NOTA_CASSA, query_cassa, anno)\n    saldo_cassa = saldi_cassa["saldo"]\n    saldi_banca = await aggrega_saldo_prima_nota(\n        db, COLLECTION_PRIMA_NOTA_BANCA, query_banca, anno)\n    saldo_banca = saldi_banca["saldo"]\n    saldi_sumup = await aggrega_saldo_prima_nota(\n        db, COLLECTION_PRIMA_NOTA_SUMUP, query_sumup, anno)\n    saldo_sumup = saldi_sumup["saldo"]\n''')
replace_once(path,
'''    totale_attivo = saldo_cassa + saldo_banca + totale_crediti + totale_immobilizzazioni\n''',
'''    totale_attivo = saldo_cassa + saldo_banca + saldo_sumup + totale_crediti + totale_immobilizzazioni\n''')
replace_once(path,
'''                "cassa": round(saldo_cassa, 2),\n                "banca": round(saldo_banca, 2),\n                "totale": round(saldo_cassa + saldo_banca, 2)\n''',
'''                "cassa": round(saldo_cassa, 2),\n                "banca": round(saldo_banca, 2),\n                "sumup_mastercard": round(saldo_sumup, 2),\n                "totale": round(saldo_cassa + saldo_banca + saldo_sumup, 2)\n''')
replace_once(path,
'''        ['Banca', fmt_eur(sp['attivo']['disponibilita_liquide']['banca']),\n         'Fondo TFR', fmt_eur(sp['passivo']['fondo_tfr'])],\n        ['Crediti vs Clienti', fmt_eur(sp['attivo']['crediti']['totale']),\n''',
'''        ['Banca BPM', fmt_eur(sp['attivo']['disponibilita_liquide']['banca']),\n         'Fondo TFR', fmt_eur(sp['passivo']['fondo_tfr'])],\n        ['Mastercard SumUp', fmt_eur(sp['attivo']['disponibilita_liquide']['sumup_mastercard']), '', ''],\n        ['Crediti vs Clienti', fmt_eur(sp['attivo']['crediti']['totale']),\n''')
replace_once(path,
'''            "banca": calc_variazione(\n                sp_corrente["attivo"]["disponibilita_liquide"]["banca"],\n                sp_precedente["attivo"]["disponibilita_liquide"]["banca"]\n            ),\n            "crediti": calc_variazione(\n''',
'''            "banca": calc_variazione(\n                sp_corrente["attivo"]["disponibilita_liquide"]["banca"],\n                sp_precedente["attivo"]["disponibilita_liquide"]["banca"]\n            ),\n            "sumup_mastercard": calc_variazione(\n                sp_corrente["attivo"]["disponibilita_liquide"].get("sumup_mastercard", 0),\n                sp_precedente["attivo"]["disponibilita_liquide"].get("sumup_mastercard", 0)\n            ),\n            "crediti": calc_variazione(\n''')

# --- Utile obiettivo: reuse canonical Conto Economico, no parallel gross calculation ---
path = 'app/routers/accounting/centri_costo.py'
replace_once(path,
'''    # Calcola dati reali\n    date_start = f"{anno}-01-01"\n    date_end = f"{anno}-12-31"\n    \n    # Ricavi da corrispettivi\n    ricavi_pipeline = [\n        {"$match": {"data": {"$gte": date_start, "$lte": date_end}}},\n        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}\n    ]\n    ricavi_result = await db[Collections.CORRISPETTIVI].aggregate(ricavi_pipeline).to_list(1)\n    ricavi_totali = ricavi_result[0]["totale"] if ricavi_result else 0\n    \n    # Costi da fatture\n    costi_pipeline = [\n        {"$match": {"invoice_date": {"$gte": date_start, "$lte": date_end}}},\n        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}\n    ]\n    costi_result = await db[Collections.INVOICES].aggregate(costi_pipeline).to_list(1)\n    costi_totali = costi_result[0]["totale"] if costi_result else 0\n''',
'''    # Calcola dati reali usando lo stesso Conto Economico canonico della pagina\n    # Bilancio: ricavi imponibili da corrispettivi, costi imponibili al netto\n    # delle note di credito e dei documenti eliminati/archiviati.\n    from app.routers.accounting.bilancio import get_conto_economico\n    conto_economico = await get_conto_economico(anno=anno, mese=None)\n    ricavi_totali = conto_economico["ricavi"]["totale_ricavi"]\n    costi_totali = conto_economico["costi"]["totale_costi"]\n''')
replace_once(path,
'''        # 3. Default: costi generali\n        if not cdc:\n            cdc = "CDC-99"\n        \n        # Aggiorna fattura\n        await db[Collections.INVOICES].update_one(\n            {"_id": fatt["_id"]},\n            {"$set": {"centro_costo": cdc, "cdc_auto_assigned": True}}\n        )\n        updated += 1\n        stats[cdc] = stats.get(cdc, 0) + 1\n''',
'''        # 3. Nessun fallback inventato: se categoria e fornitore non\n        # identificano un centro in modo esplicito, la fattura resta da\n        # verificare invece di essere forzata in CDC-99.\n        if not cdc:\n            await db[Collections.INVOICES].update_one(\n                {"_id": fatt["_id"]},\n                {"$set": {\n                    "cdc_auto_assigned": False,\n                    "cdc_requires_review": True,\n                }, "$unset": {"centro_costo": ""}}\n            )\n            stats["DA_VERIFICARE"] = stats.get("DA_VERIFICARE", 0) + 1\n            continue\n\n        # Aggiorna fattura soltanto quando il mapping è deterministico.\n        await db[Collections.INVOICES].update_one(\n            {"_id": fatt["_id"]},\n            {"$set": {\n                "centro_costo": cdc,\n                "cdc_auto_assigned": True,\n                "cdc_requires_review": False,\n            }}\n        )\n        updated += 1\n        stats[cdc] = stats.get(cdc, 0) + 1\n''')

# --- Regression tests ---
Path('tests/test_point11_accounting_governance.py').write_text(r'''import asyncio
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
''')
