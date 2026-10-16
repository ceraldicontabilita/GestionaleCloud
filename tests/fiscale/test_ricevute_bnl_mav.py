import asyncio
import fitz
import pytest
from mongomock_motor import AsyncMongoMockClient
from app.services import pagopa_receipts as m
from app.routers.documenti import detect_document_type


def content(amount='123,45',code='81010000000000001',date='28/07/2017'):
    return f'''Movimenti consolidati
Ragione Soc. TEST SRL
Importo -{amount} EUR ABI 01005 CAB 03400
Data operazione {date} Data valuta {date}
Descr. movimento BWAY-0614592485 Pag. MAV {code}
'''


def pdf(texts):
    with fitz.open() as d:
        for text in texts:
            p=d.new_page()
            p.insert_text((20,30),text,fontsize=8)
        return d.tobytes()


def test_bnl_addebito_consolidato_mav():
    data=pdf([content()])
    assert detect_document_type('ricevute.pdf',data)=='ricevuta_mav'
    r=m.parse_receipt_pdf(data)
    assert r['is_payment_receipt']
    assert r['identificativo_bolletta']=='81010000000000001'
    assert r['importo']==123.45 and r['data_pagamento']=='2017-07-28'


@pytest.mark.parametrize('change',['positivo','codice','data'])
def test_bnl_senza_prove_complete_non_registra(change):
    text=content()
    if change=='positivo':text=text.replace('Importo -','Importo ')
    if change=='codice':text=text.replace('81010000000000001','8101')
    if change=='data':text=text.replace('28/07/2017','99/99/2017')
    assert not m.parse_receipt_pdf(pdf([text]))['is_payment_receipt']


def test_bnl_ocr_senza_spazi_e_importo_prima_della_etichetta(monkeypatch):
    text = content().replace('Movimenti consolidati', 'Movimenticonsolidati')
    text = text.replace('Importo -123,45 EUR', '-123,45\nEUR\nImporto')
    text = text.replace('Data operazione', 'Dataoperazione').replace('MAV ', 'MAV')
    monkeypatch.setattr(m, '_extract_receipt_text', lambda _: (text, True))
    parsed = m.parse_receipt_pdf(pdf([text]))
    assert parsed['is_payment_receipt'] and parsed['importo'] == 123.45


def test_due_contabili_nello_stesso_pdf_restano_distinte_e_deduplicate():
    db=AsyncMongoMockClient()['bnl']
    data=pdf([content(),content('223,45','81010000000000002','30/11/2017')])
    preview=m.parse_receipt_pdf(data)
    assert len(preview['multiple_receipts'])==2 and preview['is_payment_receipt']
    async def run():
        first=await m.import_receipt(db,content=data,filename='bnl.pdf',company_id='00000000000')
        second=await m.import_receipt(db,content=data,filename='copia.pdf',company_id='00000000000')
        assert first['success'] and first['imported']==2
        assert second['success'] and second['duplicate'] and second['imported']==0
        rows=await db['ricevute_pagopa'].find({'duplicate_of':{'$exists':False}}).to_list(None)
        assert len(rows)==2
        assert sorted(r['importo'] for r in rows)==[123.45,223.45]
        assert {r['source_context']['source_page'] for r in rows}=={1,2}
        assert all(r['source_context']['original_document_id'] for r in rows)
        import base64
        originals=await db['documents_inbox'].find({'document_type':'fascicolo_contabili_bnl'}).to_list(None)
        assert len(originals)==1
        assert base64.b64decode(originals[0]['pdf_data'])==data
        assert originals[0]['fiscal_document_id']==first['original_document_id']
        version=await db['fiscal_document_versions'].find_one({'document_id':first['original_document_id']})
        assert version['page_count']==2
    asyncio.run(run())


def test_fascicolo_con_pagina_non_leggibile_non_importa_la_prima_soltanto():
    r=m.parse_receipt_pdf(pdf([content(),content().replace('81010000000000001','???')]))
    assert not r['is_payment_receipt'] and r['error']
