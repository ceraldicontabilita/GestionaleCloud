"""Regressioni dei layout storici: quietanza, modello e domanda restano distinti."""
import fitz
import pytest
from app.services.f24_parser import parse_quietanza_f24
from app.services.parser_f24 import parse_f24_commercialista
from app.services.dilazioni_inps import leggi_istanza, riconosci_istanza
from app.routers.documenti import detect_document_type


def pdf(words):
    with fitz.open() as doc:
        p = doc.new_page()
        for x, y, text in words:
            p.insert_text((x, y), text, fontsize=8)
        return doc.tobytes()


def test_cassetto_form_legge_righe_e_data_pagamento_non_stampa():
    data = pdf([
        (20, 20, 'Data: 27/12/2021 - Ore: 14:13:27 - Utente: 01234567890'),
        (20, 35, 'Soggetto: AZIENDA TEST SRL ( 01234567890 )'),
        (20, 65, 'MODELLO DI PAGAMENTO UNIFICATO'), (20, 90, 'DELEGA IRREVOCABILE A:'),
        (20, 320, 'SEZIONE INPS'), (100, 230, 'codice tributo'),
        (30, 352, '5100'), (80, 352, 'RC01'), (120, 352, '1234567890'),
        (220, 352, '2'), (240, 352, '2020'), (280, 352, '8'), (300, 352, '2020'),
        (350, 352, '756,00'), (465, 352, '0,00'),
        (330, 700, 'SALDO FINALE'), (530, 710, '756,00'),
        (30, 780, '1 7 0 6 2 0 2 1 05034 03406'),
    ])
    assert detect_document_type('allegato.pdf', data) == 'quietanza_f24'
    result = parse_quietanza_f24(pdf_content=data)
    assert result['dati_generali']['data_pagamento'] == '2021-06-17'
    assert result['validazione']['saldo_quadrato']
    assert result['validazione']['righe_estratte'] == 1
    assert result['sezione_inps'][0]['periodo_a'] == '08/2020'
    assert result['totali']['saldo_delega_cents'] == 75600


def test_quietanza_vuota_non_e_pagamento_zero():
    result = parse_quietanza_f24(pdf_content=pdf([(20, 50, 'Inviare la quietanza di versamento della prima rata.')]))
    assert not result['validazione']['saldo_quadrato']


@pytest.mark.parametrize('text', [
    'INPS Diffida. Versare tramite F24 entro trenta giorni.',
    'SUAP. Pagare con BONIFICO sul seguente IBAN IT1234567890.',
    'Domanda: si impegna a presentare la QUIETANZA del pagamento F24.',
])
def test_citazione_non_trasforma_lettera_in_pagamento(text):
    assert detect_document_type('lettera.pdf', pdf([(20, 50, text)])) == 'auto'


def test_domanda_dilazione_due_totali_non_e_quietanza():
    text = '''DOMANDA E ATTO DI IMPEGNO PER IL PAGAMENTO DILAZIONATO
    Protocollo domanda: INPS.5100.02/12/2020.1005936 MATRICOLA: 1234567890
    CHIEDE CHE GLI SIA CONCESSO DI REGOLARIZZARE
    Numero Inadempienza Periodo Importo contributi euro Importo sanzioni euro
    3058 02/2020 3.591,00 10,00 3059 08/2020 2.275,00 20,00
    Totale da dilazionare Totale da dilazionare Euro 5.866,00 Euro 30,00
    FINO A 24: 8'''
    assert riconosci_istanza(text)
    result = leggi_istanza(text)
    assert result['quadra'] and result['totale_richiesto_cents'] == 589600
    assert result['rate_richieste'] == 8
    assert result['periodo_da'] == '02/2020'


def test_sanzioni_locali_con_comune_non_vanno_in_erario():
    data = pdf([(30, 550, 'F839'), (170, 550, '8926'), (250, 550, '00/10'),
                (290, 550, '2017'), (350, 550, '12,30'), (470, 550, '0,00')])
    result = parse_f24_commercialista(pdf_content=data)
    assert not result['sezione_erario']
    assert result['sezione_tributi_locali'][0]['codice_tributo'] == '8926'
    assert result['totali']['totale_debito_cents'] == 1230


def semplificato(second_code='3944', second_amount='549'):
    words=[(20, 30, 'F24 SEMPLIFICATO'), (20, 50, 'CODICE FISCALE 01234567890')]
    for dy, code, amount in [(0, '3944', '549'), (410, second_code, second_amount)]:
        words += [(24, 180+dy, 'MOTIVO DEL PAGAMENTO'), (320, 180+dy, '123456789012345678'),
                  (41, 211+dy, 'E'), (52, 211+dy, 'L'), (85, 211+dy, code),
                  (122, 211+dy, 'F839'), (279, 211+dy, '0101'), (317, 211+dy, '2014'),
                  (455, 211+dy, amount), (472, 211+dy, '40'),
                  (455, 330+dy, 'EURO'), (537, 330+dy, amount), (554, 330+dy, '40')]
    return pdf(words)


def test_semplificato_copie_banca_contribuente_una_delega_non_pagata():
    result=parse_f24_commercialista(pdf_content=semplificato())
    assert result['validazione']['saldo_quadrato']
    assert len(result['modelli']) == 1
    assert result['totali']['saldo_netto_cents'] == 54940
    assert result['dati_generali'].get('data_pagamento') is None
    assert result['sezione_tributi_locali'][0]['rateazione'] == '0101'


def test_semplificato_due_deleghe_diverse_non_sono_copie():
    result=parse_f24_commercialista(pdf_content=semplificato('3945', '100'))
    assert result['validazione']['saldo_quadrato']
    assert len(result['modelli']) == 2
    assert result['totali']['saldo_netto_cents'] == 64980


def test_equitalia_storica_protocollo_e_copia_documento_con_asterisco():
    from app.services.ader_snapshot_import import riconosci, parse_rate_plan
    text = '''Equitalia Servizi di riscossione SpA
    Accoglimento dell'istanza di rateizzazione protocollo n. 396164 del 15/12/2016
    relativa ai seguenti documenti: 37120130005952092(*) EUR 100,00
    Le comunichiamo Numero rate accordato: 1
    Importo complessivo rateizzato: EUR 100,00
    Totale piano EUR 100,00'''
    data = pdf([(20, 30+n*15, line.replace('EUR', chr(183))) for n,line in enumerate(text.splitlines())])
    # La struttura storica e il protocollo bastano al routing; la quadratura
    # resta falsa se un PDF non contiene le righe effettive del piano.
    assert riconosci(' '.join(text.split()).upper()) == 'ader_piano_rateizzazione'
    result = parse_rate_plan(content=data, filename='piano.pdf',company_id='01234567890',document_numbers=[],dataset_sha256='test')
    assert result['plan_reference'] == 'EQUITALIA-396164-15122016'
    assert result['application_date'] == '2016-12-15'
    assert not result['quadratura']['rate_vs_totale_piano']
