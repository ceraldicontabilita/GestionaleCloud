import asyncio
import pytest
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.iva_comunicazioni import registra_comunicazione


@pytest.mark.parametrize('subject,body,sent,periodo,amount',[
 ('Iva 05.2026 - ritenuta 1040','La liquidazione iva di maggio è a debito di 3.600€, viene compensata con il credito precedente','Fri, 12 Jun 2026 12:38:00 +0200','2026-05',360000),
 ('F24 ritenuta 1040','La liquidazione iva giugno 2026 evidenzia un debito che viene compensato dal credito dei periodi precedenti','Tue, 14 Jul 2026 10:32:36 +0200','2026-06',None),
 ('IVA LUGLIO 2026','La liquidazione iva di luglio è a debito ma compensate con il credito precedente','Thu, 06 Aug 2026 20:05:20 +0200','2026-07',None),
 ('F24 RITENUTE - IVA AGOSTO','Per l’iva siete a debito ma compensate con il credito del mese precedente','Fri, 11 Sep 2026 12:00:28 +0200','2026-08',None),
 ('IVA dicembre','Debito compensato con il credito precedente','Tue, 12 Jan 2027 12:00:00 +0100','2026-12',None)])
def test_periodo_da_contenuto_no_credito_inventato_e_replay_sicuro(subject,body,sent,periodo,amount):
 async def scenario():
    db=ClientArchivioMemoria()['iva-mails']
    await db['mittenti_email'].insert_one({'pattern':'studio@example.com','attivo':True,'tipo_documento':'f24'})
    args=dict(subject=subject,body=body,sender='Studio <studio@example.com>',date_str=sent,message_id='<mail-test@example.com>',account='azienda@example.com')
    one=await registra_comunicazione(db,**args)
    assert one['periodo']==periodo
    assert await registra_comunicazione(db,**args)==one
    saved=await db['iva_comunicazioni'].find_one({'id':one['id']})
    assert saved['debito_mese_cents']==amount and saved['credito_residuo_cents'] is None
    assert await db['iva_comunicazioni'].count_documents({})==1
    assert await db['f24_unificato'].count_documents({})==0
    assert await db['pagamenti'].count_documents({})==0
    assert await registra_comunicazione(db,**{**args,'sender':'non-autorizzato@example.com'}) is None
    assert await registra_comunicazione(db,**{**args,'subject':'IVA','body':body.replace('compens','non compens')}) is None
 asyncio.run(scenario())
