"""Named-field AdE exports: source labels, signed arithmetic and revisions."""
import asyncio
import fitz
import pytest
from app.services.lipe_parser import parse_lipe, parse_cassetto_testuale, quadra
from app.services.declaration_field_certainty import extract_lipe_fields
from app.services.lipe_verifica import parse_lipe_modules
from app.services.lipe_deposito import deposita_lipe
from tests.fiscale.test_lipe_deposito import _Db

HEADER = 'Comunicazione iva\nFrontespizio\nCodice fiscale:00000000000;\nAnno imposta:2026;\nPartita iva:00000000000;\n'

def module(n, month, debt='3.600,00', credit='10.000,00', final='6.400,00'):
    return f'''Modulo numero: {n}
Mod.{n} - VP1 Mese:{month};
Mod.{n} - VP2 Totale operazioni attive(al netto dell'IVA):36.000,00;
Mod.{n} - VP3 Totale operazioni passive(al netto dell'IVA):10.000,00;
Mod.{n} - VP4 Iva esigibile:{debt};
Mod.{n} - VP5 Iva detratta:0,00;
Mod.{n} - VP6 Iva dovuta:{debt};
Mod.{n} - VP8 Credito periodo precedente:{credit};
Mod.{n} - VP14 IVA a credito:{final};
'''

def pdf(pages):
    doc=fitz.open()
    for text in pages:
        page=doc.new_page();page.insert_text((30,30),text,fontsize=10)
    result=doc.tobytes();doc.close();return result


def test_three_modules_across_two_pages_keep_month_source_page_and_cents():
    content=pdf([HEADER+module(1,4)+module(2,5),module(3,6)])
    parsed=parse_lipe(content)
    assert parsed['anno']=='2026'
    assert [p['periodo'] for p in parsed['periodi']]==['2026-04','2026-05','2026-06']
    assert [p['pagina'] for p in parsed['periodi']]==[1,1,2]
    assert all(p['quadratura_ok'] for p in parsed['periodi'])
    proof=extract_lipe_fields(content,document_id='d',tax_year=2026)
    assert proof['extracted_with_certainty']==3
    assert len({p['id'] for p in proof['declared_fields']})==3
    assert not proof['tax_rows'] # credit does not create F24 debt


def test_native_words_do_not_override_named_field_export():
    parsed=parse_lipe_modules(HEADER+module(1,4),layout_words=[{'text':'VP14','x0':0,'x1':5,'y0':0,'y1':5}])
    assert parsed[0]['values']['vp14_cents']==640000
    assert parsed[0]['values']['vp14_side']=='credito'
    assert parsed[0]['quadrature']=={'vp6':True,'vp14':True}


def test_description_threshold_and_acconto_method_are_not_amounts():
    text=HEADER+module(1,4,final='6.382,85').replace('Mod.1 - VP14', 'Mod.1 - VP7 Debito precedente non superiore a 25,82 euro:17,15;\nMod.1 - VP13 Metodo:3;\nMod.1 - VP14')
    period=parse_cassetto_testuale([text])['periodi'][0]
    assert period['debito_periodo_precedente']==17.15
    assert period['acconto_dovuto'] is None
    assert period['quadratura_ok']


def test_empty_layout_and_unknown_sign_do_not_certify_zero():
    assert not quadra({})
    text=HEADER+module(1,4).replace('IVA a credito','IVA saldo')
    assert not parse_cassetto_testuale([text])['periodi'][0]['quadratura_ok']


def test_conflicting_duplicate_field_and_invalid_month_are_rejected():
    for text in [HEADER+module(1,13),HEADER+module(1,4)+'Mod.1 - VP14 IVA a credito:9,00;']:
        assert not parse_cassetto_testuale([text])['periodi'][0]['quadratura_ok']


def test_unknown_filing_date_keeps_both_sources_without_arbitrary_overwrite():
    async def run():
        db=_Db();old=pdf([HEADER+module(1,4)]);new=pdf([HEADER+module(1,4,debt='3.500,00',final='6.500,00')])
        await deposita_lipe(db,old,nome_file='163990_testuale.pdf',origine='test')
        result=await deposita_lipe(db,new,nome_file='999999_testuale.pdf',origine='test')
        row=db['lipe_periodi'].docs[0]
        assert row['iva_da_versare_o_credito']==6400
        assert row['conflitto_fonti'] is True
        assert row['fonti_alternative'][0]['iva_da_versare_o_credito']==6500
        assert result['periodi_con_fonti_discordanti']==['2026-04']
        await deposita_lipe(db,new,nome_file='999999_testuale.pdf',origine='test')
        assert len(row['fonti_alternative'])==1
    asyncio.run(run())


def test_later_verified_filing_date_wins_and_replay_old_does_not_restore_it():
    async def run():
        db=_Db();old=pdf([HEADER+module(1,4)]);new=pdf([HEADER+module(1,4,debt='3.500,00',final='6.500,00')])
        await deposita_lipe(db,old,nome_file='999999_testuale.pdf',origine='test',data_presentazione='2026-05-24')
        await deposita_lipe(db,new,nome_file='111111_testuale.pdf',origine='test',data_presentazione='2026-12-07')
        row=db['lipe_periodi'].docs[0]
        assert row['iva_da_versare_o_credito']==6500
        assert row['data_presentazione']=='2026-12-07'
        assert not row['conflitto_fonti']
        await deposita_lipe(db,old,nome_file='999999_testuale.pdf',origine='test',data_presentazione='2026-05-24')
        assert row['iva_da_versare_o_credito']==6500
        assert not row['conflitto_fonti']
    asyncio.run(run())


@pytest.mark.parametrize('year,taxpayer,text', [
    ('2025', '00000000000', HEADER+module(1,4)),
    ('2026', '11111111111', HEADER+module(1,4)),
    ('2026', '00000000000', HEADER+module(1,4,final='9.999,99')),
])
def test_upload_checks_year_taxpayer_and_arithmetic_before_drive(monkeypatch,year,taxpayer,text):
    from io import BytesIO
    from fastapi import UploadFile, HTTPException
    from app.routers.documenti_fiscali import upload_documento_fiscale
    from app.config import settings
    from app.services import drive_declaration_upload
    monkeypatch.setattr(settings,'FISCAL_COMPANY_ID',taxpayer)
    def forbidden(**kwargs):
        raise AssertionError('Drive write before validation')
    monkeypatch.setattr(drive_declaration_upload,'upload_declaration',forbidden)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(upload_documento_fiscale(file=UploadFile(filename='export.pdf',file=BytesIO(pdf([text]))),
            categoria='lipe',periodo=year,note=None,data_presentazione=None,riferimento_cassetto=None,_admin={'email':'admin'}))
    assert caught.value.status_code==422


def test_filing_date_for_matching_native_source_resolves_older_amended_export():
    async def run():
        db=_Db();correct=pdf([HEADER+module(1,4)]);old=pdf([HEADER+module(1,4,debt='3.500,00',final='6.500,00')])
        await deposita_lipe(db,correct,nome_file='LIPE_2026_322737554.pdf',origine='test')
        await deposita_lipe(db,old,nome_file='old_testuale.pdf',origine='test',data_presentazione='2026-05-30')
        assert db['lipe_periodi'].docs[0]['conflitto_fonti']
        await deposita_lipe(db,correct,nome_file='correct_testuale.pdf',origine='test',data_presentazione='2027-04-06')
        row=db['lipe_periodi'].docs[0]
        assert not row['conflitto_fonti']
        assert row['protocollo']==322737554
        assert row['iva_da_versare_o_credito']==6400
    asyncio.run(run())
