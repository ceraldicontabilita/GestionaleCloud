"""Regressioni dai formati reali, con identificativi sintetici."""
import asyncio
import hashlib
import pytest
from app.services import pagopa_receipts as m
from app.services import cartelle_pagamento as cp
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

EMAIL = '''Il team di pagoPA
Il tuo pagamento è andato a buon fine.
Data e ora: 19 giugno 2025, 19:59:56
Ente creditore: Comune di Prova
Codice Fiscale ente: 00000000000
Codice Avviso: 02000600000000001
falseImporto: 57,05
falseCommissione (applicata da Nexi): 1,50 €
Totale: 58,55 €
VERBALE N.: A25000000001
'''

def parse(monkeypatch, text):
    monkeypatch.setattr(m, '_extract_receipt_text', lambda _: (text, False))
    return m.parse_receipt_pdf(b'%PDF-test')

@pytest.mark.parametrize('colon', [':', ''])
def test_email_senza_commissioni_nel_verbale(monkeypatch, colon):
    r = parse(monkeypatch, EMAIL.replace('Codice Avviso:', 'Codice Avviso'+colon))
    assert r['is_payment_receipt']
    assert (r['importo'], r['fee_amount'], r['bank_debit_total']) == (57.05, 1.5, 58.55)
    assert (r['operation_amount_cents'], r['fee_amount_cents'], r['bank_debit_total_cents']) == (5705,150,5855)
    assert r['data_pagamento'] == '2025-06-19'
    assert r['beneficiario'] == 'Comune di Prova'

@pytest.mark.parametrize('change', ['bad_sum', 'negative'])
def test_non_accetta_email_non_quadrata_o_esito_negativo(monkeypatch, change):
    text = EMAIL.replace('58,55', '68,55') if change == 'bad_sum' else EMAIL+'\nESITO: Pagamento non eseguito'
    assert not parse(monkeypatch,text)['is_payment_receipt']

def test_vecchia_email_iuv_a_capo(monkeypatch):
    r=parse(monkeypatch, '''Hai inviato un pagamento di 48,44 € tramite pagoPA
Data e ora
20 dicembre 2022, 12:37:24
Debitore Beneficiario IUV Importo
AZIENDA DI PROVA
800710500000001
40
46,94 €
Totale
48,44 €
''')
    assert r['is_payment_receipt']
    assert r['identificativo_bolletta']=='80071050000000140'
    assert r['importo']==46.94 and r['fee_amount']==1.5

ADER='''Ricevuta di pagamento
Intestata a:
Codice ﬁscale:
Data/ora:
Transazione numero:
Agente della Riscossione:
Cod. Fisc. Agente Risc.:
IdenƟﬁcaƟvo PSP:
ID Univoco Riscossione:
AZIENDA TEST 00000000000
20/10/2022 13:33:21
202200000000000001
Agenzia delle entrate-Riscossione 13756881002
TESTITMM - Banca Prova
12345678900000000001
DeƩaglio transazione
IUV¹:
80071050000000001
Importo originario:
Cartella/Avviso n.:
€
144,48
37120220000000001000
Ente creditore:
Importo tribuƟ:
Interessi di mora:
INPS
€ 144,17 €
0,31
Totale Cartella/Avviso:
€
144,48
Transazione eseguita
Il pagamento e' stato registrato correƩamente.
'''

def test_ader_etichette_prima_dei_valori(monkeypatch):
    r=parse(monkeypatch,ADER)
    assert r['is_payment_receipt']
    assert r['data_pagamento']=='2022-10-20'
    doc=r['documenti'][0]
    assert doc['numero']=='37120220000000001000'
    assert doc['importo_tributi']==144.17 and doc['interessi_mora']==.31


def test_rilettura_aggancia_verbale_arrivato_dopo_senza_duplicare(monkeypatch):
    db=ClientArchivioMemoria()['rilettura']
    parse(monkeypatch,EMAIL)
    async def scenario():
        first=await m.import_receipt(db,content=b'%PDF-test',filename='r.pdf',company_id='c')
        await db['verbali_noleggio'].insert_one({'id':'v1','numero_verbale':'A25000000001','importo':57.05})
        again=await m.import_receipt(db,content=b'%PDF-test',filename='r.pdf',company_id='c')
        assert first['success'] and again['duplicate']
        assert again['riconciliazione_verbale']['matched']
        assert await db['ricevute_pagopa'].count_documents({})==1
        v=await db['verbali_noleggio'].find_one({'id':'v1'})
        assert v['stato']=='pagato' and v['importo_pagato']==57.05
        assert not v['banca_verificata']
    asyncio.run(scenario())


