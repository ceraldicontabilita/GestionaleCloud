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


def test_secondo_motore_non_accetta_numero_senza_fornitore():
    evidenza = _evidenza_forte_fattura_banca(
        FATTURA_LEASYS,
        "PAGAMENTO FATTURA 0000202610458640",
        24.40,
    )
    assert evidenza["numero_presente"] is True
    assert evidenza["auto_ammesso"] is False


def test_secondo_motore_accetta_importo_numero_e_fornitore():
    evidenza = _evidenza_forte_fattura_banca(
        FATTURA_LEASYS,
        "PAGAMENTO LEASYS ITALIA FATTURA 0000202610458640",
        24.40,
    )
    assert evidenza["numero_presente"] is True
    assert evidenza["fornitore_presente"] is True
    assert evidenza["auto_ammesso"] is True


def test_rata_xml_esatta_richiede_comunque_identita():
    fattura = {
        **FATTURA_LEASYS,
        "total_amount": 120.00,
        "importo_residuo": 80.00,
        "pagamento_rate": [{"importo": 40.00}],
    }
    senza_identita = _evidenza_forte_fattura_banca(fattura, "ADDEBITO GENERICO", 40.00)
    con_identita = _evidenza_forte_fattura_banca(
        fattura, "BONIFICO LEASYS FATTURA 0000202610458640", 40.00
    )
    assert senza_identita["auto_ammesso"] is False
    assert con_identita["auto_ammesso"] is True


def test_stesso_importo_non_scambia_timas_con_carta_party():
    timas = {
        "total_amount": 153.72,
        "supplier_name": "TIMAS ASCENSORI S.R.L.",
        "invoice_number": "386",
    }
    carta_party = {
        "total_amount": 153.72,
        "supplier_name": "CARTA & PARTY SNC DI COSITORE GIOVANNI",
        "invoice_number": "56",
    }
    causale = "BONIFICO TIMAS ASCENSORI PAGAMENTO FATTURA 386"
    assert _evidenza_forte_fattura_banca(timas, causale, 153.72)["auto_ammesso"] is True
    assert _evidenza_forte_fattura_banca(carta_party, causale, 153.72)["auto_ammesso"] is False


def test_numero_di_carta_party_con_nome_timas_e_conflitto_non_auto_associa():
    timas = {
        "total_amount": 153.72,
        "supplier_name": "TIMAS ASCENSORI S.R.L.",
        "invoice_number": "386",
    }
    carta_party = {
        "total_amount": 153.72,
        "supplier_name": "CARTA & PARTY SNC DI COSITORE GIOVANNI",
        "invoice_number": "56",
    }
    causale = "BONIFICO TIMAS ASCENSORI PAGAMENTO FATTURA 56"
    assert _evidenza_forte_fattura_banca(timas, causale, 153.72)["auto_ammesso"] is False
    assert _evidenza_forte_fattura_banca(carta_party, causale, 153.72)["auto_ammesso"] is False
