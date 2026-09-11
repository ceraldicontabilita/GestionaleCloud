from pathlib import Path


def test_tax_engine_uses_canonical_pnl_and_not_gross_divided_by_110():
    source = Path('app/services/calcolo_imposte.py').read_text()
    assert 'get_conto_economico' in source
    assert 'ce["risultato"]["utile_perdita"]' in source
    assert 'totale_lordo / 1.10' not in source
    assert 'costo_personale / 25000' not in source
    assert 'deduzioni_irap = 0.0' in source


def test_tax_router_marks_result_as_management_estimate():
    source = Path('app/routers/accounting/contabilita_avanzata.py').read_text()
    assert '"tipo": "previsionale_gestionale"' in source
    assert '"base_civilistica": "conto_economico_canonico"' in source
    assert '"uso_dichiarativo": False' in source
    assert '"aliquota_irap_verificata_2026"' in source
