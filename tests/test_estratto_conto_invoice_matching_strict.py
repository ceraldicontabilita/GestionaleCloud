from app.handlers.estratto_conto import _score_match


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
