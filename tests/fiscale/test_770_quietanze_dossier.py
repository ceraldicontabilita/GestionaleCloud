from copy import deepcopy
from app.services.declaration_dossiers import reconcile_withholdings, attach_receipts


def declaration(rows, id='source', submission='INVIO-1'):
    return {'id':id,'declaration_identifier':submission,'filename':'770.pdf','pdf_url':'/original/'+id,'withholding_rows':rows}


def row(code='1001',month=1,amount=10000,day='2024-02-16',**kw):
    return {'rigo':'ST2','modulo':1,'sezione':'I','pagina':4,'anno':2024,'mese':month,
            'codice_tributo':code,'ritenute_operate_cents':amount,'importo_versato_cents':amount,
            'data_versamento':day,'ravvedimento':False,**kw}


def payment(code='1001',month=1,amount=10000,day='2024-02-16',id='receipt',**kw):
    return {'chiave':id,'data':day,'quietanze':[{'id':id,'pdf_url':'/quietanza/'+id}],
            '_righe':[{'sezione':'sezione_erario','codice':code,'anno':2024,'mese':month,
                       'importo_debito_cents':amount, 'importo_credito_cents':0,**kw}]}


def test_later_year_receipt_with_penalty_matches_original_code_and_period():
    source=declaration([row('1040',12,52157,'2025-03-12',ritenute_operate_cents=52000,interessi_cents=157,ravvedimento=True)])
    p=payment('1040',12,52157,'2025-03-12')
    p['_righe'].append({**p['_righe'][0],'codice':'8948','importo_debito_cents':722})
    actual=reconcile_withholdings([source],[p])['groups'][0]
    assert actual['stato']=='PAGATO_RAVVEDIMENTO'
    assert actual['quietanzato_cents']==52157 and actual['differenza_cents']==0
    assert actual['sanzioni'][0]['row']['importo_debito_cents']==722
    assert actual['payments'][0]['quietanze'][0]['id']=='receipt'
    assert actual['rows'][0]['sources'][0]['page']==4


def test_same_code_wrong_month_or_year_and_credit_do_not_pay():
    p=payment(month=2);other=payment();other['_righe'][0]['anno']=2023
    credit=payment(amount=0,importo_credito_cents=10000)
    g=reconcile_withholdings([declaration([row()])],[p,other,credit])['groups'][0]
    assert g['stato']=='QUIETANZA_MANCANTE' and g['payments']==[]


def test_copies_and_partial_pdf_same_cells_are_not_summed_but_two_rows_are():
    source=declaration([row(amount=4000),row(amount=6000,rigo='ST3')])
    copy=declaration(deepcopy(source['withholding_rows']),'copy')
    fragment=declaration([row(amount=4000,pagina=1)],'fragment')
    r=reconcile_withholdings([source,copy,fragment],[payment()])
    assert r['declared_rows']==2
    assert r['groups'][0]['dichiarato_cents']==10000
    assert r['groups'][0]['stato']=='PAGATO'


def test_separate_submissions_not_replaced_by_latest_or_summed_together():
    a=declaration([row()]);b=declaration([row('1040')],'b','INVIO-2')
    r=reconcile_withholdings([a,b],[payment(),payment('1040',id='b')])
    assert len(r['groups'])==2 and r['counts']=={'PAGATO':2}


def test_one_quietanza_cannot_confirm_two_conflicting_submissions():
    r=reconcile_withholdings([declaration([row()]),declaration([row()],'b','INVIO-2')],[payment()])
    assert r['counts']=={'DA_VERIFICARE':2}


def test_same_period_split_dates_match_individual_payments_and_partial_amount_flags():
    a=row(amount=7000);b=row(amount=3000,day='2024-03-20',rigo='ST3')
    r=reconcile_withholdings([declaration([a,b])],[payment(amount=7000),payment(amount=2500,day='2024-03-20',id='second')])
    assert r['groups'][0]['stato']=='PAGATO'
    assert r['groups'][1]['stato']=='IMPORTO_DIVERSO'
    assert r['groups'][1]['differenza_cents']==-500


def test_different_payment_date_keeps_explicit_warning_and_duplicate_candidates_ambiguous():
    d=declaration([row()]);p=payment(day='2024-02-19')
    g=reconcile_withholdings([d],[p])['groups'][0]
    assert g['stato']=='PAGATO' and g['warnings']
    g=reconcile_withholdings([d],[p,payment(day='2024-02-20',id='second')])['groups'][0]
    assert g['stato']=='DA_VERIFICARE' and not g['payments']


def test_declaration_ravvedimento_does_not_prove_payment_and_iva_penalty_does_not_apply():
    d=declaration([row(ravvedimento=True)])
    assert reconcile_withholdings([d],[])['groups'][0]['stato']=='QUIETANZA_MANCANTE'
    d=declaration([row()]);p=payment()
    p['_righe'].append({**p['_righe'][0],'codice':'8904','importo_debito_cents':100})
    g=reconcile_withholdings([d],[p])['groups'][0]
    assert g['stato']=='PAGATO' and g['sanzioni']==[]


