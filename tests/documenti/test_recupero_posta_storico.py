import asyncio
from email.message import EmailMessage

from mongomock_motor import AsyncMongoMockClient

from app.services import email_full_download as efd
from app.services import verbali_document_import as writer
from tests.documenti.test_posta_cursori import FintaCasella, _collega


def test_recupero_2003_cursore_separato_riprende_senza_saltare_errore(monkeypatch):
    db = AsyncMongoMockClient().db
    box = FintaCasella({'INBOX': {1: True, 2: True, 3: True}})
    calls = []
    _collega(monkeypatch, box, calls)
    original = box.uid
    searches = []
    fail = [True]

    def uid(command, *args):
        if command == 'SEARCH':
            searches.append(args[-1])
        if command == 'FETCH' and args[0] == '2' and fail[0]:
            return 'NO', []
        return original(command, *args)
    box.uid = uid

    async def run():
        await db.sistema_stato.insert_one({'chiave': efd.CHIAVE_CURSORI_POSTA, 'cartelle': {'unchanged': {'alto': 99}}})
        first = await efd.scarica_posta_con_cursori(db, data_inizio='2003-01-01', stato_chiave=efd.CHIAVE_RECUPERO_STORICO, solo_storico=True)
        assert first['errori'] == 1 and not first['storico_completo']
        saved = await db.sistema_stato.find_one({'chiave': efd.CHIAVE_RECUPERO_STORICO})
        assert saved['cartelle']['INBOX']['basso'] == 3
        fail[0] = False
        second = await efd.scarica_posta_con_cursori(db, data_inizio='2003-01-01', stato_chiave=efd.CHIAVE_RECUPERO_STORICO, solo_storico=True)
        assert second['storico_completo']
        normal = await db.sistema_stato.find_one({'chiave': efd.CHIAVE_CURSORI_POSTA})
        assert normal['cartelle'] == {'unchanged': {'alto': 99}}
    asyncio.run(run())
    assert calls == [('INBOX', 3), ('INBOX', 2), ('INBOX', 1)]
    assert 'UID 1:3 SINCE 01-Jan-2003' in searches


def test_comunicazione_originale_idempotente_senza_consegna_ne_pagamento():
    db = AsyncMongoMockClient().db
    msg = EmailMessage()
    msg['From'] = 'ceraldigroupsrl@gmail.com'
    msg['To'] = 'polizia@example.it'
    msg['Subject'] = 'Comunicazione dati conducente verbale n. A26111311018'
    msg['Date'] = 'Fri, 9 Oct 2026 12:00:00 +0200'
    msg['Message-ID'] = '<originale@company>'
    msg.set_content('Trasmettiamo i dati del conducente per il verbale A26111311018.')

    async def run():
        await db.verbali_noleggio.insert_one({'id': 'v1', 'numero_verbale': 'A26111311018', 'stato': 'aperto'})
        assert not await writer.conserva_comunicazione_inviata(db, msg, msg.as_bytes(), 'INBOX', email_user='ceraldigroupsrl@gmail.com')
        assert await writer.conserva_comunicazione_inviata(db, msg, msg.as_bytes(), '[Gmail]/Sent Mail', email_user='ceraldigroupsrl@gmail.com')
        assert not await writer.conserva_comunicazione_inviata(db, msg, msg.as_bytes(), '[Gmail]/Sent Mail', email_user='ceraldigroupsrl@gmail.com')
        result = await writer.associa_comunicazioni_conducente(db)
        assert result['associate'] == 1
        doc = await db.documents_inbox.find_one({})
        assert doc['comunicazione_stato'] == 'inviata_da_casella'
        assert doc['prova_consegna_pec'] is False and doc['email_message_id'] == '<originale@company>'
        v = await db.verbali_noleggio.find_one({})
        assert v['comunicazioni_conducente_ids'] == [doc['id']]
        assert v['stato'] == 'aperto' and 'driver_id' not in v and 'pagato' not in v
    asyncio.run(run())


def test_modulo_conducente_non_crea_verbale_e_non_prova_invio(monkeypatch):
    db = AsyncMongoMockClient().db
    monkeypatch.setattr(writer, '_extract_text', lambda _: 'Comunicazione dati del conducente. Verbale n. A26111311018')
    from app.services import pagopa_receipts
    monkeypatch.setattr(pagopa_receipts, 'parse_receipt_pdf', lambda *a, **kw: {})

    async def run():
        await db.documents_inbox.insert_one({'id': 'form'})
        result = await writer.process_verbale_document(db, document_id='form', content=b'form', filename='modulo.pdf')
        assert result['status'] == 'comunicazione_da_verificare'
        assert await db.verbali_noleggio.count_documents({}) == 0
        doc = await db.documents_inbox.find_one({'id': 'form'})
        assert doc['comunicazione_stato'] == 'documento_presente_invio_non_provato'
    asyncio.run(run())


def test_originale_personale_escluso_senza_cancellare_e_preruolo_non_duplicato(monkeypatch):
    db = AsyncMongoMockClient().db
    from app.services import pagopa_receipts
    monkeypatch.setattr(pagopa_receipts, 'parse_receipt_pdf', lambda *a, **kw: {})
    monkeypatch.setattr(writer, '_extract_text', lambda b: b.decode())

    async def run():
        await db.verbali_noleggio.insert_one({'id': 'personale', 'source_document_id': 'p1', 'stato': 'aperto'})
        excluded = await writer.process_verbale_document(db, document_id='p1', content=b'Verbale n. A22110899760 CERALDI ANTONIETTA CERALDIANTONIETTA@LEGALMAIL.IT', filename='originale.pdf')
        assert excluded['status'] == 'escluso_verbali_aziendali'
        assert (await db.verbali_noleggio.find_one({'id': 'personale'}))['stato'] == 'quarantena'
        await db.verbali_noleggio.insert_one({'id': 'azienda', 'numero_verbale': '20210355244', 'source_document_id': 's1', 'stato': 'salvato'})
        corrected = await writer.process_verbale_document(db, document_id='s1', content=b'AVVISO DI PAGAMENTO CERALDI GROUP SRL Verbale 20210355244 - BB19140301282', filename='preruolo.pdf')
        assert corrected['verbale_id'] == 'azienda'
        assert (await db.verbali_noleggio.find_one({'id': 'azienda'}))['numero_verbale'] == 'BB19140301282'
        assert await db.verbali_noleggio.count_documents({}) == 2
    asyncio.run(run())
