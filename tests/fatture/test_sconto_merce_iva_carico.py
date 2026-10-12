import asyncio
from copy import deepcopy
from pathlib import Path
import pytest
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.services.fattura_totali import verifica_totali, rivalida_originale
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import registrazione_contabile as journal

FIXTURES = Path(__file__).parent / 'fixtures'


def parsed(name):
    return parse_fattura_xml((FIXTURES/name).read_text())


@pytest.mark.parametrize('name,discount,cost,total',[
    ('sconto_merce_1293.xml',209.65,525.18,598.66),
    ('sconto_merce_1371.xml',43.50,156.81,176.84)])
def test_iva_carico_preserva_riepilogo_e_non_sottrae_sconti_percentuali_due_volte(name,discount,cost,total):
    result = parsed(name)
    assert result['totali_coerenti'] and result['differenza_totali'] == 0
    assert result['sconto_merce'] == discount and result['imponibile_contabile'] == cost
    assert result['total_amount'] == total
    assert result['controllo_totali']['criterio'] == 'sconto_merce_iva_a_carico'


def test_arrotondamento_esplicito_non_e_tolleranza_generica():
    result = parsed('arrotondamento_riepilogo.xml')
    assert result['totali_coerenti'] and result['controllo_totali']['rettifica_arrotondamento_xml'] == .03
    result['riepilogo_iva'][0]['arrotondamento'] = '0'
    assert not verifica_totali(result)['totali_coerenti']


@pytest.mark.parametrize('mutation',['totale','riepilogo','SC_mancante','SC_negativo','righe_duplicate'])
def test_nessun_aggiustamento_senza_prova_nell_xml(mutation):
    f = parsed('sconto_merce_1371.xml')
    if mutation=='totale':f['total_amount'] += 1
    if mutation=='riepilogo':f['riepilogo_iva'][0]['imponibile'] = '199.31'
    if mutation=='SC_mancante':f['linee'][-1]['tipo_cessione_prestazione'] = ''
    if mutation=='SC_negativo':f['linee'][-1]['prezzo_totale'] = '-43.50'
    if mutation=='righe_duplicate':f['linee'][-1]['numero_linea'] = '1'
    f['imponibile_contabile'] = f['total_amount'] - f['iva'] # derivato falsificato: non e' una prova
    assert not verifica_totali(f)['totali_coerenti']


@pytest.mark.parametrize('name,cost', [('sconto_merce_1293.xml',525.18),('sconto_merce_1371.xml',156.81),('arrotondamento_riepilogo.xml',51.45)])
def test_giornale_quadrato_con_iva_originale_e_idempotenza(name,cost):
    async def scenario():
        db=ClientArchivioMemoria()['sc-journal']
        f={**parsed(name),'id':'fattura-sc','iva_detraibile':parsed(name)['iva']}
        await db['invoices'].insert_one(f)
        first=await journal.registra_fattura(db,f)
        assert first['stato']=='registrato'
        mov=first['movimento']
        assert journal.scrittura_quadrata(mov['righe'])
        assert mov['imponibile']==f['imponibile'] and mov['iva']==f['iva']
        assert mov['imponibile_contabile']==cost and mov['importo_totale']==f['total_amount']
        assert (await journal.registra_fattura(db,f))['stato']=='gia_registrato'
        assert await db['movimenti_contabili'].count_documents({})==1
    asyncio.run(scenario())


def test_rivalidazione_stesso_id_no_reimport_no_pagamento_idempotente():
    async def scenario():
        db=ClientArchivioMemoria()['repair-sc']
        name='sconto_merce_1371.xml';f={**parsed(name),'id':'sc','xml_raw':(FIXTURES/name).read_text()}
        for r in f['linee']:r.pop('tipo_cessione_prestazione',None)
        for r in f['riepilogo_iva']:r.pop('arrotondamento',None)
        f.update(totali_coerenti=False,differenza_totali=43.5,registrata_contabilita=False,
                 pagato=True,pagamenti=[{'id':'bonifico-esistente','importo':176.84}])
        await db['invoices'].insert_one(f)
        preview=await rivalida_originale(db,'sc')
        assert preview['da_aggiornare'] and not preview['aggiornata']
        assert (await db['invoices'].find_one({'id':'sc'}))['totali_coerenti'] is False
        result=await rivalida_originale(db,'sc',dry_run=False)
        assert result['aggiornata']
        assert not (await rivalida_originale(db,'sc',dry_run=False))['aggiornata']
        saved=await db['invoices'].find_one({'id':'sc'})
        assert saved['pagamenti']==f['pagamenti'] and saved['pagato'] is True
        assert saved['imponibile']==200.31 and saved['iva']==20.03 and saved['total_amount']==176.84
        assert await db['movimenti_contabili'].count_documents({})==0
        assert await db['invoices'].count_documents({})==1
    asyncio.run(scenario())