def test_ridotto_documentato_e_scadenza_provata():
    v={'importo':47.5,'importo_ridotto':34.9}
    assert m.importo_ricevuta_compatibile(v,{},34.9)
    v.update(data_notifica_fonte='pec',data_notifica='2025-06-01')
    assert m.importo_ricevuta_compatibile(v,{'data_pagamento':'2025-06-05'},34.9)
    assert not m.importo_ricevuta_compatibile(v,{'data_pagamento':'2025-06-10'},34.9)
    assert not m.importo_ricevuta_compatibile(v,{},36.4)


def test_quote_documentate_su_due_cartelle_e_parziale_non_chiude():
    db=ClientArchivioMemoria()['quote']
    async def scenario():
        for n,total in [('001',100),('002',200)]:
            await db[cp.COLL].insert_one({'id':'cartella:'+n,'totale':str(total)})
        r={'id':'receipt','identificativo_bolletta':'80071050000000001','data_pagamento':'2025-06-19',
           'importo':150,'importi_quadrano':True,'documenti':[
            {'numero':'001','totale':100,'quadra':True}, {'numero':'002','totale':50,'quadra':True}]}
        await db['ricevute_pagopa'].insert_one(r)
        await cp.chiudi_da_ricevuta(db,r)
        await cp.chiudi_da_ricevuta(db,r)
        one=await db[cp.COLL].find_one({'id':'cartella:001'})
        two=await db[cp.COLL].find_one({'id':'cartella:002'})
        assert one['expectation_status']=='SODDISFATTO'
        assert two['expectation_status']=='DA_VERIFICARE'
        assert two['importo_pagato_documentale']=='50'
        assert len(two['pagamenti_documentati'])==1
    asyncio.run(scenario())


def test_copie_legacy_un_pagamento_originali_conservati():
    db=ClientArchivioMemoria()['copies']
    async def scenario():
        for ident in ['a','b']:
            await db['ricevute_pagopa'].insert_one({'id':ident,'iuv':'02000600000000001',
                'importo':57.05,'data_pagamento':'2025-06-19','pdf_data':ident})
        r=await db['ricevute_pagopa'].find_one({'id':'b'})
        canonical=await m.consolida_copie_ricevuta(db,r)
        assert canonical['id']=='a'
        assert await db['ricevute_pagopa'].count_documents({'duplicate_of':{'$exists':False}})==1
        assert (await db['ricevute_pagopa'].find_one({'id':'b'}))['pdf_data']=='b'
    asyncio.run(scenario())


def test_aggancio_avviso_per_iuv_non_per_solo_importo():
    db=ClientArchivioMemoria()['avvisi']
    async def scenario():
        for ident,code in [('right','02000600000000001'),('wrong','02000600000000002')]:
            await db['documents_inbox'].insert_one({'id':ident,'category':'avviso_pagopa',
                'parsed_metadata':{'identificativo_bolletta':code,'importo':57.05}})
        receipt={'id':'r','identificativo_bolletta':'02000600000000001','importo':57.05,'data_pagamento':'2025-06-19'}
        await db['ricevute_pagopa'].insert_one(receipt)
        assert await m.associa_avvisi_a_ricevuta(db,receipt)==['right']
        assert (await db['documents_inbox'].find_one({'id':'right'}))['obligation_status']=='PAGATO_DOCUMENTALE'
        assert not (await db['documents_inbox'].find_one({'id':'wrong'})).get('ricevuta_pagopa_id')
    asyncio.run(scenario())


def test_copia_senza_commissione_non_perde_addebito_documentato(monkeypatch):
    db=ClientArchivioMemoria()['commissioni']
    parsed=parse(monkeypatch,EMAIL)
    async def scenario():
        await m.import_receipt(db,content=b'%PDF-test',filename='email.pdf',company_id='c')
        without_fee={**parsed,'fee_amount':None,'fee_amount_cents':None,'bank_debit_total':57.05,'bank_debit_total_cents':5705}
        monkeypatch.setattr(m,'parse_receipt_pdf',lambda content: without_fee)
        result=await m.import_receipt(db,content=b'%PDF-portal',filename='portale.pdf',company_id='c')
        r=result['receipt']
        assert r['fee_amount']==1.5 and r['bank_debit_total']==58.55
        assert await db['documents_inbox'].count_documents({'sha256':hashlib.sha256(b'%PDF-portal').hexdigest()})==1
    asyncio.run(scenario())
