from app.parsers.estratto_conto_bpm_parser import parse_bpm_text


def test_parser_bpm_conserva_segno_beneficiario_e_pos():
    text = """
    DATA CONTABILE
    25/03/26
    25/03/26
    NUMIA-AMEX DEL 24/03/26 PDV 3757283/00011
    24,40
    25/03/26
    CERALDI CAFFE NA
    27/03/26
    27/03/26
    VS.DISP. RIF. MBVT0001/0001 FAVORE
    - 267,02
    27/03/26
    TOP SPINA S.R.L. UNIPERSONALE NOTPROVIDE 000000000001855/01
    """
    rows = parse_bpm_text(text)
    assert len(rows) == 2
    assert rows[0]["tipo"] == "entrata"
    assert rows[0]["importo"] == 24.40
    assert "NUMIA-AMEX" in rows[0]["descrizione"]
    assert rows[1]["tipo"] == "uscita"
    assert rows[1]["importo"] == -267.02
    assert "TOP SPINA" in rows[1]["descrizione"]
    assert "000000000001855/01" in rows[1]["descrizione"]


def test_parser_bpm_assegno_non_inventa_beneficiario():
    text = """
    20/03/26
    20/03/26
    VOSTRO ASSEGNO N. 0208770767
    - 646,72
    20/03/26
    21/03/26
    21/03/26
    NUMIA-INTER DEL 20/03/26
    100,00
    21/03/26
    """
    rows = parse_bpm_text(text)
    assert len(rows) == 2
    assert rows[0]["descrizione"] == "VOSTRO ASSEGNO N. 0208770767"
    assert "EUREKA" not in rows[0]["descrizione"]
