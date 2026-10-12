import asyncio
from mongomock_motor import AsyncMongoMockClient
from app.services.verbali_document_import import process_verbale_document
from app.services.verbali_pagamento_finder import _genera_pdf_da_testo


def test_originale_sostituisce_riferimento_fattura_senza_nuovo_verbale(tmp_path):
    path=tmp_path/'originale.pdf'
    _genera_pdf_da_testo("Verbale di Accertamento di Violazione alle Norme del Codice della Strada\n"
        "Verbale n. A99111311018 Registro n. 20990355546\n"
        "In data 27/07/2026 alle ore 09:48 Autoveicolo targato HB411GV\n"
        "entro 5 giorni pagamento di Euro 52,40",str(path))
    db=AsyncMongoMockClient().db
    async def run():
        await db.verbali_noleggio.insert_one({'id':'pending','numero_verbale':'20990355546',
            'numero_riferimento_fattura':'20990355546','origine':'FATTURA_SPESA_NOLEGGIO',
            'verbale_originale_acquisito':False,'fattura_id':'f1','targa':'HB411GV','stato':'fattura_ricevuta'})
        result=await process_verbale_document(db,document_id='doc1',content=path.read_bytes(),filename=path.name)
        assert result['verbale_id']=='pending'
        assert await db.verbali_noleggio.count_documents({})==1
        row=await db.verbali_noleggio.find_one({'id':'pending'})
        assert row['numero_verbale']=='A99111311018' and row['fattura_id']=='f1'
        assert row['verbale_originale_acquisito'] is True and row['importo']==52.4
        assert not row.get('pagato_documentalmente')
    asyncio.run(run())
