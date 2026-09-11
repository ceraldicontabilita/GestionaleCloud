from pathlib import Path


def test_supplier_ui_does_not_default_to_bank():
    src = Path("frontend/src/pages/Fornitori.jsx").read_text()
    assert "metodo_pagamento: ''," in src
    assert "value={canaleCanonico(form.metodo_pagamento) || ''}" in src
    assert '<option value="">Non definito</option>' in src
    assert "METODI_PAGAMENTO[key] || METODI_PAGAMENTO.banca" not in src


def test_supplier_update_accepts_explicit_undefined_method():
    src = Path("app/routers/suppliers_module/base.py").read_text()
    block = src.split('if "metodo_pagamento" in data:', 1)[1].split('if "termini_pagamento" in data:', 1)[0]
    assert 'metodo = str(data.get("metodo_pagamento") or "")' in block
    assert 'if metodo and metodo not in PAYMENT_METHODS' in block
    assert 'data["metodo_pagamento"] = metodo' in block
    assert 'metodo_configurato = bool(metodo)' in block
