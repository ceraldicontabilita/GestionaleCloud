import asyncio

from app.routers import pos_corrispettivi_check as pos
from app.services import sumup_payout
from app.services.paypal_reconciliation_links import finalizza_transazione_paypal_se_completa
from app.services.sheets_document_store import MemorySheetsClient
from app.services.scritture_contabili import registra_chiusura_pos_reale


def _run(coro):
    return asyncio.run(coro)


def test_numia_richiede_causale_bancaria_reale_con_giorno_operazione():
    assert pos._e_accredito_pos_numia_con_giorno(
        'INC.POS CARTE CREDIT - NUMIA-INTER DEL 06/07/26 PDV 123/01'
    )
    assert not pos._e_accredito_pos_numia_con_giorno('ACCREDITO NUMIA POS')
    assert not pos._e_accredito_pos_numia_con_giorno('COMMISSIONI NUMIA DEL 06/07/26')


def test_sumup_payout_provider_non_si_dichiara_accredito_bancario():
    db = MemorySheetsClient()['point10_sumup_provider_evidence']
    _run(db.sumup_transactions.insert_one({
        'chiave': 'M:t1', 'transaction_id': 't1', 'tipo': 'PAYMENT',
        'stato': 'SUCCESSFUL', 'data': '2026-08-06', 'importo': 100.0,
        'payout_id': 'P1', 'valuta': 'EUR',
    }))
    _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='sumup'))
    result = _run(sumup_payout.registra_payout(db, {
        'id': 'P1', 'amount': 98.0, 'date': '2026-08-07T05:00:00Z',
        'currency': 'EUR', 'status': 'SUCCESSFUL',
    }))
    assert result['stato_riconciliazione'] == 'riconciliato'
    payout = _run(db.sumup_payouts.find_one({'payout_id': 'P1'}))
    assert payout['evidenza_provider'] == 'sumup_payout_api'
    assert payout['accredito_banca_verificato'] is False
    assert payout['movimento_bancario_id'] is None
    accredito = _run(db.prima_nota_sumup.find_one({'source': 'accredito_payout'}))
    assert accredito['evidenza_provider'] == 'sumup_payout_api'
    assert accredito['accredito_banca_verificato'] is False
    assert accredito['movimento_bancario_id'] is None


def test_paypal_transazione_e_fattura_non_bastano_senza_estratto_conto():
    db = MemorySheetsClient()['point10_paypal_bank_gate']
    _run(db.paypal_transactions.insert_one({
        'transaction_id': 'PAY-1', 'importo': -100.0,
        'fattura_associata': {'fattura_id': 'INV-1'},
    }))
    _run(db.invoices.insert_one({'id': 'INV-1', 'total_amount': 100.0, 'pagato': False}))
    result = _run(finalizza_transazione_paypal_se_completa(db, 'PAY-1'))
    assert result == {'finalizzata': False, 'motivo': 'estratto_conto_non_collegato'}
    invoice = _run(db.invoices.find_one({'id': 'INV-1'}))
    assert invoice.get('pagato') is not True


def test_chiusura_pos_manual_only_non_e_prova_bancaria():
    db = MemorySheetsClient()['point10_manual_pos_not_bank']
    _run(db.chiusure_pos_manuali.insert_one({
        'data': '2026-07-05', 'importo': 1000.0,
        'source': 'inserimento_manuale_terminale',
    }))
    out = _run(pos._carica_accrediti_banca_pos(db, '2026-07-01', '2026-07-31'))
    assert out == {}
