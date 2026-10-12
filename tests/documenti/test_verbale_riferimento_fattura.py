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


def test_fascicolo_legge_la_ricevuta_canonica_e_non_duplica_inbox():
    from app.services.verbali_pdf_service import collect_verbale_pdfs
    db=AsyncMongoMockClient().db
    async def run():
        await db.ricevute_pagopa.insert_one({'id':'r1','pdf_data':'receipt-bytes','filename':'bonifico.pdf','source_sha256':'hash1'})
        root={'id':'v1','numero_verbale':'A99111311018','ricevuta_pagopa_id':'r1'}
        files=await collect_verbale_pdfs(db,root)
        assert len(files)==1 and files[0]['content_base64']=='receipt-bytes' and files[0]['tipo']=='quietanza'
        await db.documents_inbox.insert_one({'id':'d1','verbale_id':'v1','pdf_data':'receipt-bytes','file_hash':'hash1'})
        files=await collect_verbale_pdfs(db,root)
        assert len(files)==1
        metadata=await collect_verbale_pdfs(db,root,include_content=False)
        assert 'content_base64' not in metadata[0]
    asyncio.run(run())
