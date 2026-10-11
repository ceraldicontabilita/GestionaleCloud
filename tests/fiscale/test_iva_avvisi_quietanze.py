"""Avviso 9001: prova identificata, quota IVA e chiusura senza F24/banca."""
import asyncio
from copy import deepcopy
from datetime import date

import fitz
import pytest

from app.services import f24_controllo_incrociato as reg, incroci_fiscali as inc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.declaration_dossiers import attach_receipts
from app.services.f24_parser import parse_quietanza_f24
from tests.fiscale.test_comunicazioni_irregolarita import _doc54bis, TESTO_54BIS
from tests.fiscale.test_ires_iva_quietanze_dossier import dossier, field


def receipt(amount=163304, act='05354492513', cf='04523831214', id='q1', year=2024, day='2025-02-17'):
    return reg._quietanza_legacy({'id': id, 'filename': id+'.pdf', 'status': 'PAGATO_QUIETANZA',
        'dati_generali': {'codice_fiscale': cf, 'codice_atto': act, 'data_pagamento': day,
                         'protocollo_telematico': id, 'saldo_delega': amount/100},
        'saldo_delega': amount/100, 'validazione': {'saldo_quadrato': True},
        'sezione_erario': [{'codice_tributo': '9001', 'periodo_riferimento': str(year),
                            'importo_debito': amount/100, 'importo_credito': 0}]})


def test_real_june_notice_principal_and_annual_total_no_double_count():
    notice = _doc54bis()
    q = receipt()
    result = reg.riscontri_avvisi_iva([q, deepcopy(q)], [notice, {**notice, 'id': 'copy'}])
    [check], [payment] = result['avvisi'], result['pagamenti']
    assert check['stato'] == 'PAGATA'
    assert (check['imposta_cents'], check['sanzioni_cents'], check['interessi_cents']) == (146315,14632,2357)
    assert len(payment['_righe']) == 1 and payment['_righe'][0]['codice'] == '6006'
    assert payment['_righe'][0]['importo_debito_cents'] == 146315
    d = dossier('DICHIARAZIONE_IVA', '1463.00')
    d['tax_codes'] = ['6006']
    attach_receipts([d], [q], [notice])
    assert d['tax_check']['paid_cents'] == 146315
    c = d['tax_check']['comparisons'][0]
    assert c['stato'] == 'PAGATO' and c['difference_cents'] == 15
    assert c['classification_review'] is True
    assert not d['tax_check']['groups'][0]['ravvedimento']
    assert d['receipt_count'] == 1
    # Colonne 3+4: nessuna duplicazione del capitale e classificazione coerente.
    d['originals'][0]['tax_fields']['vl30_iva_periodica_versata'] = field('0.00','VL30')
    d['originals'][0]['tax_fields']['vl30_versata_comunicazioni'] = field('1463.00','VL30')
    attach_receipts([d], [q], [notice])
    assert d['tax_check']['comparisons'][0]['declared_cents'] == 146300
    assert d['tax_check']['comparisons'][0]['classification_review'] is False


@pytest.mark.parametrize('change', [dict(act='99999999999'), dict(act=None), dict(cf='99999999999'),
    dict(year=2023), dict(amount=100000), dict(amount=163305), dict(day='2024-12-01')])
def test_same_amount_or_partial_or_wrong_identity_never_closes_month(change):
    assert not reg.riscontri_avvisi_iva([receipt(**change)], [_doc54bis()])['pagamenti']


def test_conflicting_notices_missing_components_and_invalid_receipts_do_not_close():
    n = _doc54bis()
    other = deepcopy(n)
    other['id'] = 'amended'
    other['comunicazione_54bis']['periodi'][0]['imposta_da_versare'] = '1500.00'
    assert not reg.riscontri_avvisi_iva([receipt()], [n, other])['pagamenti']
    n['comunicazione_54bis']['periodi'][0]['sanzioni'] = None
    assert not reg.riscontri_avvisi_iva([receipt()], [n])['pagamenti']
    for status in ('quarantena', 'pagamento_non_eseguito', 'eliminato', 'annullato', 'stornato'):
        q = receipt(); q['status'] = status
        assert not reg.riscontri_avvisi_iva([q], [_doc54bis()])['pagamenti']


def test_installments_close_only_when_complete_and_not_before_annual_filing():
    qs = [receipt(amount=100000), receipt(amount=63304, id='q2', day='2025-05-01')]
    result = reg.riscontri_avvisi_iva(qs, [_doc54bis()])
    assert result['pagamenti'][0]['data'] == '2025-05-01'
    d = dossier('DICHIARAZIONE_IVA', '1463.00')
    attach_receipts([d], qs, [_doc54bis()])
    assert d['tax_check']['comparisons'][0]['paid_cents'] == 0
    assert d['tax_check']['paid_cents'] == 146315


