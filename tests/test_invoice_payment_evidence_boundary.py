from pathlib import Path


def test_manual_bank_payment_does_not_mark_invoice_paid():
    src = Path("app/services/invoice_payments.py").read_text()
    bank_block = src.split('else:\n                # La banca manuale e\' solo una disposizione da riscontrare.', 1)[1]
    bank_block = bank_block.split('update_fields.update({', 1)[0]
    assert '"pagato": False' in bank_block
    assert '"stato_pagamento": "da_verificare_banca"' in bank_block
    assert '"importo_pagato": min(current_paid, total)' in bank_block
    assert 'current_paid + abs(req.importo)' not in bank_block


def test_invoice_badge_uses_evidence_description():
    src = Path("frontend/src/pages/ArchivioFattureRicevute.jsx").read_text()
    block = src.split('const getStatoBadge = fattura => {', 1)[1].split('// ==================== RENDER', 1)[0]
    assert 'const pagamento = descriviPagamento(fattura)' in block
    assert 'if (fattura.pagato)' not in block
    assert 'pagamento.verified' in block
