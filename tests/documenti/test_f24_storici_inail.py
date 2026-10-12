from io import BytesIO
from contextlib import nullcontext
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from app.services.f24_parser import parse_quietanza_f24
from app.routers.documenti import detect_document_type
from app.services import verbali_document_import as writer


def _model(rows, balance):
    buffer=BytesIO(); c=canvas.Canvas(buffer,pagesize=A4); height=A4[1]
    def word(x,y,text,size=12):
        c.setFont('Helvetica',size); c.drawString(x,height-y,text)
    word(29,108,'CODICE FISCALE',8)
    for i,digit in enumerate('01234567890'): word(117+i*14.4,108,digit)
    word(29,560,'SEZIONE ALTRI ENTI PREVIDENZIALI ED ASSICURATIVI',8)
    word(145,578,'codice ditta',6); word(29,610,'INAIL',8)
    for index,(reference,debit,credit) in enumerate(rows):
        y=598+index*12
        for x,text in [(103,'33400'),(146,'12345678'),(212,'91'),(238,reference),(295,'P')]:word(x,y,text)
        if debit:word(360,y,debit)
        if credit:word(447,y,credit)
    word(330,696,'SALDO FINALE',8);word(548,706,balance)
    c.save();return buffer.getvalue()


def test_inail_crediti_non_diventano_debiti_e_saldo_zero_esplicito():
    model=_model([('000004',None,'250,83'),('000003',None,'215,36'),('902013','466,19',None)],'0,00')
    data=parse_quietanza_f24(pdf_content=model)
    assert data['dati_generali']['codice_fiscale']=='01234567890'
    assert data['totali']['totale_debito_cents']==46619
    assert data['totali']['totale_credito_cents']==46619
    assert data['totali']['saldo_delega_cents']==0
    assert len(data['sezione_inail'])==3
    assert not data['dati_generali'].get('data_pagamento')


def test_inail_saldo_non_zero():
    data=parse_quietanza_f24(pdf_content=_model([('902014','633,93',None)],'633,93'))
    assert data['totali']['saldo_netto_cents']==63393
    assert data['totali']['saldo_delega_cents']==63393


def test_quietanza_bollettino_non_e_f24():
    buffer=BytesIO(); c=canvas.Canvas(buffer)
    c.drawString(40,700,'Quietanza di Pagamento Numero Bollettino Importo Bollettino')
    c.save()
    assert detect_document_type('ricevuta.pdf',buffer.getvalue())=='ricevuta_bollettino_postale'


def test_testo_alternativo_recupera_spazi_persi_nel_verbale(monkeypatch):
    import pdfplumber
    from types import SimpleNamespace
    buffer=BytesIO();c=canvas.Canvas(buffer)
    c.drawString(30,700,'In data 02/07/2025 alle ore 09:10 nel Comune di Napoli')
    c.drawString(30,680,'entro 5 giorni: pagamento di Euro 121,00')
    c.save()
    broken='Indata02/07/2025alleore09:10nelComune ' + 'x'*150 + ' entro5giornipagamentodiEuro121,00'
    monkeypatch.setattr(pdfplumber,'open',lambda _:nullcontext(SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:broken)])))
    text=writer._extract_text(buffer.getvalue())
    assert writer._extract_violation_date(text)=='2025-07-02'
    assert writer._extract_amount(text)==121.00
