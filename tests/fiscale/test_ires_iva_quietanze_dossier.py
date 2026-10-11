import json
from copy import deepcopy
from pathlib import Path

from app.services import dichiarazioni_quadri as dq
from app.services.declaration_dossiers import reconcile_annual_taxes, attach_receipts


def field(value, row='RN22', reason=None):
    return {'valore': value, 'rigo': row, 'colonna': 2, 'pagina': 6, 'motivo': reason}


def dossier(kind='REDDITI_SC', amount='9234.00'):
    fields = {'rn22_acconti_versati': field(amount),
              'rn23_imposta_a_debito': field(None, 'RN23', 'casella_vuota'),
              'rn24_imposta_a_credito': field('7.00', 'RN24')}
    if kind == 'DICHIARAZIONE_IVA':
        fields = {'vl30_iva_periodica_versata': field(amount, 'VL30'),
                  'vx1_da_versare': field(None, 'VX1', 'casella_vuota'),
                  'vx2_a_credito': field('7784.00', 'VX2')}
    return {'document_type':kind,'taxpayer_id':'04523831214','tax_year':2024,'tax_codes':['2001','2002','2003'],
            'quietanze':[], 'originals':[{'id':'d','filename':'Dichiarazione.pdf','pdf_url':'/original/d',
                'declaration_identifier':'INVIO-1','filed_at':'18/4/2025','parsed_type':kind,'tax_fields':fields}]}


def payment(code='2001', amount=10000, day='2024-11-05', id='q', **row):
    return {'chiave':id,'data':day,'protocollo':id,'quietanze':[{'id':id,'pdf_url':'/quietanza/'+id}],
            '_righe':[{'codice':code,'anno':2024,'sezione':'sezione_erario',
                       'importo_debito_cents':amount,'importo_credito_cents':0,**row}]}


def test_actual_columns_distinguish_acconti_saldo_and_periodic_payments():
    fixtures=json.loads((Path(__file__).parent/'fixtures/annual_tax_columns.json').read_text())
    rn=dq.estrai_quadri_pagine([fixtures['RN']], 'REDDITI_SC')['campi']
    assert rn['rn22_acconti_versati']['valore']=='9234.00'
    assert rn['rn23_imposta_a_debito']['valore'] is None
    assert rn['rn23_imposta_a_debito']['motivo']=='casella_vuota'
    assert rn['rn24_imposta_a_credito']['valore']=='7.00'
    # Cambiare il totale della seconda riga RN22 non cambia la colonna 2.
    copy=deepcopy(fixtures['RN'])
    next(w for w in copy['layout_words'] if w['text']=='9.234' and w['x0']>500)['text']='8.000'
    assert dq.estrai_quadri_pagine([copy], 'REDDITI_SC')['campi']['rn22_acconti_versati']['valore']=='9234.00'
    iva=dq.estrai_quadri_pagine([fixtures['VL']], 'DICHIARAZIONE_IVA')['campi']
    assert iva['vl30_iva_periodica_dovuta']['valore']=='6860.00'
    assert iva['vl30_iva_periodica_versata']['valore']=='6860.00'
    assert iva['vl30_versata_cartelle']['motivo']=='casella_vuota'
    assert iva['vl30_versata_comunicazioni']['motivo']=='casella_vuota'
    copy=deepcopy(fixtures['VL'])
    copy['layout_words']=[w for w in copy['layout_words'] if w['text']!='3']
    assert dq.estrai_quadri_pagine([copy], 'DICHIARAZIONE_IVA')['campi']['vl30_iva_periodica_versata']['valore'] is None


def test_real_ires_difference_two_equal_instalments_and_credit_not_payment():
    d=dossier();a=payment(amount=653500)
    a['_righe'].append({**a['_righe'][0],'importo_debito_cents':135490})
    a['_righe'].append({**a['_righe'][0],'codice':'8918','importo_debito_cents':13150})
    b=payment(amount=135490,id='second-protocol')
    r=reconcile_annual_taxes(d,[a,b,payment('2003',0,id='credit',importo_credito_cents=291600)])
    assert r['paid_cents']==924480
    assert r['comparisons'][0]['difference_cents']==1080
    assert r['comparisons'][0]['stato']=='IMPORTO_DIVERSO'
    assert len(r['groups'][0]['payments'])==3 and r['groups'][0]['ravvedimento']
    assert r['comparisons'][1]['stato']=='SALDO_A_CREDITO'
    assert r['comparisons'][1]['declared_cents'] is None
    assert len(r['credits'])==1 and len(r['accessories'])==1


