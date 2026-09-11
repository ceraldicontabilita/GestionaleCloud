import asyncio

from app.routers.prima_nota_module import banca
from app.services import sumup_payout
from app.services.sheets_document_store import MemorySheetsClient
from app.services.scritture_contabili import registra_chiusura_pos_reale


def _run(coro):
    return asyncio.run(coro)


def _tx():
    return {'chiave': 'M:t1', 'transaction_id': 't1', 'tipo': 'PAYMENT', 'stato': 'SUCCESSFUL', 'data': '2026-08-06', 'importo': 100.0, 'payout_id': 'P1', 'valuta': 'EUR'}


def test_chiusura_sumup_scrive_nel_registro_sumup_non_in_banca():
    db = MemorySheetsClient()['p10_sumup_close']
    result = _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='sumup'))
    assert _run(db.prima_nota_banca.find({}).to_list(20)) == []
    rows = _run(db.prima_nota_sumup.find({}).to_list(20))
    assert len(rows) == 1 and rows[0]['source'] == 'trasferimento_pos'
    assert result['prima_nota_banca_id'] is None
    assert result['prima_nota_sumup_id'] == rows[0]['id']


def test_payout_sumup_scrive_solo_prima_nota_sumup():
    db = MemorySheetsClient()['p10_sumup_payout']
    _run(db.sumup_transactions.insert_one(_tx()))
    _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='sumup'))
    result = _run(sumup_payout.registra_payout(db, {'id': 'P1', 'amount': 98.0, 'date': '2026-08-07T05:00:00Z', 'currency': 'EUR', 'status': 'SUCCESSFUL'}))
    assert result['stato_riconciliazione'] == 'riconciliato'
    assert _run(db.prima_nota_banca.find({}).to_list(50)) == []
    rows = _run(db.prima_nota_sumup.find({}).to_list(50))
    assert {'trasferimento_pos', 'chiusura_credito_pos', 'accredito_payout', 'commissioni_sumup'} <= {r['source'] for r in rows}


def test_numia_resta_nella_prima_nota_banca_bpm():
    db = MemorySheetsClient()['p10_numia_bpm']
    result = _run(registra_chiusura_pos_reale(db, '2026-08-06', 100.0, gestore='numia'))
    rows = _run(db.prima_nota_banca.find({}).to_list(20))
    assert len(rows) == 1 and rows[0]['gestore'] == 'numia'
    assert result['prima_nota_banca_id'] == rows[0]['id']
    assert result['prima_nota_sumup_id'] is None
    assert _run(db.prima_nota_sumup.find({}).to_list(20)) == []


def test_endpoint_sumup_legge_il_registro_dedicato(monkeypatch):
    db = MemorySheetsClient()['p10_sumup_endpoint']
    _run(db.prima_nota_sumup.insert_one({'id': 'S1', 'data': '2026-08-07', 'tipo': 'entrata', 'importo': 98.0, 'source': 'accredito_payout', 'conto_contabile': '19.01.05', 'gestore': 'sumup', 'status': 'active'}))
    _run(db.prima_nota_banca.insert_one({'id': 'B1', 'data': '2026-08-07', 'tipo': 'entrata', 'importo': 999.0, 'source': 'accredito_payout', 'conto_contabile': '19.01.05', 'gestore': 'sumup', 'status': 'active'}))
    monkeypatch.setattr(banca.Database, 'get_db', staticmethod(lambda: db))
    result = _run(banca.list_prima_nota_sumup(anno=2026))
    assert result['totale_ricevuto'] == 98.0
    assert result['numero_payout'] == 1