def test_parser_reads_only_act_box_and_preserves_leading_zero():
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((28, 400), 'CODICE UFFICIO', fontsize=8)
    page.insert_text((115, 400), 'CODICE ATTO', fontsize=8)
    page.insert_text((310, 400), 'IDENTIFICATIVO OPERAZIONE TRIBUTI LOCALI', fontsize=8)
    for i, digit in enumerate('05354492513'):
        page.insert_text((116+i*14, 420), digit, fontsize=10)
    page.insert_text((28, 100), 'Soggetto: AZIENDA S.R.L. ( 04523831214 )')
    parsed = parse_quietanza_f24(pdf_content=doc.tobytes())
    assert parsed['dati_generali']['codice_atto'] == '05354492513'
    other = doc.new_page()
    other.insert_text((115,400), 'CODICE ATTO', fontsize=8)
    for i,digit in enumerate('99999999999'):
        other.insert_text((116+i*14,420),digit,fontsize=10)
    assert not parse_quietanza_f24(pdf_content=doc.tobytes())['dati_generali'].get('codice_atto')
    doc.close()


def test_current_sources_link_compliance_and_close_month_and_alert_idempotently():
    async def scenario():
        db = ClientArchivioMemoria()['iva_avvisi']
        n = _doc54bis(); n.update(company_id='04523831214', current_version_id='v1')
        await db['fiscal_documents'].insert_one(n)
        await db['fiscal_pages'].insert_one({'document_id': n['id'], 'version_id': 'v1', 'page_number': 1,
            'text': TESTO_54BIS+' Protocollo della dichiarazione 0000361428083 del 18-09-2024'})
        await db['fiscal_documents'].insert_one({'id':'compliance','document_type':'LETTERA_COMPLIANCE',
            'company_id':'04523831214','current_version_id':'v2','filename':'compliance.pdf'})
        await db['fiscal_pages'].insert_one({'document_id':'compliance','version_id':'v2','page_number':1,
            'text':'Codice fiscale contribuente: 04523831214 II trimestre 2024 identificativo n.361428083 del 18/09/2024'})
        await db['quietanze_f24'].insert_one(receipt()['documento'])
        await db[inc.COLL_LIPE].insert_one({'id':'june', 'periodo':'2024-06','quadratura_ok':True,
            'iva_da_versare_o_credito':1463.15,'iva_da_versare_o_credito_segno':'debito'})
        await db[inc.COLL_ALERTS].insert_one({'id':'old','codice':inc.ALERT_IVA_MENSILE,
            'entita_id':'june','stato':'aperto','extra':{'anno':2024}})
        result = await inc.incroci(db, anni=[2024], oggi=date(2026,10,11))
        assert result['confronti_iva_mensile'][0]['stato'] == 'OK'
        assert result['comunicazioni_54bis'][0]['stato'] == 'PAGATA'
        assert result['avvisi_iva_riscontro'][0]['compliance'][0]['id'] == 'compliance'
        assert not result['confronti_iva_mensile'][0]['ravvedimento_rilevato']
        assert (await inc.applica_alert(db,result,anni_completi=False))['chiusi'] == 1
        assert (await inc.applica_alert(db,result,anni_completi=False))['chiusi'] == 0
    asyncio.run(scenario())


def test_multiple_months_use_printed_principal_not_arbitrary_receipt_split():
    n = _doc54bis(); data = n['comunicazione_54bis']
    data['periodi'].append({**data['periodi'][0], 'mese':7, 'imposta_da_versare':'100.00',
                            'sanzioni':'10.00', 'interessi':'1.00', 'totale':'111.00'})
    data['importo_totale']='1744.04'
    result = reg.riscontri_avvisi_iva([receipt(amount=174404)], [n])
    assert [(r['codice'],r['importo_debito_cents']) for r in result['pagamenti'][0]['_righe']] == [('6006',146315),('6007',10000)]
    assert not reg.riscontri_avvisi_iva([receipt(amount=163304)], [n])['pagamenti']


def test_existing_receipt_is_enriched_without_replacing_amounts_or_creating_payment(monkeypatch):
    import hashlib
    from app.services import quietanze_import as qi, f24_parser
    content = b'%PDF existing receipt'
    raw = receipt(act=None)['documento']
    raw['pdf_hash'] = hashlib.sha256(content).hexdigest()
    parsed = deepcopy(raw); parsed['dati_generali']['codice_atto']='05354492513'
    monkeypatch.setattr(f24_parser, 'parse_quietanza_f24', lambda **kw: parsed)
    async def scenario():
        db = ClientArchivioMemoria()['enrich_receipt']
        await db['quietanze_f24'].insert_one(raw)
        for _ in range(2):
            r = await qi.importa_quietanza_bytes(db,content,'q.pdf')
            assert r['duplicate'] and r['quietanza_id']=='q1'
        qs = await db['quietanze_f24'].find({},{'_id':0}).to_list(100)
        assert len(qs)==1
        assert qs[0]['dati_generali']['codice_atto']=='05354492513'
        assert qs[0]['sezione_erario']==raw['sezione_erario']
        assert await db['f24_unificato'].count_documents({})==0
    asyncio.run(scenario())