def test_real_iva_reference_year_late_ravvedimento_without_f24_or_bank():
    d=dossier('DICHIARAZIONE_IVA','6860.00')
    ps=[payment(c,a,day='2024-10-16',id=c) for c,a in
        [('6002',131121),('6003',74425),('6004',204302),('6009',14928),('6010',16622)]]
    p=payment('6007',98252,'2025-02-17','late')
    p['_righe'] += [{**p['_righe'][0],'codice':c,'importo_debito_cents':a} for c,a in [('8904',4211),('1991',929)]]
    ps += [p,payment('6099',0,'2025-06-16','credit',importo_credito_cents=357400)]
    r=reconcile_annual_taxes(d,ps)
    assert r['paid_cents']==539650
    assert r['comparisons'][0]['difference_cents']==-146350
    assert r['comparisons'][1]['stato']=='SALDO_A_CREDITO'
    assert next(g for g in r['groups'] if g['codice']=='6007')['ravvedimento']
    assert len(r['accessories'])==2 and len(r['credits'])==1


def test_unknown_fields_and_unknown_date_cannot_confirm_annual_return():
    d=dossier(amount=None)
    r=reconcile_annual_taxes(d,[payment()])
    assert r['comparisons'][0]['stato']=='DA_VERIFICARE'
    d=dossier(amount='100.00');d['originals'][0]['filed_at']=None
    assert reconcile_annual_taxes(d,[payment()])['comparisons'][0]['stato']=='DA_VERIFICARE'
    assert reconcile_annual_taxes(d,[payment(day=None)])['comparisons'][0]['stato']=='DA_VERIFICARE'


def test_post_filing_receipt_stays_visible_without_backdating_declared_payments():
    d=dossier(amount='100.00');p=payment(day='2025-06-01')
    r=reconcile_annual_taxes(d,[p])
    assert r['paid_cents']==10000
    c=r['comparisons'][0]
    assert c['stato']=='QUIETANZA_MANCANTE' and not c['payments'] and c['excluded_payments']


def test_wrong_section_wrong_year_and_other_tax_penalty_never_match():
    a=payment(anno=2023);b=payment(sezione='sezione_regioni')
    c=payment();c['_righe'].append({**c['_righe'][0],'codice':'8907'})
    r=reconcile_annual_taxes(dossier(amount='100.00'),[a,b,c])
    assert r['paid_cents']==10000 and not r['accessories']
    assert not r['groups'][0]['ravvedimento']


def test_shared_ravvedimento_not_arbitrarily_assigned_to_multiple_codes():
    p=payment()
    p['_righe'] += [{**p['_righe'][0],'codice':c} for c in ['2002','8918']]
    r=reconcile_annual_taxes(dossier(),[p])
    assert not any(g['ravvedimento'] for g in r['groups'])
    assert r['accessories'][0]['principal_codes']==['2001','2002']


def test_same_submission_copies_not_summed_conflicts_visible_drafts_excluded():
    d=dossier(amount='100.00');copy=deepcopy(d['originals'][0]);copy['id']='copy'
    d['originals'].append(copy)
    draft=deepcopy(copy);draft['id']='draft';draft['declaration_identifier']=None
    d['originals'].append(draft)
    isa=deepcopy(copy);isa['id']='isa';isa['parsed_type']='ISA_ESITO';d['originals'].append(isa)
    r=reconcile_annual_taxes(d,[payment()])
    assert len(r['comparisons'])==2 and r['comparisons'][0]['declared_cents']==10000
    assert r['excluded_originals']==['draft','isa']
    copy['tax_fields']['rn22_acconti_versati']=field('200.00')
    assert reconcile_annual_taxes(d,[payment()])['comparisons'][0]['stato']=='DA_VERIFICARE'
    copy['declaration_identifier']='INVIO-2'
    r=reconcile_annual_taxes(d,[payment()])
    assert len(r['comparisons'])==4 and r['paid_cents']==10000


def test_rounding_is_explicit_and_missing_receipt_is_not_paid():
    d=dossier(amount='100.00')
    assert reconcile_annual_taxes(d,[])['comparisons'][0]['stato']=='QUIETANZA_MANCANTE'
    c=reconcile_annual_taxes(d,[payment(amount=10040)])['comparisons'][0]
    assert c['stato']=='PAGATO' and c['difference_cents']==40 and c['warnings']
    assert reconcile_annual_taxes(d,[payment(amount=10050)])['comparisons'][0]['stato']=='IMPORTO_DIVERSO'


def test_full_projection_filters_tenant_rejected_duplicates_and_zero_balance():
    d=dossier(amount='100.00')
    q={'id':'q','documento':{'codice_fiscale':'04523831214'},'righe':payment()['_righe'],
       'data':'2024-11-05','protocollo':'PROTO','importo_cents':0}
    other={**q,'documento':{'codice_fiscale':'another'},'protocollo':'OTHER'}
    rejected={**q,'protocollo':'REJECTED','status':'quarantena'}
    attach_receipts([d],[q,{**q,'id':'copy'},other,rejected])
    r=d['tax_check']
    assert r['paid_cents']==10000 and r['comparisons'][0]['stato']=='PAGATO'
    assert r['groups'][0]['payments'][0]['compensazione_totale']
