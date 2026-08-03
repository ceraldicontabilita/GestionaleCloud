from app.handlers.estratto_conto import _score_match
from app.services.riconciliazione_bancaria import _evidenza_forte_fattura_banca


FATTURA_LEASYS = {
    "id": "f-1",
    "total_amount": 24.40,
    "invoice_date": "2026-03-20",
    "supplier_name": "Leasys Italia S.p.A",
    "invoice_number": "0000202610458640",
}


def test_accredito_numia_stesso_importo_non_e_pagamento_leasys():
    movimento = {
        "tipo": "entrata",
        "importo": 24.40,
        "data": "2026-03-25",
        "descrizione": "NUMIA-AMEX DEL 24/03/26 PDV 3757283",
    }
    assert _score_match(movimento, FATTURA_LEASYS) == 0.0


def test_assegno_stesso_importo_senza_fornitore_o_numero_non_auto_abbina():
    movimento = {
        "tipo": "uscita",
        "importo": 646.72,
        "data": "2026-03-20",
        "descrizione": "VOSTRO ASSEGNO N. 0208770767",
    }
    fattura = {
        "total_amount": 646.72,
        "invoice_date": "2026-03-20",
        "supplier_name": "Eureka Onlus societa cooperativa sociale",
        "invoice_number": "25/D",
    }
    assert _score_match(movimento, fattura) == 0.0


def test_uscita_con_importo_e_fornitore_e_match_forte():
    movimento = {
        "tipo": "uscita",
        "importo": 24.40,
        "data": "2026-03-27",
        "descrizione": "ADDEBITO LEASYS ITALIA FATTURA 0000202610458640",
    }
    assert _score_match(movimento, FATTURA_LEASYS) >= 0.90


def test_secondo_motore_non_auto_abbina_il_solo_importo():
    evidenza = _evidenza_forte_fattura_banca(
        FATTURA_LEASYS,
        "ADDEBITO CARTA NUMIA OPERAZIONE DEL 24 MARZO",
        24.40,
    )
    assert evidenza["importo_esatto"] is True
    assert evidenza["auto_ammesso"] is False


def test_secondo_motore_accetta_importo_e_numero_fattura():
    evidenza = _evidenza_forte_fattura_banca(
        FATTURA_LEASYS,
        "PAGAMENTO FATTURA 0000202610458640",
        24.40,
    )
    assert evidenza["numero_presente"] is True
    assert evidenza["auto_ammesso"] is True


def test_rata_xml_esatta_richiede_comunque_identita():
    fattura = {
        **FATTURA_LEASYS,
        "total_amount": 120.00,
        "importo_residuo": 80.00,
        "pagamento_rate": [{"importo": 40.00}],
    }
    senza_identita = _evidenza_forte_fattura_banca(fattura, "ADDEBITO GENERICO", 40.00)
    con_identita = _evidenza_forte_fattura_banca(fattura, "BONIFICO LEASYS", 40.00)
    assert senza_identita["auto_ammesso"] is False
    assert con_identita["auto_ammesso"] is True
