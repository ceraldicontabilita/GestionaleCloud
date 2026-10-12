import asyncio
import base64
from email.message import EmailMessage

from mongomock_motor import AsyncMongoMockClient

from app.services import verbali_document_import as writer
from app.services.verbali_pagamento_finder import applica_pagamento_a_verbale, _genera_pdf_da_testo


def _receipt():
    msg = EmailMessage()
    msg['From'] = 'noreply-checkout@ricevute.pagopa.it'
    msg['To'] = 'ceraldigroupsrl@gmail.com'
    msg['Date'] = 'Thu, 15 May 2025 16:27:37 +0000'
    msg['Message-ID'] = '<receipt-test@provider>'
    msg['Subject'] = 'Il riepilogo del tuo pagamento'
    msg.set_content('Il tuo pagamento è andato a buon fine.\n'
        'Oggetto del pagamento /RFB/02000600006098462/34.90/TXT/Violazione CdS - '
        'TARGA: GW980EP - DATA: 05/04/2025 VERBALE N.: B99121382028- C.F.: 04523831214\n'
        'Data e ora: 15 maggio 2025, 18:27:14\nCodice avviso: 02000600006098462\n'
        'Importo: 34,90 €\nCommissione (applicata dal PSP): 1,50 €\nTotale: 36,40 €\n')
    return msg


def test_ricevuta_email_senza_pdf_originale_conservato_importo_senza_commissione(tmp_path):
    db = AsyncMongoMockClient().db
    msg = _receipt()
    async def run():
        await db.verbali_noleggio.insert_one({'id':'v1','numero_verbale':'B99121382028','importo':34.9,
            'stato':'aperto','importo_verificato':True})
        allowed = {'noreply-checkout@ricevute.pagopa.it'}
        assert await writer.conserva_ricevuta_email_pagopa(db, msg, msg.as_bytes(), 'INBOX', mittenti_ammessi=allowed)
        assert not await writer.conserva_ricevuta_email_pagopa(db, msg, msg.as_bytes(), 'Archivio', mittenti_ammessi=allowed)
        raw = await db.documents_inbox.find_one({'tipo_documento':'originale_email_pagopa'})
        assert base64.b64decode(raw['pdf_data']) == msg.as_bytes()
        copy = await db.documents_inbox.find_one({'copia_email':True})
        assert copy['originale_email_id'] == raw['id'] and copy['quietanza_ufficiale_pdf_allegata'] is False
        path = tmp_path / 'receipt.pdf'
        path.write_bytes(base64.b64decode(copy['pdf_data']))
        row = await db.verbali_noleggio.find_one({'id':'v1'})
        assert row['pagato_documentalmente'] is True and row['data_pagamento'] == '2025-05-15'
        assert row['importo'] == 34.9
        assert await db.verbali_noleggio.count_documents({}) == 1
    asyncio.run(run())


def test_receipt_non_autorizzata_e_pagamento_personale_non_importati():
    db = AsyncMongoMockClient().db
    msg = _receipt()
    async def run():
        assert not await writer.conserva_ricevuta_email_pagopa(db,msg,msg.as_bytes(),'INBOX',mittenti_ammessi=set())
        msg.set_content(msg.get_content().replace('04523831214','CF_PERSONALE'))
        assert not await writer.conserva_ricevuta_email_pagopa(db,msg,msg.as_bytes(),'INBOX',mittenti_ammessi={'noreply-checkout@ricevute.pagopa.it'})
        assert await db.documents_inbox.count_documents({}) == 0
    asyncio.run(run())


def test_consegna_pec_anche_fuori_posta_inviata_non_crea_driver_ne_pagamento():
    db = AsyncMongoMockClient().db
    msg = EmailMessage()
    msg['From'] = 'posta-certificata@pec.actalis.it'
    msg['To'] = 'ceraldigroupsrl@legalmail.it'
    msg['Date'] = 'Wed, 27 Apr 2022 09:11:03 +0200'
    msg['Message-ID'] = '<delivery-test@provider>'
    msg['Subject'] = 'CONSEGNA: comunicazione dati conducente verbale S99180043251'
    msg.set_content('Ricevuta breve di avvenuta consegna. Il messaggio proveniente da "ceraldigroupsrl@legalmail.it" '
                    'è stato consegnato nella casella di destinazione.')
    async def run():
        await db.verbali_noleggio.insert_one({'id':'v1','numero_verbale':'S99180043251','stato':'aperto'})
        assert await writer.conserva_comunicazione_inviata(db,msg,msg.as_bytes(),'Archivio',email_user='ceraldigroupsrl@gmail.com')
        assert not await writer.conserva_comunicazione_inviata(db,msg,msg.as_bytes(),'INBOX',email_user='ceraldigroupsrl@gmail.com')
        assert (await writer.associa_comunicazioni_conducente(db))['associate'] == 1
        doc = await db.documents_inbox.find_one({})
        assert doc['prova_consegna_pec'] is True and doc['firma_pec_verificata_crittograficamente'] is False
        row = await db.verbali_noleggio.find_one({})
        assert row['stato'] == 'aperto' and 'driver_id' not in row and 'pagamento_id' not in row
    asyncio.run(run())


def test_ricevuta_non_ripristina_verbale_escluso():
    db = AsyncMongoMockClient().db
    async def run():
        await db.verbali_noleggio.insert_one({'id':'v1','importo':34.9,'stato':'quarantena'})
        assert not await applica_pagamento_a_verbale(db,'v1',{'importo':34.9,'ricevuta_pagopa_id':'r1'})
        assert (await db.verbali_noleggio.find_one({'id':'v1'}))['stato'] == 'quarantena'
    asyncio.run(run())


def test_copia_pdf_conserva_numero_oltre_la_vecchia_troncatura(tmp_path):
    path = tmp_path / 'long.pdf'
    _genera_pdf_da_testo('Oggetto: ' + 'descrizione lunga ' * 15 + 'VERBALE N.: B99121382028',str(path))
    from pypdf import PdfReader
    assert 'B99121382028' in '\n'.join(p.extract_text() for p in PdfReader(path).pages)
