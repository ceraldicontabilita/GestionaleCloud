import asyncio

from app.routers.accounting import bilancio, centri_costo


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, rows): self.rows = list(rows)
    async def to_list(self, _n): return list(self.rows)


class _Collection:
    def __init__(self, rows=None): self.rows = list(rows or [])
    def find(self, *_args, **_kwargs): return _Cursor(self.rows)


class _DB(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


def test_cespiti_capitalizzati_e_ammortamenti_registrati():
    db = _DB({
        'cespiti': _Collection([
            {'id': 'c1', 'provenienza': 'fattura_xml', 'fattura_id': 'f1',
             'data_acquisto': '2026-03-10', 'valore_acquisto': 3500.0,
             'piano_ammortamento': [{'anno': 2026, 'quota': 210.0}]},
            {'id': 'c2', 'provenienza': 'fattura_xml', 'fattura_id': 'f1',
             'data_acquisto': '2026-03-10', 'valore_acquisto': 500.0,
             'piano_ammortamento': []},
        ])
    })
    per_fattura, totale = _run(bilancio._cespiti_capitalizzati_nel_periodo(
        db, '2026-01-01', '2026-12-31'))
    assert per_fattura['f1'] == 4000.0
    assert totale == 4000.0
    annuo, meta = _run(bilancio._ammortamenti_registrati_periodo(db, 2026, None))
    mensile, _ = _run(bilancio._ammortamenti_registrati_periodo(db, 2026, 3))
    assert annuo == 210.0
    assert mensile == 17.5
    assert meta['solo_quote_registrate'] is True


def test_cdc_usa_righe_xml_ed_esclude_cespite():
    invoice = {
        'id': 'f1', 'invoice_date': '2026-03-10', 'tipo_documento': 'TD01',
        'classificazioni_righe': [
            {'descrizione': 'Imballaggi carta', 'centro_costo_id': '13.1_IMBALLAGGI',
             'centro_costo_nome': 'Imballaggi e confezioni', 'imponibile': 100.0,
             'richiede_verifica': False},
            {'descrizione': 'Manutenzione locale', 'centro_costo_id': '5.4_MANUTENZIONE_LOCALI',
             'centro_costo_nome': 'Manutenzione locali', 'imponibile': 50.0,
             'richiede_verifica': False},
            {'descrizione': 'Forno industriale 6 teglie', 'centro_costo_id': '5.3_PICCOLE_ATTREZZATURE',
             'centro_costo_nome': 'Attrezzature', 'imponibile': 3500.0,
             'richiede_verifica': False},
            {'descrizione': 'Voce ignota', 'centro_costo_id': '99_ALTRI_COSTI',
             'centro_costo_nome': 'Altro', 'imponibile': 25.0,
             'richiede_verifica': True},
        ],
    }
    asset = {'fattura_id': 'f1', 'descrizione': 'Forno industriale 6 teglie',
             'valore_acquisto': 3500.0, 'provenienza': 'fattura_xml',
             'data_acquisto': '2026-03-10'}
    db = _DB({'invoices': _Collection([invoice]), 'cespiti': _Collection([asset])})
    out = _run(centri_costo._costi_cdc_da_righe_xml(db, 2026))
    assert out['costi']['CDC-04'] == 100.0
    assert out['costi']['CDC-99'] == 50.0
    assert out['cespiti_esclusi'] == 3500.0
    assert out['da_verificare'] == 25.0
    assert out['righe_da_verificare'] == 1


def test_ce_source_non_spesa_due_volte_cespiti():
    source = open('app/routers/accounting/bilancio.py', encoding='utf-8').read()
    assert 'acquisti_operativi = totale_acquisti - totale_cespiti_capitalizzati' in source
    assert 'totale_costi = costi_netti + ammortamenti_registrati' in source
    assert '"B10_ammortamenti"' in source