def test_conflicting_cells_do_not_pick_a_winner_and_missing_amount_stays_unknown():
    r=reconcile_withholdings([declaration([row()]),declaration([row(amount=9000)],'different')],[payment()])
    assert r['groups'][0]['stato']=='DA_VERIFICARE'
    r=reconcile_withholdings([declaration([row(amount=None)])],[])
    assert r['groups'][0]['dichiarato_cents'] is None


def test_region_entity_cannot_use_another_region_payment():
    d=declaration([row(sezione='II',code='3802',regione='05')])
    p=payment('3802',sezione='sezione_regioni',ente='12')
    assert reconcile_withholdings([d],[p])['groups'][0]['stato']=='QUIETANZA_MANCANTE'


def test_sv_local_tax_uses_local_receipt_section():
    d=declaration([row('3848',rigo='SV2',sezione='SV')]);p=payment('3848',sezione='sezione_tributi_locali')
    assert reconcile_withholdings([d],[p])['groups'][0]['stato']=='PAGATO'


def test_tenant_filter_and_rejected_receipt_remain_active_in_full_attachment():
    ds=[{'taxpayer_id':'04523831214','tax_year':2024,'document_type':'MODELLO_770','tax_codes':['1001'],
         'quietanze':[],'originals':[declaration([row()])]}]
    raw={'id':'q','documento':{'codice_fiscale':'11111111111'},'righe':payment()['_righe'],'data':'2024-02-16','importo_cents':10000}
    attach_receipts(ds,[raw])
    assert ds[0]['withholding_check']['counts']=={'QUIETANZA_MANCANTE':1}
    raw['documento']['codice_fiscale']='04523831214';raw['status']='quarantena'
    attach_receipts(ds,[raw])
    assert ds[0]['withholding_check']['counts']=={'QUIETANZA_MANCANTE':1}


def test_addizionali_prior_income_year_require_exact_date_and_aggregate_amount():
    d=declaration([row('3802',amount=27511,sezione='II',regione='05')])
    old=payment('3802',amount=13908,anno=2023,sezione='sezione_regioni',ente='05')
    current=payment('3802',amount=13603,sezione='sezione_regioni',ente='05',id='current')
    g=reconcile_withholdings([d],[old,current])['groups'][0]
    assert g['stato']=='PAGATO' and g['quietanzato_cents']==27511
    assert {p['receipt_row']['anno'] for p in g['payments']}=={2023,2024}
    assert 'anno dei redditi' in g['warnings'][0]
    old['data']='2024-02-19'
    g=reconcile_withholdings([d],[old,current])['groups'][0]
    assert g['stato']=='IMPORTO_DIVERSO' and g['quietanzato_cents']==13603
    assert g['candidates'][0]['anni_riferimento']==[2023]


def test_1701_prior_year_recovery_needs_printed_note_p():
    p=payment('1701',anno=2023)
    g=reconcile_withholdings([declaration([row('1701',note='P')])],[p])['groups'][0]
    assert g['stato']=='PAGATO'
    g=reconcile_withholdings([declaration([row('1701')])],[p])['groups'][0]
    assert g['stato']=='QUIETANZA_MANCANTE'
    p['data']='2024-02-19'
    g=reconcile_withholdings([declaration([row('1701',note='P')])],[p])['groups'][0]
    assert g['stato']=='DA_VERIFICARE' and not g['payments']


def test_sv_aggregate_multiple_municipalities_and_prior_year_penalty():
    d=declaration([row('3848',rigo='SV2',amount=73095,ravvedimento=True)])
    p=payment('3848',amount=40796,anno=2023,sezione='sezione_tributi_locali',ente='F839')
    p['_righe'] += [{**p['_righe'][0],'ente':'B990','importo_debito_cents':32299},
                   {**p['_righe'][0],'codice':'8952','importo_debito_cents':100}]
    g=reconcile_withholdings([d],[p])['groups'][0]
    assert g['stato']=='PAGATO_RAVVEDIMENTO' and g['quietanzato_cents']==73095
    assert len(g['sanzioni'])==1


def test_zero_declared_versamento_does_not_create_missing_payment():
    g=reconcile_withholdings([declaration([row(amount=0)])],[])['groups'][0]
    assert g['stato']=='NESSUN_VERSAMENTO'


def test_legacy_fragment_without_module_does_not_duplicate_uniquely_identified_cell():
    full=declaration([row()])
    fragment=declaration([row(modulo=None,pagina=1)],id='fragment')
    r=reconcile_withholdings([fragment,full],[payment()])
    assert r['declared_rows']==1 and r['counts']=={'PAGATO':1}
    assert len(r['groups'][0]['rows'][0]['sources'])==2
